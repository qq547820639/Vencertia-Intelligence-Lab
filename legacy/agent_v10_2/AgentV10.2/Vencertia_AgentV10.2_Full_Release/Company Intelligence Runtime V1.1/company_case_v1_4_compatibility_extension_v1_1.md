# Vencertia Startup Intelligence Company Case V1.4 — Compatibility Extension V1.1

**Status:** ADDITIVE COMPATIBILITY EXTENSION  
**Core schema remains:** Startup Intelligence Company Case V1.4  
**Purpose:** close AgentV9 → AgentV10 migration gaps without redefining the V1.4 single sources of truth.

## 1. FounderRecord extension

`FounderRecord` restores structured public founder/team case intelligence from V9. It is not user Founder Memory. Every material founder fact should remain traceable to Claim → Evidence → Source. Recommended fields: founder_id, company_id, name, education, previous_companies, previous_industries, previous_startups, technical_background, sales_background, industry_background, capital_background, special_resources, founder_market_fit_notes, claim_ids, last_verified_at.

## 2. FundingRound extension

`FundingRound` restores a first-class funding event identity: funding_round_id, company_id, round_name, announced_at, amount, currency, investors, lead_investors, pre_money_valuation, post_money_valuation, total_funding_after_round, claim_ids, source_ids, last_verified_at. Funding remains contextual evidence and MUST NOT be interpreted as proof of demand, healthy unit economics, or venture quality.

## 3. Source metadata extension

Optional Source metadata adds `language`, `publisher_country`, and `source_geography`. These describe the source itself and must not be confused with the business/evidence Scope.

## 4. Legacy → V1.4 / Runtime mapping

| V9 construct | V10.1 canonical interpretation |
|---|---|
| CompanyMaster | Company identity + Case Schema V1.4 registries/snapshots |
| FounderRecord | FounderRecord compatibility extension |
| FundingRound | FundingRound compatibility extension + FUNDING Event linkage |
| StartupCaseResult | CaseContextPack or GetCaseResult depending requested depth |
| CaseBenchmark | ComparisonResult or CompareCaseSetResult |
| COMPANY DEEP DIVE | retrieval_objective=COMPANY_DEEP_DIVE + get_case |
| COMPETITIVE CASE SET | retrieval_objective=COMPETITIVE_CASE_SET + compare_case_set |
| Direct WRITE/UPDATE by A8 | DEPRECATED; use propose_case_update / submit_evidence / ingest_case, then Mutation Engine |

## 5. Legacy company-status mapping

| V9 coarse status | V1.4 representation |
|---|---|
| ACTIVE | company_status=ACTIVE |
| GROWING | lifecycle_stage=GROWTH |
| PROFITABLE | case_role=DURABLE_PROFIT and/or outcome=DURABLE_PROFITABLE when supported |
| ACQUIRED | company_status=ACQUIRED |
| MERGED | company_status=MERGED |
| IPO | capital_stage=PUBLIC_MARKETS |
| PIVOTED | Pivot Event + case_role=PIVOT where relevant |
| DISTRESSED | lifecycle_stage=DISTRESS |
| CLOSED | company_status=CLOSED |
| UNKNOWN | corresponding V1.4 field remains UNKNOWN |

Do not translate a coarse V9 status into multiple stronger V1.4 facts unless evidence supports each field independently.
