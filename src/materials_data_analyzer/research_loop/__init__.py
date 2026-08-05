"""Deterministic research-state kernel for bounded autonomous research loops.

The package deliberately contains no planner, language model, model fitting, or
scientific conclusion logic yet. It provides the immutable state and evidence
contracts on which those later components can safely depend.
"""

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
    "LEDGER_FILENAME",
    "STATE_FILENAME",
    "ResearchLoopError",
    "append_action",
    "append_evidence",
    "append_hypothesis",
    "append_stop",
    "initialize_research_loop",
    "load_research_state",
    "verify_research_loop",
]
