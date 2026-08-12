# Vencertia Company Intelligence Runtime V1.1

V1.1 is the compatibility release that closes the remaining AgentV9 → AgentV10 Company Intelligence migration gaps while preserving Startup Intelligence Company Case Schema V1.4 as the canonical core fact schema.

## V1.1 additions

- Restores structured public `FounderRecord` case intelligence.
- Restores structured `FundingRound` records without treating funding as demand evidence.
- Adds `COMPANY_DEEP_DIVE`, `COMPETITIVE_CASE_SET`, and `FOUNDER_MARKET_FIT` retrieval objectives.
- Adds `get_case` and `compare_case_set` boundaries.
- Adds incremental research update boundaries: `propose_case_update`, `refresh_case`, `submit_evidence`.
- Adds an admin/review `resolve_case_conflict` boundary.
- Adds optional source-language and source-geography metadata.
- Keeps direct canonical database mutation outside reasoning-Agent authority.

## Canonical hierarchy

1. Startup Intelligence Company Case Schema V1.4 — core company-case facts and derived intelligence.
2. Company Case V1.4 Compatibility Extension V1.1 — additive Founder/Funding/Source compatibility objects and legacy mappings.
3. Company Intelligence Runtime V1.1 — ingestion, retrieval, comparison, deep dive, incremental update, eligibility, and traceability boundaries.

## Run

```bash
python generate_json_schema.py
pytest -q
```
