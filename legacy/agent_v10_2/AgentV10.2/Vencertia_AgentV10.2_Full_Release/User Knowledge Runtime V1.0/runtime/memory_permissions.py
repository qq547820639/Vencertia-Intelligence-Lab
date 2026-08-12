from __future__ import annotations

from .models import AccessClass, AgentId


DEFAULT_AGENT_ACCESS = {
    AgentId.A0_ORCHESTRATOR: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A1_FOUNDER_DIAGNOSIS: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A2_MARKET_OPPORTUNITY: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A3_VENTURE_DESIGN: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A4_PROJECT_PROSECUTOR: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A5_FINANCIAL_BUSINESS_MODEL: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A6_EXECUTION_STRATEGY: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A7_NEXT_ACTION: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    # A8 receives only minimized internal query context. Raw private memory must not be exported to external tools.
    AgentId.A8_STARTUP_CASE_INTELLIGENCE: {AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
    # Matchmaking receives only permissioned signals.
    AgentId.A9_FOUNDER_MATCHMAKING: {AccessClass.MATCHABLE, AccessClass.PUBLIC},
    AgentId.A10_BUSINESS_PLAN: {AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC},
}
