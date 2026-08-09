"""Deterministic contracts for bounded autonomous materials research loops.

The package deliberately contains no language model, unconstrained code
generation, model fitting, or automatic scientific conclusion logic. It provides
immutable state, strict action registries, typed deterministic action execution,
and deterministic planning, transition, authorization, and execution gates.
"""

from .action_authorization import (
    AUTHORIZATION_POLICY_VERSION,
    AUTHORIZATION_SCHEMA_VERSION,
    ActionAuthorizationError,
    assess_action_authorization,
    assess_current_action_authorization,
)
from .action_registry import (
    ACTION_REGISTRY_SCHEMA_VERSION,
    action_summaries,
    describe_action,
    load_action_registry,
    validate_action_registry,
)
from .authorized_execution import (
    EXECUTION_POLICY_VERSION,
    EXECUTION_SCHEMA_VERSION,
    AuthorizedExecutionError,
    execute_authorized_action,
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
from .planning_adapter import (
    PLANNING_ADAPTER_VERSION,
    PLANNING_DECISION_SCHEMA_VERSION,
    PlanningAdapterError,
    available_planning_adapters,
    plan_research_next_action,
)
from .planning_state import (
    PLANNING_STATE_SCHEMA_VERSION,
    PLANNING_STATE_VERSION,
    PlanningStateError,
    build_research_planning_state,
)
from .planning_transition import (
    TRANSITION_POLICY_VERSION,
    TRANSITION_SCHEMA_VERSION,
    PlanningTransitionError,
    build_current_research_transition,
    build_reopen_evidence_review,
    determine_research_transition,
    prepare_reopen_evidence_review,
)
from .protocol_stratification import build_protocol_stratification
from .target_reference_sensitivity import (
    TargetReferenceSensitivityError,
    build_target_reference_sensitivity,
)

__all__ = [
    "ACTION_REGISTRY_SCHEMA_VERSION",
    "ACTION_REPORT_FILENAME",
    "AUTHORIZATION_POLICY_VERSION",
    "AUTHORIZATION_SCHEMA_VERSION",
    "EXECUTION_POLICY_VERSION",
    "EXECUTION_SCHEMA_VERSION",
    "LEDGER_FILENAME",
    "PLANNING_ADAPTER_VERSION",
    "PLANNING_DECISION_SCHEMA_VERSION",
    "PLANNING_STATE_SCHEMA_VERSION",
    "PLANNING_STATE_VERSION",
    "STATE_FILENAME",
    "TRANSITION_POLICY_VERSION",
    "TRANSITION_SCHEMA_VERSION",
    "ActionAuthorizationError",
    "AuthorizedExecutionError",
    "NasaActionPolicyError",
    "NasaAuditActionError",
    "NasaProtocolStratificationActionError",
    "NasaTargetReferenceActionError",
    "PlanningAdapterError",
    "PlanningStateError",
    "PlanningTransitionError",
    "ResearchLoopError",
    "TargetReferenceSensitivityError",
    "action_summaries",
    "append_action",
    "append_evidence",
    "append_hypothesis",
    "append_stop",
    "assess_action_authorization",
    "assess_current_action_authorization",
    "available_planning_adapters",
    "build_current_research_transition",
    "build_protocol_stratification",
    "build_reopen_evidence_review",
    "build_research_planning_state",
    "build_target_reference_sensitivity",
    "describe_action",
    "determine_research_transition",
    "execute_authorized_action",
    "execute_nasa_audit_action",
    "execute_nasa_protocol_stratification_action",
    "execute_nasa_target_reference_action",
    "initialize_research_loop",
    "load_action_registry",
    "load_research_state",
    "plan_nasa_next_action",
    "plan_research_next_action",
    "prepare_reopen_evidence_review",
    "validate_action_registry",
    "verify_nasa_audit_action_report",
    "verify_nasa_protocol_stratification_report",
    "verify_nasa_target_reference_report",
    "verify_research_loop",
]
