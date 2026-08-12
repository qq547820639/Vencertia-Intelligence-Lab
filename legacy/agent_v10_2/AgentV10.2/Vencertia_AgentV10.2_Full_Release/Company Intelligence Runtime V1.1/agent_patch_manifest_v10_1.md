# AgentV10.1 Company Intelligence Compatibility Patch Manifest

## Global

- Runtime Contract V1.1.
- Core Company Case Schema remains V1.4.
- Add Compatibility Extension V1.1.
- Preserve V9 body rules unless explicitly deprecated below.
- Restore `FounderRecord`, `FundingRound`, `COMPANY_DEEP_DIVE`, `COMPETITIVE_CASE_SET`, and `FOUNDER_MARKET_FIT`.
- Add incremental update paths: `propose_case_update`, `submit_evidence`, `refresh_case`.
- `resolve_case_conflict` is review/admin governed.
- Direct reasoning-Agent canonical mutation is deprecated.

## A8

V9 Founder/Team and Funding capabilities remain active through compatibility models. V9 direct database-write authority is reinterpreted as PROPOSE through Runtime; Mutation Engine owns commit.

## Pydantic

Add FounderRecord, FundingRound, SourceMetadataExtension, GetCase, CompareCaseSet, ProposeCaseUpdate, RefreshCase, SubmitEvidence, and ResolveCaseConflict schemas. Generate JSON Schema from Pydantic.

## Router / A0

Recognize explicit deep-dive, case-set, founder-market-fit, refresh, and incremental-update intents.

## A1 / A4 / A5 / A10

Add role-appropriate compatibility rules without changing their primary decision ownership.
