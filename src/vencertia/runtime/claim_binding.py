"""ClaimBindingEngine — the deterministic evidence→claim binding pipeline.

Pipeline (ADR-008): Research Result → ClaimExtractor (candidates) →
DeterministicClaimMatcher (existing / multiple / no match) → candidate
validation → EvidenceClaimLinker → EvidenceClaimBinding (BOUND | UNBOUND).

Rules:
- No match is NEVER silently bound: it becomes an explicit UNBOUND_EVIDENCE
  binding with claim_id=None (re-processable via retry_count).
- Candidate claims must pass deterministic validation before persistence
  (validation_status=PENDING); they never become canonical Claims here.
- Binding-level scope gate: COMPANY_CASE evidence may only bind
  COMPANY_CASE/WORLD/MARKET claims; PROJECT evidence only PROJECT/CUSTOMER.
- binding_confidence = match_score × extraction_confidence.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    BindingMethod,
    BindingStatus,
    CandidateClaim,
    Claim,
    ClaimBindingInput,
    ClaimBindingOutput,
    ClaimMatchResult,
    ClaimType,
    Direction,
    Evidence,
    EvidenceClaimBinding,
    EvidenceType,
    Scope,
    Verification,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.repositories.base import Repository
from vencertia.runtime.evidence_policy import EvidencePolicy

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "of",
    "to", "in", "on", "at", "by", "with", "from", "as", "is", "are", "was",
    "were", "will", "would", "can", "could", "should", "this", "that", "these",
    "those", "it", "its", "they", "them", "he", "she", "we", "our", "you",
    "your", "their", "not", "no", "yes", "do", "does", "did", "have", "has",
    "had", "be", "been", "being", "more", "most", "than", "so", "such",
}

# Lightweight synonym/stem normalization for the deterministic offline
# baseline (documented; a real stemmer would replace this table).
_WORD_FAMILY = {
    "paid": "pay",
    "paying": "pay",
    "pays": "pay",
    "icps": "icp",
    "founders": "founder",
    "problems": "problem",
    "pilots": "pilot",
    "signals": "signal",
}

# Binding-level scope matrix (design §4.1 rule 4)
_COMPANY_CASE_CLAIM_SCOPES = {Scope.COMPANY_CASE.value, Scope.WORLD.value, Scope.MARKET.value}
_PROJECT_CLAIM_SCOPES = {Scope.PROJECT.value, Scope.CUSTOMER.value}


class SemanticClaimMatcher(Protocol):
    """Replaceable semantic matcher adapter (v1.1 not implemented)."""

    def similarity(self, query: str, candidates: list[str]) -> list[float]: ...


class ClaimExtractor:
    """Research Result → CandidateClaim[] (capability output, candidates only)."""

    def __init__(
        self,
        model=None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model

    def extract(self, result: dict, context) -> list[CandidateClaim]:
        text = self._text_of(result)
        claims = self._claims_from_context(context)
        candidates: list[CandidateClaim] = []
        for claim in claims:
            recall = token_recall(text, claim.statement)
            if recall >= 0.6:
                candidates.append(
                    CandidateClaim(
                        id="CC_" + uuid4().hex,
                        statement=claim.statement,
                        scope=claim.scope,
                        claim_type=claim.claim_type or ClaimType.HYPOTHESIS,
                        source_evidence_ids=[
                            str(result.get("evidence_id") or result.get("id") or "")
                        ],
                        extractor_model=getattr(self.model, "name", None),
                        extractor_provider="mock" if self.model is None else "provider",
                        extraction_confidence=round(recall, 6),
                    )
                )
        return candidates

    @staticmethod
    def _text_of(result: dict) -> str:
        for key in ("source", "content", "snippet", "title", "text"):
            value = result.get(key)
            if value:
                return str(value)
        return str(result)

    @staticmethod
    def _claims_from_context(context) -> list[Claim]:
        claims: list[Claim] = []
        raw = getattr(context, "claims", None) or (context or {}).get("claims")
        if raw:
            for item in raw:
                if isinstance(item, Claim):
                    claims.append(item)
                elif isinstance(item, dict):
                    try:
                        claims.append(Claim.model_validate(item))
                    except Exception:  # noqa: BLE001 - skip malformed context entries
                        continue
        # Fall back to beliefs' claim statements.
        if not claims:
            critical = getattr(context, "critical_assumptions", None) or (context or {}).get(
                "critical_assumptions"
            )
            if critical:
                for belief in critical:
                    claim_id = getattr(belief, "claim_id", None)
                    statement = getattr(belief, "statement", "")
                    scope = getattr(belief, "scope", Scope.PROJECT)
                    if statement:
                        claims.append(
                            Claim(
                                id=claim_id or "CLM_" + str(uuid4().hex),
                                statement=str(statement),
                                scope=scope,
                            )
                        )
        return claims


def normalize_text(text: str) -> str:
    """Lowercase / strip punctuation / fold whitespace / unify CJK width."""
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_set(text: str) -> set[str]:
    return {_WORD_FAMILY.get(t, t) for t in normalize_text(text).split() if t not in _STOPWORDS and len(t) > 1}


def lexical_overlap(a: str, b: str) -> float:
    """Jaccard overlap of normalized token sets (0..1)."""
    ta = token_set(a)
    tb = token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def token_recall(a: str, b: str) -> float:
    """Fraction of b's tokens covered by a (0..1); used by the extractor."""
    ta = token_set(a)
    tb = token_set(b)
    if not tb:
        return 0.0
    return len(ta & tb) / len(tb)


class DeterministicClaimMatcher:
    """Normalized matching baseline: exact → normalized → lexical.

    v1.1.1 (GAP-01): the match threshold is ``settings.binding_min_score``
    (no hard-coded magic number), and the returned :class:`ClaimMatchResult`
    always carries the full score map so the engine can classify
    BOUND / AMBIGUOUS / REJECTED / UNBOUND_EVIDENCE.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def normalize(self, text: str) -> str:
        return normalize_text(text)

    def match(
        self,
        candidate: CandidateClaim,
        existing: list[Claim],
        semantic: SemanticClaimMatcher | None = None,
    ) -> ClaimMatchResult:
        if not existing:
            return ClaimMatchResult(candidate=candidate, verdict="NEW_CANDIDATE")
        cand_norm = self.normalize(candidate.statement)
        cand_tokens = token_set(candidate.statement)
        scores: dict[str, float] = {}
        for claim in existing:
            claim_norm = self.normalize(claim.statement)
            if cand_norm and cand_norm == claim_norm:
                scores[claim.id] = 1.0
                continue
            ct = token_set(claim.statement)
            if cand_tokens and ct:
                overlap = len(cand_tokens & ct) / len(cand_tokens)
                scores[claim.id] = round(overlap, 6)
        if semantic is not None:
            # Semantic adapter may raise scores above lexical baseline.
            semantic_scores = semantic.similarity(candidate.statement, [c.statement for c in existing])
            for claim, score in zip(existing, semantic_scores):
                scores[claim.id] = max(scores.get(claim.id, 0.0), float(score))

        min_score = self.settings.binding_min_score
        matched = [(cid, s) for cid, s in scores.items() if s >= min_score]
        if not matched:
            # Always return the full score map (GAP-01) so the engine can
            # distinguish "no candidate" from "candidate below reliability".
            return ClaimMatchResult(candidate=candidate, scores=scores, verdict="NO_MATCH")
        if len(matched) > 1:
            return ClaimMatchResult(
                candidate=candidate,
                matched_claim_ids=[cid for cid, _ in matched],
                scores=dict(matched),
                verdict="MULTIPLE_MATCH",
            )
        return ClaimMatchResult(
            candidate=candidate,
            matched_claim_ids=[matched[0][0]],
            scores=dict(matched),
            verdict="EXISTING_MATCH",
        )


class EvidenceClaimLinker:
    """Evidence → Claim many-to-many binding; no match → UNBOUND_EVIDENCE."""

    def link(
        self,
        evidence: Evidence,
        result: ClaimMatchResult,
        threshold: float,
        scope_ok: Callable[[str, str], bool] | None = None,
    ) -> list[EvidenceClaimBinding]:
        bindings: list[EvidenceClaimBinding] = []
        for claim_id in result.matched_claim_ids:
            if scope_ok is not None and not scope_ok(evidence.scope, claim_id):
                continue
            match_score = result.scores.get(claim_id, 0.0)
            confidence = round(match_score * result.candidate.extraction_confidence, 6)
            if confidence < threshold:
                continue
            bindings.append(
                EvidenceClaimBinding(
                    id="EB_" + uuid4().hex,
                    evidence_id=evidence.id,
                    claim_id=claim_id,
                    binding_confidence=confidence,
                    binding_method=BindingMethod.LEXICAL_MATCH,
                    model=result.candidate.extractor_model,
                    provider=result.candidate.extractor_provider,
                    matched_at=utcnow(),
                )
            )
        return bindings


class ClaimBindingEngine:
    """Binding pipeline orchestrator: Extract → Match → Validate → Link → Persist."""

    def __init__(
        self,
        extractor: ClaimExtractor | None = None,
        matcher: DeterministicClaimMatcher | None = None,
        linker: EvidenceClaimLinker | None = None,
        policy: EvidencePolicy | None = None,
        repo: Repository | None = None,
        bus: EventBus | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.extractor = extractor or ClaimExtractor(settings=self.settings)
        self.matcher = matcher or DeterministicClaimMatcher(self.settings)
        self.linker = linker or EvidenceClaimLinker()
        self.policy = policy or EvidencePolicy(self.settings)
        self.repo = repo
        self.bus = bus

    def process(self, inp: ClaimBindingInput) -> ClaimBindingOutput:
        existing = [Claim.model_validate(c) if isinstance(c, dict) else c for c in inp.existing_claims]
        bindings: list[EvidenceClaimBinding] = []
        unbound: list[EvidenceClaimBinding] = []
        new_candidates: list[CandidateClaim] = []
        applied: list[Evidence] = []
        rejected: list[dict] = []
        notes: list[str] = []
        min_score = inp.binding_min_score if inp.binding_min_score is not None else self.settings.binding_min_score
        ambiguity_margin = (
            inp.binding_ambiguity_margin
            if inp.binding_ambiguity_margin is not None
            else self.settings.binding_ambiguity_margin
        )
        reject_threshold = (
            inp.binding_reject_threshold
            if inp.binding_reject_threshold is not None
            else self.settings.binding_reject_threshold
        )

        for result in inp.research_results:
            evidence = self._to_evidence(result)
            candidates = self.extractor.extract(result, inp.context) if inp.auto_extract else []
            match_results: list[ClaimMatchResult] = []
            validation_failed = False
            for candidate in candidates:
                mr = self.matcher.match(candidate, existing)
                match_results.append(mr)
                if mr.verdict == "NO_MATCH":
                    if self._validate_candidate(candidate, existing):
                        if self.repo is not None:
                            self.repo.save_candidate_claim(candidate)
                        new_candidates.append(candidate)
                    else:
                        validation_failed = True
                        rejected.append(
                            {"evidence_id": evidence.id, "reason": "candidate failed deterministic validation"}
                        )

            claim_scope_by_id = {c.id: c.scope.value if hasattr(c.scope, "value") else c.scope for c in existing}

            def _scope_ok(evidence_scope, claim_id: str, _scope_map: dict = claim_scope_by_id) -> bool:
                cscope = _scope_map.get(claim_id)
                if cscope is None:
                    return True
                return ClaimBindingEngine._scope_ok(evidence_scope, cscope)

            # ---- GAP-01 four-state classification per evidence ----
            candidate_scores: dict[str, float] = {}
            claim_extraction: dict[str, float] = {}
            for mr in match_results:
                conf = float(mr.candidate.extraction_confidence)
                for cid, score in mr.scores.items():
                    if score >= reject_threshold:
                        candidate_scores[cid] = max(candidate_scores.get(cid, 0.0), score)
                        claim_extraction[cid] = max(claim_extraction.get(cid, 0.0), conf)
            candidate_ids = sorted(candidate_scores, key=lambda c: (-candidate_scores[c], c))

            bound_claims: set[str] = set()
            status = BindingStatus.UNBOUND_EVIDENCE
            reason = "no candidate reached minimum reliability score"
            if validation_failed and not candidate_scores:
                status = BindingStatus.REJECTED
                reason = "candidate failed deterministic validation"

            reliable = {cid: s for cid, s in candidate_scores.items() if s >= min_score}
            if reliable:
                scope_ok_ids = [cid for cid in reliable if _scope_ok(evidence.scope, cid)]
                if not scope_ok_ids:
                    # Candidates existed but every one violates the binding
                    # scope matrix → explicit REJECTED (not UNBOUND).
                    status = BindingStatus.REJECTED
                    reason = "scope mismatch / company-case isolation violation"
                else:
                    ranked = sorted(scope_ok_ids, key=lambda c: (-reliable[c], c))
                    # Round the top-1/top-2 gap to 7dp so a gap exactly on the
                    # ambiguity margin (e.g. 0.90-0.80=0.09999...98) is not
                    # misclassified by binary float noise (MAJOR-CB-001; same
                    # guard class as decision_sensitivity._classify). 7dp keeps
                    # genuine sub-boundary gaps (e.g. 0.0999999) below the
                    # margin, while 6dp would collapse them to the boundary.
                    if (
                        len(ranked) >= 2
                        and round(reliable[ranked[0]] - reliable[ranked[1]], 7) < ambiguity_margin
                    ):
                        # Top-1/top-2 are too close: forcing top-1 is forbidden.
                        status = BindingStatus.AMBIGUOUS
                        reason = (
                            f"top candidates within ambiguity margin: "
                            f"{ranked[0]}={reliable[ranked[0]]:.3f}, {ranked[1]}={reliable[ranked[1]]:.3f}"
                        )
                    else:
                        linked: list[EvidenceClaimBinding] = []
                        for cid in ranked:
                            match_score = reliable[cid]
                            confidence = round(match_score * claim_extraction.get(cid, 0.5), 6)
                            if confidence < inp.binding_confidence_threshold:
                                continue
                            linked.append(
                                EvidenceClaimBinding(
                                    id="EB_" + uuid4().hex,
                                    evidence_id=evidence.id,
                                    claim_id=cid,
                                    binding_confidence=confidence,
                                    binding_method=ClaimBindingEngine._binding_method(match_score),
                                    model=match_results[0].candidate.extractor_model if match_results else None,
                                    provider=match_results[0].candidate.extractor_provider if match_results else None,
                                    matched_at=utcnow(),
                                    candidate_claim_ids=candidate_ids,
                                    candidate_scores=dict(candidate_scores),
                                    selected_claim_ids=[cid],
                                    reason="clear match reached binding threshold",
                                )
                            )
                        if linked:
                            status = BindingStatus.BOUND
                            selected = [b.claim_id for b in linked]
                            bindings.extend(linked)
                            bound_claims.update(selected)
                        else:
                            # Reliable candidate(s) but the combined confidence
                            # (score × extraction) did not reach the threshold.
                            status = BindingStatus.UNBOUND_EVIDENCE
                            reason = "candidates reliable but binding confidence below threshold"

            if status != BindingStatus.BOUND:
                unbound.append(
                    EvidenceClaimBinding(
                        id="EB_" + uuid4().hex,
                        evidence_id=evidence.id,
                        claim_id=None,
                        binding_confidence=0.0,
                        binding_method=BindingMethod.EXTRACTOR_INFERRED,
                        status=status,
                        model=match_results[0].candidate.extractor_model if match_results else None,
                        provider=match_results[0].candidate.extractor_provider if match_results else None,
                        matched_at=utcnow(),
                        candidate_claim_ids=candidate_ids,
                        candidate_scores=dict(candidate_scores),
                        selected_claim_ids=[],
                        reason=reason,
                    )
                )

            evidence.claim_ids = sorted(bound_claims)
            if bound_claims:
                grade = self.policy.grade(evidence)
                if grade.scope_gate == "REJECTED":
                    rejected.append(
                        {"evidence_id": evidence.id, "reason": f"scope gate: {grade.reason}"}
                    )
                else:
                    graded = self.policy.apply_authority(evidence, self.settings.policy_version)
                    applied.append(graded)
                    if self.repo is not None:
                        self.repo.add_evidence(graded)
                    if self.bus is not None:
                        self.bus.publish(
                            make_event(
                                EventType.EVIDENCE_ADDED,
                                "evidence",
                                graded.id,
                                {
                                    "scope_gate": grade.scope_gate,
                                    "authority": graded.authority_level,
                                    "claim_ids": list(bound_claims),
                                },
                            )
                        )
            elif self.repo is not None:
                # Persist unbound evidence as an explicit auditable record.
                self.repo.add_evidence(evidence)

        # Persist bindings + emit events.
        if self.repo is not None:
            for binding in bindings:
                self.repo.save_binding(binding)
            for binding in unbound:
                self.repo.save_binding(binding)
        if self.bus is not None:
            for binding in bindings:
                self.bus.publish(
                    make_event(
                        EventType.EVIDENCE_BOUND_TO_CLAIM,
                        "binding",
                        binding.id,
                        {
                            "evidence_id": binding.evidence_id,
                            "claim_id": binding.claim_id,
                            "confidence": binding.binding_confidence,
                            "status": binding.status,
                        },
                    )
                )
            for binding in unbound:
                self.bus.publish(
                    make_event(
                        EventType.EVIDENCE_BINDING_REJECTED,
                        "binding",
                        binding.id,
                        {
                            "evidence_id": binding.evidence_id,
                            "status": binding.status,
                            "reason": binding.reason,
                        },
                    )
                )

        if new_candidates:
            notes.append(f"{len(new_candidates)} candidate claim(s) saved (PENDING validation).")
        if unbound:
            notes.append(f"{len(unbound)} evidence item(s) not bound "
                         f"({', '.join(sorted({u.status for u in unbound}))}).")
        return ClaimBindingOutput(
            bindings=bindings,
            unbound=unbound,
            new_candidates=new_candidates,
            applied_evidence=[e.model_dump(mode="json") for e in applied],
            rejected_evidence=rejected,
            notes=notes,
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _binding_method(score: float) -> BindingMethod:
        """Pick the binding method from the match score (deterministic)."""
        if score >= 0.999:
            return BindingMethod.EXACT_MATCH
        if score >= 0.85:
            return BindingMethod.NORMALIZED_MATCH
        return BindingMethod.LEXICAL_MATCH

    @staticmethod
    def _scope_ok(evidence_scope: str, claim_scope: str) -> bool:
        """Binding-level scope matrix (design §4.1 rule 4)."""
        escope = evidence_scope.value if hasattr(evidence_scope, "value") else str(evidence_scope)
        cscope = claim_scope.value if hasattr(claim_scope, "value") else str(claim_scope)
        if escope == Scope.COMPANY_CASE.value:
            return cscope in _COMPANY_CASE_CLAIM_SCOPES
        if escope in (Scope.PROJECT.value, Scope.CUSTOMER.value):
            return cscope in _PROJECT_CLAIM_SCOPES
        return True  # MARKET / WORLD / FOUNDER evidence may bind any claim

    def _validate_candidate(self, candidate: CandidateClaim, existing: list[Claim]) -> bool:
        """Deterministic validation: candidates must be well-formed + non-duplicate."""
        statement = (candidate.statement or "").strip()
        if len(statement) < 4 or len(statement) > 1000:
            return False
        try:
            Scope(candidate.scope.value if hasattr(candidate.scope, "value") else candidate.scope)
        except ValueError:
            return False
        cand_norm = self.matcher.normalize(statement)
        return all(self.matcher.normalize(claim.statement) != cand_norm for claim in existing)

    def _to_evidence(self, result: dict) -> Evidence:
        """Normalize a research-result dict into a candidate Evidence record."""
        source_text = (
            str(result.get("source") or result.get("content") or result.get("snippet") or result.get("title") or "")
        )
        return Evidence(
            id=str(result.get("evidence_id") or result.get("id") or "E_" + uuid4().hex),
            claim_ids=[],
            scope=result.get("scope", Scope.MARKET),
            evidence_type=result.get("evidence_type", EvidenceType.REVIEWED_EXTERNAL_RESEARCH),
            provenance={
                "tool": "ClaimBindingEngine",
                "source_url": result.get("url") or "",
                "raw_extract": source_text,
            },
            source=source_text,
            directness=float(result.get("directness", 0.6)),
            reliability=float(result.get("reliability", 0.6)),
            relevance=float(result.get("relevance", 0.6)),
            strength=float(result.get("strength", 0.5)),
            supports_or_contradicts=result.get("supports_or_contradicts", Direction.SUPPORTS),
            independence_group=result.get("independence_group"),
            observed_at=utcnow(),
            authority_level=result.get("authority_level", "REVIEWED_EXTERNAL_RESEARCH"),
            verification=result.get("verification", Verification.ESTIMATED),
            content_fingerprint=result.get("content_fingerprint"),
            canonical_source_id=result.get("canonical_source_id"),
            source_family=result.get("source_family"),
        )
