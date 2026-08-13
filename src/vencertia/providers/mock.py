"""Mock providers — deterministic offline outputs (default for v1.0/v1.1).

The mock provider recognizes task kinds (compile/research/extract/match/
research_plan) and returns canned, deterministic structures so the whole system
runs without any external API. Provider names are normalized (``name``
attribute) so observability records are stable.
"""

from __future__ import annotations

from uuid import uuid4

from vencertia.providers.models import Document, SearchResult


class MockProvider:
    """Deterministic structured/prompt output provider."""

    name = "mock"

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        kind = schema.get("kind") or task
        if "compile" in kind:
            return self._compile(context)
        if "research" in kind or "search" in kind:
            return self._research(context)
        if "extract" in kind:
            return self._extract(context)
        if "match" in kind:
            return self._match(context)
        if "research_plan" in kind:
            return self._research_plan(context)
        return {
            "result": task,
            "context": {k: v for k, v in context.items() if not isinstance(v, (bytes, bytearray))},
            "note": "mock provider fallback",
        }

    def complete(self, prompt: str) -> str:
        return f"[mock] deterministic completion of prompt ({len(prompt)} chars)."

    # -- templates -------------------------------------------------------------

    def _compile(self, context: dict) -> dict:
        problem = context.get("problem_text", "Should we proceed with the venture?")
        user_id = context.get("user_id", "u_default")
        project_id = context.get("project_id", "PRJ_mock")
        text = problem.lower()
        options = context.get("options")
        if options:
            compiled_options = options
        elif any(k in text for k in ("commit", "mvp", "build", "six week", "6 week")):
            compiled_options = [
                {
                    "id": "commit_mvp",
                    "label": "Commit six weeks to build the MVP",
                    "description": "Full-time commitment to ship MVP",
                    "kind": "GO",
                    "base_utility": 0.05,
                    "belief_coefficients": {"wtp": 0.85, "problem": 0.45, "access": 0.3},
                    "irreversible_cost": 0.4,
                    "opportunity_cost": 0.1,
                },
                {
                    "id": "stop_project",
                    "label": "Stop and redeploy resources",
                    "description": "Stop investing; redeploy to higher-value use",
                    "kind": "KILL",
                    "base_utility": 0.65,
                    "belief_coefficients": {"wtp": -0.3, "problem": -0.2, "access": -0.1},
                    "irreversible_cost": 0.02,
                    "opportunity_cost": 0.0,
                },
            ]
        elif any(k in text for k in ("pivot", "change direction")):
            compiled_options = [
                {
                    "id": "pivot_to_adjacent",
                    "label": "Pivot to adjacent market",
                    "kind": "PIVOT",
                    "base_utility": 0.4,
                    "belief_coefficients": {"problem": 0.4, "wtp": 0.3},
                    "irreversible_cost": 0.15,
                    "opportunity_cost": 0.05,
                },
                {
                    "id": "hold_current",
                    "label": "Hold current course",
                    "kind": "HOLD",
                    "base_utility": 0.2,
                    "belief_coefficients": {"problem": 0.1, "wtp": 0.1},
                    "irreversible_cost": 0.0,
                    "opportunity_cost": 0.0,
                },
            ]
        else:
            compiled_options = [
                {
                    "id": "proceed",
                    "label": "Proceed with investment",
                    "kind": "GO",
                    "base_utility": 0.3,
                    "belief_coefficients": {"problem": 0.4, "wtp": 0.6},
                    "irreversible_cost": 0.25,
                    "opportunity_cost": 0.1,
                },
                {
                    "id": "hold",
                    "label": "Hold and investigate more",
                    "kind": "HOLD",
                    "base_utility": 0.25,
                    "belief_coefficients": {"problem": 0.1, "wtp": 0.2},
                    "irreversible_cost": 0.0,
                    "opportunity_cost": 0.0,
                },
            ]
        return {
            "objective": {
                "id": f"OBJ_{uuid4().hex}",
                "owner": user_id,
                "name": "Maximize expected venture value",
                "description": problem,
                "metric": "expected company value (incl. option value)",
                "direction": "MAXIMIZE",
                "weight": 1.0,
                "constraints": ["preserve runway", "no irreversible over-commit before evidence"],
                "time_horizon": "18 months",
                "priority": 5,
                "source": "capability:mock",
            },
            "decision": {
                "id": f"DEC_{uuid4().hex}",
                "decision_question": problem,
                "objective_id": "OBJ_PENDING",
                "project_id": project_id,
                "options": compiled_options,
                "decision_type": None,
                "horizon": "short",
                "reversible": True,
                "estimated_cost": 0.0,
                "relevant_belief_ids": ["wtp", "problem", "access"],
                "status": "DRAFT",
            },
            "claims": [
                {
                    "id": "CLM_PROBLEM",
                    "statement": "ICP has a severe recurring problem",
                    "scope": "PROJECT",
                    "claim_type": "HYPOTHESIS",
                    "project_id": project_id,
                },
                {
                    "id": "CLM_WTP",
                    "statement": "ICP will pay for the promised outcome",
                    "scope": "PROJECT",
                    "claim_type": "HYPOTHESIS",
                    "project_id": project_id,
                },
                {
                    "id": "CLM_ACCESS",
                    "statement": "Founder can reach enough ICPs for validation",
                    "scope": "PROJECT",
                    "claim_type": "HYPOTHESIS",
                    "project_id": project_id,
                },
            ],
            "beliefs": [
                {
                    "id": "problem",
                    "claim_id": "CLM_PROBLEM",
                    "statement": "ICP has a severe recurring problem",
                    "project_id": project_id,
                    "scope": "PROJECT",
                    "prior": 0.5,
                    "posterior": 0.5,
                    "alpha": 1.0,
                    "beta": 1.0,
                    "decision_weight": 0.8,
                    "decision_relevant": True,
                    "calibration_group": "default",
                },
                {
                    "id": "wtp",
                    "claim_id": "CLM_WTP",
                    "statement": "ICP will pay for the promised outcome",
                    "project_id": project_id,
                    "scope": "PROJECT",
                    "prior": 0.5,
                    "posterior": 0.5,
                    "alpha": 1.0,
                    "beta": 1.0,
                    "decision_weight": 1.0,
                    "decision_relevant": True,
                    "calibration_group": "default",
                },
                {
                    "id": "access",
                    "claim_id": "CLM_ACCESS",
                    "statement": "Founder can reach enough ICPs for validation",
                    "project_id": project_id,
                    "scope": "PROJECT",
                    "prior": 0.5,
                    "posterior": 0.5,
                    "alpha": 1.0,
                    "beta": 1.0,
                    "decision_weight": 0.7,
                    "decision_relevant": True,
                    "calibration_group": "default",
                },
            ],
            "experiments": context.get("experiment_candidates") or [
                {
                    "id": "EXP_PAID_PILOT",
                    "name": "Sell a paid concierge pilot",
                    "decision_id": "DEC_PENDING",
                    "target_belief_ids": ["wtp"],
                    "hypothesis": "At least 2 of 20 ICPs pay for a manual pilot",
                    "action": "Offer the promised outcome manually to 20 ICPs within 30 days",
                    "predicted_observation": ">=2 paid pilots",
                    "success_criteria": ">=2 paid pilots",
                    "failure_criteria": "0 paid pilots",
                    "ambiguity_criteria": "1 paid pilot",
                    "expected_information_gain": 0.95,
                    "decision_impact": 1.0,
                    "cost": 1.0,
                    "time": 3.0,
                    "reversibility": 1.0,
                }
            ],
            "notes": ["compiled by mock provider"],
        }

    def _research(self, context: dict) -> dict:
        query = context.get("query", "market evidence")
        return {
            "evidence": [
                {
                    "id": f"E_{uuid4().hex}",
                    "claim_ids": list(context.get("claim_ids") or []),
                    "scope": "MARKET",
                    "evidence_type": "REVIEWED_EXTERNAL_RESEARCH",
                    "source": f"Mock research result for '{query}': secondary market signals.",
                    "directness": 0.6,
                    "reliability": 0.6,
                    "relevance": 0.6,
                    "strength": 0.5,
                    "supports_or_contradicts": "SUPPORTS",
                    "authority_level": "REVIEWED_EXTERNAL_RESEARCH",
                    "verification": "ESTIMATED",
                }
            ]
        }

    def _extract(self, context: dict) -> dict:
        """Deterministic candidate-claim extraction template (T03 hook).

        The runtime's ClaimExtractor uses this when a model is available; the
        extractor itself performs lexical overlap against existing claims so
        the pipeline remains deterministic even without this template.
        """
        text = str(context.get("text", ""))
        existing = context.get("existing_claims") or []
        candidates = []
        for claim in existing:
            statement = str(claim.get("statement", "")) if isinstance(claim, dict) else str(claim)
            lowered = text.lower()
            tokens = [t for t in statement.lower().split() if len(t) > 2]
            hits = sum(1 for t in tokens if t in lowered)
            score = hits / len(tokens) if tokens else 0.0
            if score >= 0.5:
                candidates.append(
                    {
                        "id": "CC_" + uuid4().hex,
                        "statement": statement,
                        "scope": claim.get("scope", "PROJECT") if isinstance(claim, dict) else "PROJECT",
                        "claim_type": "HYPOTHESIS",
                        "extraction_confidence": round(score, 6),
                    }
                )
        return {"candidates": candidates}

    def _match(self, context: dict) -> dict:
        """Deterministic match template (normalized + lexical)."""
        candidate = context.get("candidate", {})
        existing = context.get("existing_claims") or []
        statement = str(candidate.get("statement", "")).lower()
        matched: list[dict] = []
        for claim in existing:
            text = str(claim.get("statement", "")).lower() if isinstance(claim, dict) else str(claim).lower()
            shared = set(statement.split()) & set(text.split())
            score = len(shared) / max(1, len(set(statement.split()) | set(text.split())))
            if score >= 0.5:
                matched.append({"claim_id": claim.get("id") if isinstance(claim, dict) else claim, "score": round(score, 6)})
        return {"matched": matched}

    def _research_plan(self, context: dict) -> dict:
        """Deterministic research-plan template (T03 hook)."""
        criticals = context.get("criticals") or []
        questions = []
        for idx, c in enumerate(criticals):
            belief_id = c.get("belief_id", f"b{idx}")
            statement = c.get("statement", belief_id)
            impact = float(c.get("impact", 0.5))
            questions.append(
                {
                    "id": f"RQ_{uuid4().hex}",
                    "target_claim_ids": c.get("claim_ids", []),
                    "question": f"What is the best available evidence on: {statement}?",
                    "reason": f"Critical uncertainty impact={impact:.3f}",
                    "expected_decision_impact": round(min(1.0, impact), 6),
                    "preferred_source_types": ["OFFICIAL_DATA", "PRIMARY_RESEARCH"],
                    "search_queries": [f"{statement} evidence", f"{statement} market data"],
                    "stop_condition": "3 independent sources agree or belief delta < 0.02",
                }
            )
        return {"questions": questions}


class MockSearchProvider:
    """Returns a small built-in document set (no network).

    Snippets deliberately echo claim statements (problem / wtp / access) so the
    deterministic ClaimExtractor can bind them in offline scenarios.
    """

    name = "mock_search"

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        results = [
            SearchResult(
                title="Willingness to pay signals in SMB",
                url="https://mock.example/wtp",
                snippet=(
                    "Interviews alone overstate willingness to pay; ICP will pay for the "
                    "promised outcome only when value is demonstrated by a paid pilot."
                ),
                source="mock_research",
            ),
            SearchResult(
                title="ICP problem severity benchmarks",
                url="https://mock.example/problem",
                snippet=(
                    "Early ICPs report a severe recurring problem: 8 of 10 list it as a "
                    "top-three pain point each week."
                ),
                source="mock_research",
            ),
            SearchResult(
                title="Founder reachability for validation",
                url="https://mock.example/access",
                snippet=(
                    "Founders who can reach enough ICPs for validation in two weeks are "
                    "significantly more likely to get decision-relevant signals."
                ),
                source="mock_research",
            ),
        ]
        return results[:k]


class MockRetrievalProvider:
    """Keyword-matched built-in documents (no vector store, ADR-006)."""

    name = "mock_retrieval"

    def retrieve(self, query: str, k: int = 5) -> list[Document]:
        corpus = [
            Document(
                id="DOC_01",
                content="Customer interviews: 8 of 10 report severe recurring problem.",
                metadata={"topic": "problem", "source": "mock"},
            ),
            Document(
                id="DOC_02",
                content=(
                    "Paid pilot evidence: 0 of 4 pilot prospects paid in first round — "
                    "ICP did not pay for the promised outcome in this sample."
                ),
                metadata={"topic": "wtp", "source": "mock"},
            ),
            Document(
                id="DOC_03",
                content="Founder can reach 20 ICPs in two weeks via personal network.",
                metadata={"topic": "access", "source": "mock"},
            ),
        ]
        q = query.lower()
        # v1.9: no silent fallback to the whole corpus — a query that matches
        # nothing returns nothing (fail honest, never fabricate matches).
        matched = [d for d in corpus if any(t in q for t in d.metadata["topic"])]
        return matched[:k]
