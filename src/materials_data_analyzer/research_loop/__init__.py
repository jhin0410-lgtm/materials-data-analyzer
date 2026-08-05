"""Deterministic contracts for bounded autonomous materials research loops.

The package deliberately contains no language model, unconstrained code
generation, model fitting, or automatic scientific conclusion logic yet. It
provides immutable state and a strict action registry on which later planner,
executor, and verifier components can safely depend.
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

__all__ = [
    "ACTION_REGISTRY_SCHEMA_VERSION",
    "LEDGER_FILENAME",
    "STATE_FILENAME",
    "ResearchLoopError",
    "action_summaries",
    "append_action",
    "append_evidence",
    "append_hypothesis",
    "append_stop",
    "describe_action",
    "initialize_research_loop",
    "load_action_registry",
    "load_research_state",
    "validate_action_registry",
    "verify_research_loop",
]
