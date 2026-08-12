# Addendum for `Vencertia Financial & Business Model.docx`

## AGENTV10.2 FINANCIAL SNAPSHOT / MEMORY CONSISTENCY

**Version scope:** AgentV10.2 additive consistency patch / Vencertia User Knowledge Runtime V1.0.

### CURRENT FINANCIAL TRUTH OWNER

Versioned `FinancialSnapshot` is the canonical owner of current/point-in-time financial metrics such as:

- current price / average price / ACV
- CAC
- gross margin / contribution margin
- conversion rate
- sales cycle / payment period
- retention / churn / repurchase
- fixed/variable cost
- inventory / working capital
- break-even

Every meaningful change creates a new Financial Snapshot version according to existing A5 rules.

### FINANCIAL MEMORY IS DURABLE CONTEXT, NOT A COMPETING SNAPSHOT

A5 may still propose `FINANCIAL_DATA`, `LESSON`, `RISK`, `MILESTONE`, `PROJECT_DECISION` or other valid MemoryCandidates when the information is durable and decision-relevant. However Memory must not become a second current-metric table.

Examples:

- `Current CAC = CNY 800` → Financial Snapshot.
- `Three valid paid-acquisition tests kept CAC above the project’s viable gross-profit threshold` → possible durable LESSON/RISK/FINANCIAL_DATA Memory with Evidence/Snapshot provenance.
- `Three paid pilots establish a durable pricing/payment decision` → Financial Snapshot for the current price plus optional durable PROJECT_DECISION/FINANCIAL_DATA Memory if future reasoning needs the decision history.

### CONFLICT PRECEDENCE

If durable Financial Memory and the latest valid Financial Snapshot differ on a current metric, the latest evidence-backed Financial Snapshot is the current metric source. Memory may explain historical context, decisions or lessons and should be SUPERSEDED/CONFLICTED if it claims incompatible current truth.

### CONTEXT BUILDER

A5 ContextBundle should retrieve:

- latest Financial Snapshot separately;
- relevant durable Founder constraints (capital, max loss, available time, income needs);
- relevant project decisions/risks/lessons;
- critical Assumptions and Evidence.

Do not infer current CAC/margin/price solely from old Memory when a newer Financial Snapshot exists.
