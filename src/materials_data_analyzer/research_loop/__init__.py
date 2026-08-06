"""Deterministic contracts for bounded autonomous materials research loops.

The package deliberately contains no language model, unconstrained code
generation, model fitting, or automatic scientific conclusion logic yet. It
provides immutable state, strict action registries, typed deterministic action
execution, and a deterministic next-action baseline for planner comparison.
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
from .nasa_action_policy import NasaActionPolicyError, plan_nasa_next_action
from .nasa_audit_executor import (
    ACTION_REPORT_FILENAME,
    NasaAuditActionError,
    execute_nasa_audit_action,
    verify_nasa_audit_action_report,
)
from .nasa_protocol_stratification_action import (
    NasaProtocolStratificationActionError,
    execute_nasa_protocol_stratification_action,
    verify_nasa_protocol_stratification_report,
)
from .nasa_target_reference_action import (
    NasaTargetReferenceActionError,
    execute_nasa_target_reference_action,
    verify_nasa_target_reference_report,
)
from .protocol_stratification import build_protocol_stratification
from .target_reference_sensitivity import (
    TargetReferenceSensitivityError,
    build_target_reference_sensitivity,
)

__all__ = [
    "ACTION_REGISTRY_SCHEMA_VERSION",
    "ACTION_REPORT_FILENAME",
    "LEDGER_FILENAME",
    "STATE_FILENAME",
    "NasaActionPolicyError",
    "NasaAuditActionError",
    "NasaProtocolStratificationActionError",
    "NasaTargetReferenceActionError",
    "ResearchLoopError",
    "TargetReferenceSensitivityError",
    "action_summaries",
    "append_action",
    "append_evidence",
    "append_hypothesis",
    "append_stop",
    "build_protocol_stratification",
    "build_target_reference_sensitivity",
    "describe_action",
    "execute_nasa_audit_action",
    "execute_nasa_protocol_stratification_action",
    "execute_nasa_target_reference_action",
    "initialize_research_loop",
    "load_action_registry",
    "load_research_state",
    "plan_nasa_next_action",
    "validate_action_registry",
    "verify_nasa_audit_action_report",
    "verify_nasa_protocol_stratification_report",
    "verify_nasa_target_reference_report",
    "verify_research_loop",
]
