from __future__ import annotations
from collections import Counter
from .domain import Belief, Evidence, EvidenceApplication, Direction, SourceType, Verification

SOURCE_PRIOR = {
    SourceType.REAL_PAYMENT: 1.00,
    SourceType.CONTRACT: 0.95,
    SourceType.OBSERVED_BEHAVIOR: 0.88,
    SourceType.EXPERIMENT: 0.88,
    SourceType.OFFICIAL_DATA: 0.85,
    SourceType.PRIMARY_RESEARCH: 0.75,
    SourceType.RELIABLE_SECONDARY: 0.65,
    SourceType.EXPERT_INPUT: 0.55,
    SourceType.FOUNDER_REPORT: 0.45,
    SourceType.MODEL_INFERENCE: 0.20,
}
VERIFICATION_MULTIPLIER = {
    Verification.VERIFIED: 1.0,
    Verification.ESTIMATED: 0.75,
    Verification.ASSUMED: 0.35,
    Verification.UNKNOWN: 0.20,
}

class EvidenceEngine:
    """Deterministic evidence weighting. LLM output is deliberately low-prior evidence."""
    def apply(self, beliefs: list[Belief], evidence: list[Evidence]) -> tuple[list[Belief], list[EvidenceApplication]]:
        by_id={b.id:b.model_copy(deep=True) for b in beliefs}
        seen=Counter()
        apps=[]
        for e in sorted(evidence, key=lambda x: x.observed_at):
            b=by_id[e.belief_id]
            key=e.independence_key or f"__unique__:{e.id}"
            duplicate_index=seen[key]
            # Correlated evidence has sharply diminishing returns.
            discount=1.0/(1.0+duplicate_index)
            seen[key]+=1
            w=(SOURCE_PRIOR[e.source_type] * VERIFICATION_MULTIPLIER[e.verification] *
               e.strength * e.source_reliability * e.directness * discount)
            # Max 3 pseudo-observations per evidence item: strong real behavior moves beliefs, prose doesn't dominate.
            mass=3.0*w
            da=db=0.0
            if e.direction == Direction.SUPPORTS: da=mass
            elif e.direction == Direction.CONTRADICTS: db=mass
            else: da=db=0.15*mass
            b.alpha += da; b.beta += db; b.updated_at=e.observed_at
            apps.append(EvidenceApplication(evidence_id=e.id, belief_id=b.id,
                effective_weight=w, alpha_delta=da, beta_delta=db, deduplication_discount=discount))
        return list(by_id.values()), apps
