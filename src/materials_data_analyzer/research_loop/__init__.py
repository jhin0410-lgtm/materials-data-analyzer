"""Deterministic contracts for bounded autonomous materials research loops.

The package deliberately contains no language model, unconstrained code
generation, model fitting, or automatic scientific conclusion logic yet. It
provides immutable state, a strict action registry, typed deterministic action
execution, and a deterministic next-action baseline for later planner comparison.
"""

from .action_registry import (
    ACTION_REGISTRY_SCHEMA_VERSION,
    action_summaries,
    describe_action,
    load_action_registry,
    validate_action_registry,
)
from .kernel import (
    LEDGER_FILENAME,
    STATE_FILENAME,
    ResearchLoopError,
    append_action,
    append_evidence,
    append_hypothesis,
    append_stop,
    initialize_research_loop,
    load_research_state,
    verify_research_loop,
)
from .nasa_action_policy import (
    NasaActionPolicyError,
    plan_nasa_next_action,
)
from .nasa_audit_executor import (
    ACTION_REPORT_FILENAME,
    NasaAuditActionError,
    execute_nasa_audit_action,
    verify_nasa_audit_action_report,
)

__all__ = [
    "ACTION_REGISTRY_SCHEMA_VERSION",
    "ACTION_REPORT_FILENAME",
    "LEDGER_FILENAME",
    "STATE_FILENAME",
    "NasaActionPolicyError",
    "NasaAuditActionError",
    "ResearchLoopError",
    "action_summaries",
    "append_action",
    "append_evidence",
    "append_hypothesis",
    "append_stop",
    "describe_action",
    "execute_nasa_audit_action",
    "initialize_research_loop",
    "load_action_registry",
    "load_research_state",
    "plan_nasa_next_action",
    "validate_action_registry",
    "verify_nasa_audit_action_report",
    "verify_research_loop",
]
