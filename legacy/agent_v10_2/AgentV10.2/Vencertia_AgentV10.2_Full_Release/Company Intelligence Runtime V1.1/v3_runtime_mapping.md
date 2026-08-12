# Startup Intelligence Company Case V1.4 → Runtime Mapping

This file does not redefine the V1.4 Company Case schema. It defines how Runtime consumes it.

| V1.4 source area | Runtime role | Runtime contract |
|---|---|---|
| Metadata / Company Identity | entity resolution, revision binding | `RuntimeMetadata`, `EntityResolutionResult` |
| Operating Segment / BU / Offer | scope compatibility | `CaseUnitRef` |
| Business Model Snapshot | time-aware comparison anchor | `CaseUnitRef.snapshot_id`, `valid_period` |
| Case Classification | retrieval role filtering | `CaseRole` |
| Market / Stakeholder / Demand / Buying | target profile + reranking | `ProjectRetrievalContext` + retrieval profile |
| Pricing Objects | pricing benchmark retrieval | `RetrievalObjective.PRICING` |
| Revenue Stream Registry | financial scope guard | `CaseUnitRef.revenue_stream_ids` |
| Acquisition / Sales | GTM retrieval | `EARLY_GTM`, `SCALED_GTM` |
| Delivery / Asset / Contract | operational comparison | `DELIVERY_MODEL`, `CONTRACT_RISK` |
| Economics / Cashflow | financial retrieval | `FINANCIAL_BENCHMARK`, `CASHFLOW` |
| Metric Definition / Series | benchmark comparability guard | claim trace + runtime benchmark service |
| Pivot / Failure / Restructuring | counterexample retrieval | corresponding retrieval objectives |
| Transferability / External Validity | comparison output seed | `ComparisonResult`, `TransferabilityAssessment` |
| Claim Ledger | atomic traceability | `ClaimTraceResult` |
| Evidence Ledger | support/contradiction graph | `EvidenceTraceItem` |
| Source Registry | provenance | `SourceId`, claim trace |
| Retrieval Profile | machine retrieval index | `SearchCasesRequest` target matching |
| Research Status / Refresh | freshness guard | `CaseDataQuality` + refresh service |
| Eligibility by Use | hard permission gate | `EligibilityFlags` |
| Agent-Derived Output | compact context material | `ContextCase` |

## Runtime-only metadata

The following belong to Runtime and must not become duplicated business facts inside the Company Case file:

```text
ingestion_id
revision_id
parser_version
source_file_ref
source_file_hash
record_content_hash
uploaded_at
uploaded_by
committed_at
committed_by
previous_revision_id
state_version
idempotency_key
```

## Key non-duplication rule

The Runtime may cache or index V1.4 facts, but the canonical business fact remains in its designated V1.4 source object. Search indexes, embeddings, comparison results and context packs are derived artifacts, not new fact sources.
