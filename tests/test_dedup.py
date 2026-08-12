"""Evidence dedup tests (v1.1)."""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Evidence
from vencertia.providers.search import content_fingerprint
from vencertia.runtime.evidence_dedup import EvidenceDedupEngine


def _evidence(eid, text, url="", family=None, fp=None) -> Evidence:
    return Evidence(
        id=eid, claim_ids=[], scope="MARKET", evidence_type="REVIEWED_EXTERNAL_RESEARCH",
        source=text,
        provenance={"source_url": url},
        content_fingerprint=fp or content_fingerprint(text),
        canonical_source_id=url or None,
        source_family=family,
    )


def test_exact_duplicates_dropped():
    engine = EvidenceDedupEngine(Settings())
    texts = ["same article text", "same article text", "same article text"]
    items = [_evidence(f"E_{i}", t) for i, t in enumerate(texts)]
    result = engine.group(items)
    assert len(result.dropped_ids) == 2
    assert len(result.kept_ids) == 1
    assert result.kept_ids[0] == "E_0"
    assert all(g.drop_reason == "EXACT_FINGERPRINT" for g in result.groups)


def test_different_content_kept():
    engine = EvidenceDedupEngine(Settings())
    items = [_evidence("E_0", "article one"), _evidence("E_1", "article two different")]
    result = engine.group(items)
    assert result.dropped_ids == []
    assert len(result.kept_ids) == 2


def test_same_source_family_shares_independence_group():
    engine = EvidenceDedupEngine(Settings(dedup_similarity_threshold=0.5))
    a = _evidence("E_A", "Company X raised a huge funding round yesterday", url="https://news.example/a", family="news.example")
    b = _evidence("E_B", "Company X raised a huge funding round yesterday (from a syndicate)", url="https://news.example/b", family="news.example")
    result = engine.group([a, b])
    # Both kept (similar, not exact) but share an independence group.
    assert len(result.kept_ids) == 2
    assert any(g.canonical_evidence_id in (a.id, b.id) for g in result.groups)
    members = [g for g in result.groups if g.canonical_evidence_id == a.id]
    assert members
    b2 = next(x for x in [a, b] if x.id == b.id)
    assert b2.independence_group is not None or any(
        g.independence_group == a.id for g in result.groups
    )


def test_fingerprint_uses_provided_hash():
    engine = EvidenceDedupEngine(Settings())
    fp = content_fingerprint("hello world")
    evidence = _evidence("E_1", "hello world", fp=fp)
    assert engine.fingerprint(evidence) == fp
