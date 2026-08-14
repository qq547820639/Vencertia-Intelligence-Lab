"""BusinessPlanComposer — 出口层：决策 → 商业计划章节（v2.0）。

Read-only projection over PERSISTED decision state (Decision / Beliefs /
Claims / Evidence / DecisionTrace / DecisionSensitivity / Experiments /
DecisionRecord / CalibrationProfile). Deterministic Chinese templates live in
``vencertia.presentation``; this module only assembles engine-neutral data.

Honesty contract: sections that lack data are marked ``na=True`` with an
honest note — the composer NEVER fabricates market facts or financials. The
Model Critique is not persisted by the runtime yet, so the critic section is
honestly N/A until solve-time persistence lands.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import Field

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    CalibrationScope,
    VencertiaBaseModel,
    utcnow,
)
from vencertia.repositories.base import EntityNotFoundError, Repository
from vencertia.runtime.calibration_engine import CalibrationInput


class BusinessPlanSection(VencertiaBaseModel):
    """One BP section: engine-neutral data + honest NA flag."""

    key: str  # executive_summary | market_opportunity | why_us | assumptions | plan | kill_triggers | review
    title: str  # English anchor title; Chinese copy lives in presentation
    data: dict = Field(default_factory=dict)
    na: bool = False
    na_reason: str = ""


class BusinessPlan(VencertiaBaseModel):
    plan_id: str
    decision_id: str
    company_name: str
    tagline: str = ""
    market_note: str = ""
    generated_at: str = Field(default_factory=lambda: utcnow().isoformat())
    sections: list[BusinessPlanSection] = Field(default_factory=list)
    assumption_register: list[dict] = Field(default_factory=list)
    honest_notes: list[str] = Field(default_factory=list)


class BusinessPlanComposer:
    """Assembles a data-driven business plan from a persisted decision."""

    def __init__(self, repo: Repository, engines, settings: Settings | None = None) -> None:
        self.repo = repo
        self.engines = engines
        self.settings = settings or get_settings()

    def compose(
        self,
        decision_id: str,
        company_name: str | None = None,
        tagline: str | None = None,
        market_note: str | None = None,
    ) -> BusinessPlan:
        decision = self.repo.get_decision(decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", decision_id)
        project_id = decision.project_id
        beliefs = self.repo.get_beliefs(project_id)
        beliefs_by_id = {b.id: b for b in beliefs}
        claims = {c.id: c for c in self.repo.list_claims(project_id)}
        evidence = self.repo.list_evidence(project_id=project_id)
        evidence_by_claim: dict[str, list] = {}
        for e in evidence:
            for cid in e.claim_ids:
                evidence_by_claim.setdefault(cid, []).append(e)
        trace = self.repo.get_decision_trace(decision_id)
        sensitivity = self.repo.get_decision_sensitivity(decision_id)
        record = self.repo.get_decision_record(decision_id)
        experiments = self.repo.list_experiments(project_id)

        def evidence_count(claim_id: str) -> int:
            return len(evidence_by_claim.get(claim_id, []))

        # -- executive summary -------------------------------------------------
        scores = [
            {
                "option_id": (s.get("option_id") if isinstance(s, dict) else s.option_id),
                "adjusted_utility": round(
                    float(s.get("adjusted_utility") if isinstance(s, dict) else s.adjusted_utility),
                    4,
                ),
            }
            for s in (trace.option_utilities if trace is not None else [])
        ]
        executive = {
            "decision_question": decision.decision_question,
            "status": _enum(decision.status if decision.status else "DRAFT"),
            "recommendation": decision.current_recommendation,
            "confidence": decision.confidence,
            "stakes_class": _enum(decision.stakes_class),
            "convergence": _enum(decision.convergence_status),
            "rationale": list(decision.rationale or []),
            "option_scores": scores,
        }

        # -- market opportunity ------------------------------------------------
        market_beliefs = [
            {
                "belief_id": b.id,
                "claim_id": b.claim_id,
                "statement": b.statement,
                "probability": round(float(b.probability), 4),
                "uncertainty": round(float(b.uncertainty), 4),
                "evidence_count": evidence_count(b.claim_id),
            }
            for b in beliefs
            if _enum(b.scope) in ("MARKET", "WORLD") or "market" in b.statement.lower()
        ]
        market = {
            "note": market_note or "",
            "beliefs": market_beliefs,
        }

        # -- why us --------------------------------------------------------------
        contributions = [
            {
                "belief_id": c.belief_id,
                "claim_id": c.claim_id,
                "contribution": c.contribution,
                "direction": c.direction,
                "statement": beliefs_by_id[c.belief_id].statement
                if c.belief_id in beliefs_by_id
                else "",
            }
            for c in (trace.belief_contributions if trace is not None else [])
        ]
        why_us = {
            "rationale": list(decision.rationale or []),
            "contributions": contributions,
            "margin": trace.margin if trace is not None else None,
        }

        # -- assumption register --------------------------------------------------
        flips_by_belief: dict[str, list] = {}
        if sensitivity is not None:
            for flip in sensitivity.flips:
                flips_by_belief.setdefault(flip.belief_id, []).append(
                    {
                        "threshold_value": flip.threshold_value,
                        "would_become": flip.would_become,
                        "direction": flip.direction,
                    }
                )
        register: list[dict] = []
        for b in sorted(beliefs, key=lambda x: x.uncertainty, reverse=True):
            claim = claims.get(b.claim_id)
            register.append(
                {
                    "belief_id": b.id,
                    "claim_id": b.claim_id,
                    "statement": b.statement,
                    "scope": _enum(b.scope),
                    "claim_type": _enum(claim.claim_type) if claim is not None else "HYPOTHESIS",
                    "probability": round(float(b.probability), 4),
                    "uncertainty": round(float(b.uncertainty), 4),
                    "evidence_count": evidence_count(b.claim_id),
                    "flips": flips_by_belief.get(b.id, []),
                }
            )
        robustness = sensitivity.robustness if sensitivity is not None else None
        what_changes = (
            list(sensitivity.what_could_change_my_mind) if sensitivity is not None else []
        )
        assumptions = {
            "register": register,
            "robustness": robustness,
            "what_could_change_my_mind": what_changes,
            "stakes_class": _enum(decision.stakes_class),
            "stakes": (
                decision.stakes.model_dump(mode="json") if decision.stakes is not None else None
            ),
        }

        # -- plan & milestones -----------------------------------------------------
        resolved = [
            e
            for e in experiments
            if _enum(e.status).startswith("RESOLVED") and e.decision_id == decision_id
        ]
        open_experiments = [
            {
                "experiment_id": e.id,
                "name": e.name,
                "action": e.action,
                "success_criteria": e.success_criteria,
                "failure_criteria": e.failure_criteria,
                "ambiguity_criteria": e.ambiguity_criteria,
                "cost": e.cost,
                "time_days": e.time,
                "status": _enum(e.status),
            }
            for e in experiments
            if not _enum(e.status).startswith("RESOLVED") and e.decision_id == decision_id
        ]
        plan = {
            "next_experiments": open_experiments[:3],
            "resolved_experiments": [
                {"experiment_id": e.id, "name": e.name, "status": _enum(e.status)}
                for e in resolved[:3]
            ],
            "decision_status": _enum(decision.status),
        }

        # -- kill triggers ----------------------------------------------------------
        kill_triggers = {
            "what_could_change_my_mind": what_changes,
            "stop_condition": (
                "；".join([r for r in (decision.rationale or [])[-1:]]) or None
            ),
            "stakes_class": _enum(decision.stakes_class),
            "convergence": _enum(decision.convergence_status),
        }

        # -- review & calibration ----------------------------------------------------
        outcomes = (
            self.repo.list_decision_outcome_records(record.id) if record is not None else []
        )
        profile = self.engines.calibration_engine.report(
            CalibrationInput(
                self.repo.list_predictions(),
                CalibrationScope("ALL"),
                "ALL",
                self.settings.ece_bins,
            )
        )
        review = {
            "record_status": record.status if record is not None else None,
            "action_taken": record.action_taken if record is not None else None,
            "outcome_count": len(outcomes),
            "calibration": {
                "n": profile.n,
                "brier_score": profile.brier_score,
                "expected_calibration_error": profile.expected_calibration_error,
                "empirical_rate": profile.empirical_rate,
            },
        }

        honest_notes: list[str] = []
        if not market_beliefs:
            honest_notes.append("市场机会章节无已采信的市场证据，未伪造任何市场规模数据。")
        honest_notes.append("模型自检（ModelCritique）仅在求解时生成且尚未持久化，本版如实标注为不可用。")
        if profile.n < self.settings.calibration_min_samples:
            honest_notes.append("校准样本不足，校准数字不构成有效性结论。")

        return BusinessPlan(
            plan_id="BP_" + uuid4().hex[:10],
            decision_id=decision_id,
            company_name=company_name or "未命名公司",
            tagline=tagline or "",
            market_note=market_note or "",
            sections=[
                BusinessPlanSection(key="executive_summary", title="执行摘要", data=executive),
                BusinessPlanSection(
                    key="market_opportunity",
                    title="市场机会",
                    data=market,
                    na=not market_beliefs,
                    na_reason="尚无已采信的市场/世界证据",
                ),
                BusinessPlanSection(key="why_us", title="为什么是我们", data=why_us),
                BusinessPlanSection(key="assumptions", title="关键假设与风险", data=assumptions),
                BusinessPlanSection(key="plan", title="计划与里程碑", data=plan),
                BusinessPlanSection(key="kill_triggers", title="什么会推翻这个计划", data=kill_triggers),
                BusinessPlanSection(key="review", title="复盘与校准", data=review),
            ],
            assumption_register=register,
            honest_notes=honest_notes,
        )


def _enum(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
