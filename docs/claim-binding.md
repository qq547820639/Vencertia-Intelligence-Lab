# Claim Binding（v1.1）

> 版本：1.1 · 关联：ADR-008 · 施工：T02/T03

## 目的

把"研究证据"变成"绑定了 Claim 的 Evidence"，让证据真正进入 Belief 的证据链，
同时留下可审计、可评估的绑定记录。

## 流水线

1. **ClaimExtractor**：Research Result → CandidateClaim[]。默认 deterministic：
   对既有 claim statement 做 token recall（含 `_WORD_FAMILY` 同义/词形归一化，
   如 paid→pay、icps→icp），recall ≥ 0.6 产出候选。
2. **DeterministicClaimMatcher**：Candidate → existing claims。
   - exact（归一化全等）= 1.0
   - normalized / lexical overlap ≥ 0.7 → EXISTING_MATCH
   - ≥2 claims → MULTIPLE_MATCH
   - 无 → NO_MATCH
3. **Candidate validation**（仅 NO_MATCH 的新候选）：非空 / scope 合法 / 长度界 /
   与既有 claim 归一化去重 → `validation_status=PENDING` 入库。
4. **EvidenceClaimLinker**：按 `binding_confidence = match_score × extraction_confidence`
   与 threshold 产出 BOUND 绑定；无匹配 → UNBOUND_EVIDENCE（claim_id=None）。

## 关键接口

```python
class ClaimBindingEngine:
    def __init__(self, extractor, matcher, linker, policy, repo, bus=None, settings=None): ...
    def process(self, inp: ClaimBindingInput) -> ClaimBindingOutput: ...
```

`ClaimBindingOutput`：`bindings`（BOUND）/ `unbound`（UNBOUND）/ `new_candidates` /
`applied_evidence`（已过 Policy 分级）/ `rejected_evidence` / `notes`。

## 可重处理

`EvidenceClaimBinding.retry_count` 记录 UNBOUND 重处理次数；用户重调
`/v1/evidence/bind` 可重跑（`settings.binding_auto_retry=False` 默认不自动）。
