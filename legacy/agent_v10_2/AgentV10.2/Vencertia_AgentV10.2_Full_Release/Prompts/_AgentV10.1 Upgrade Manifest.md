# AgentV10.1 Compatibility Upgrade Manifest

## Purpose

Close the remaining V9 → V10 Company Intelligence migration gaps without deleting V9 prompt content or altering Startup Intelligence Company Case Schema V1.4.

## Changes applied to all 15 prompts

- Version 2.0 → 2.1.
- Runtime Contract V1.0 → V1.1 references.
- Added additive Compatibility Extension V1.1.
- Added explicit legacy mapping.
- Restored Company Deep Dive, Competitive Case Set, Founder-Market-Fit retrieval modes.
- Added incremental research update/refresh/evidence-submission path.
- Explicitly deprecated direct reasoning-Agent database mutation while preserving update capability through Mutation Engine.
- Added legacy status mapping to V1.4 fields.

## Targeted changes

- A8: FounderRecord, FundingRound, Deep Dive, Competitive Case Set, incremental updates, direct-write deprecation.
- Pydantic: compatibility models and new API contracts.
- Router/A0: new case modes and refresh/update intents.
- A1: FOUNDER_MARKET_FIT use.
- A4: case-set challenge.
- A5: FundingRound context boundary.
- A10: deep-dive/case-set BP calibration.

## Non-changes

- No V9 body section was deleted.
- Startup Intelligence Company Case Schema V1.4 remains the canonical core case schema.
- External Case Evidence still cannot upgrade Project Evidence or satisfy project Stage Gates.

## Validation

- V9 preservation audit: 15/15 documents, 0 canonical OOXML mismatches before the Company Intelligence integration appendix after normalizing Version 2.1 → Version 1.0.
- Runtime V1.1: 24 generated JSON Schemas; 11 deterministic tests passed.
- DOCX rendering: 15/15 documents rendered successfully; 2,646 pages total.
- New/modified integration pages visually reviewed; no clipping or overlap observed.
