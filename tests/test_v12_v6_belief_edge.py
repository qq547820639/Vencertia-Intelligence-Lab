"""v1.2 V-6 BeliefEdge causal graph + shared_signal_group anti-double-counting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vencertia.config import Settings
from vencertia.domain import Belief, BeliefEdge, BeliefRelationType, Evidence
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.evidence_policy import EvidencePolicy

# --- enum contract -----------------------------------------------------------


def test_belief_relation_type_has_exactly_nine_members():
    assert len(BeliefRelationType) == 9
    assert {m.value for m in BeliefRelationType} == {
        "CAUSES",
        "DEPENDS_ON",
        "MEDIATES",
        "MODERATES",
        "SHARES_LATENT_FACTOR",
        "SHARED_SIGNAL",
        "REDUNDANT_WITH",
        "MUTUALLY_EXCLUSIVE",
        "UNKNOWN_RELATIONSHIP",
    }


def test_belief_edge_validation_and_enum_values():
    edge = BeliefEdge(
        id="BE_1",
        source_belief_id="BLF_A",
        target_belief_id="BLF_B",
        relation="CAUSES",
    )
    assert edge.relation == "CAUSES"  # use_enum_values -> plain string
    assert edge.version == 1
    assert edge.decision_id is None
    assert edge.project_id is None


def test_belief_edge_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        BeliefEdge(
            id="BE_1",
            source_belief_id="BLF_A",
            target_belief_id="BLF_B",
            relation="CAUSES",
            unexpected_field=True,
        )


# --- Evidence backward compatibility ------------------------------------------


def test_evidence_without_shared_signal_group_validates():
    ev = Evidence.model_validate(
        {
            "id": "E_1",
            "claim_ids": [],
            "scope": "PROJECT",
            "evidence_type": "OBSERVED_BEHAVIOR",
            "source": "x",
        }
    )
    assert ev.shared_signal_group is None


def test_evidence_shared_signal_group_roundtrips():
    ev = Evidence(
        id="E_1",
        scope="PROJECT",
        evidence_type="OBSERVED_BEHAVIOR",
        source="x",
        shared_signal_group="pay_signal",
    )
    roundtripped = Evidence.model_validate(ev.model_dump(mode="json"))
    assert roundtripped.shared_signal_group == "pay_signal"


# --- shared_signal discount ---------------------------------------------------


def _belief(bid: str, claim_id: str) -> Belief:
    return Belief(
        id=bid,
        claim_id=claim_id,
        statement=bid,
        scope="PROJECT",
        project_id="PRJ_1",
        decision_relevant=True,
    )


def _ev(eid: str, claim_id: str, group: str | None) -> Evidence:
    return Evidence(
        id=eid,
        claim_ids=[claim_id],
        scope="PROJECT",
        evidence_type="OBSERVED_BEHAVIOR",
        source="test",
        supports_or_contradicts="SUPPORTS",
        shared_signal_group=group,
    )


def test_shared_signal_discount_applies_across_beliefs():
    policy = EvidencePolicy(Settings())
    engine = BeliefEngine(policy=policy)
    out = engine.update(
        BeliefUpdateInput(
            beliefs=[
                _belief("BLF_wtp", "CLM_wtp"),
                _belief("BLF_problem", "CLM_problem"),
            ],
            evidence=[
                _ev("E_wtp", "CLM_wtp", "pay_signal"),
                _ev("E_problem", "CLM_problem", "pay_signal"),
            ],
            policy=policy,
        )
    )
    by_belief = {a.belief_id: a for a in out.applications}
    assert by_belief["BLF_wtp"].signal_discount == 1.0
    assert by_belief["BLF_problem"].signal_discount == pytest.approx(0.5)


def test_distinct_or_absent_signal_groups_get_full_discount():
    policy = EvidencePolicy(Settings())
    engine = BeliefEngine(policy=policy)
    out = engine.update(
        BeliefUpdateInput(
            beliefs=[
                _belief("BLF_wtp", "CLM_wtp"),
                _belief("BLF_problem", "CLM_problem"),
            ],
            evidence=[
                _ev("E_none", "CLM_wtp", None),
                _ev("E_other", "CLM_problem", "other_signal"),
            ],
            policy=policy,
        )
    )
    assert out.applications
    assert all(a.signal_discount == 1.0 for a in out.applications)


def test_dedup_discount_unaffected_by_signal_discount():
    policy = EvidencePolicy(Settings())
    engine = BeliefEngine(policy=policy)

    def _grouped_ev(eid: str) -> Evidence:
        return Evidence(
            id=eid,
            claim_ids=["CLM_wtp"],
            scope="PROJECT",
            evidence_type="PRIMARY_RESEARCH",
            source="test",
            supports_or_contradicts="SUPPORTS",
            independence_group="grp",
        )

    out = engine.update(
        BeliefUpdateInput(
            beliefs=[_belief("BLF_wtp", "CLM_wtp")],
            evidence=[_grouped_ev("E_1"), _grouped_ev("E_2")],
            policy=policy,
        )
    )
    apps = sorted(out.applications, key=lambda a: a.evidence_id)
    assert [a.dedup_discount for a in apps] == [1.0, 0.5]
    assert all(a.signal_discount == 1.0 for a in apps)


# --- persistence ---------------------------------------------------------------


@pytest.mark.parametrize("repo", [InMemoryRepository(), SQLiteRepository(path=":memory:")])
def test_belief_edge_persistence_roundtrip(repo):
    edge = BeliefEdge(
        id="BE_1",
        project_id="PRJ_1",
        decision_id="DEC_1",
        source_belief_id="BLF_A",
        target_belief_id="BLF_B",
        relation="CAUSES",
    )
    repo.save_belief_edge(edge)

    loaded = repo.get_belief_edge("BE_1")
    assert loaded is not None
    assert loaded.relation == "CAUSES"
    assert loaded.version == 1

    listed = repo.list_belief_edges(project_id="PRJ_1")
    assert [e.id for e in listed] == ["BE_1"]
    assert repo.list_belief_edges(project_id="OTHER") == []
    assert repo.list_belief_edges(decision_id="DEC_1")[0].id == "BE_1"
