"""Deterministic contracts for bounded autonomous materials research loops.

The package deliberately contains no language model, unconstrained code
generation, model fitting, or automatic scientific conclusion logic yet. It
provides immutable state, a strict action registry, and typed deterministic
action execution on which later planner components can safely depend.
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
    "validate_action_registry",
    "verify_nasa_audit_action_report",
    "verify_research_loop",
]
