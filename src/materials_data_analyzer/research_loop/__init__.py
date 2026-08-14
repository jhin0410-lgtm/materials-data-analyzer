"""Deterministic contracts for bounded autonomous materials research loops.

The package deliberately contains no unconstrained code generation or automatic
scientific truth promotion. It provides immutable state, strict action registries,
typed deterministic execution, domain planning gates, a mission-level control plane,
and a provenance-aware epistemic graph that keeps support, contradiction, and
falsification explicit. Domain-specific scientific reasoning proposals remain
schema-validated, evidence-bound planning inputs until a separate authorized action
executes them.
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
from .epistemic_graph import (
    GRAPH_POLICY_VERSION,
    GRAPH_SCHEMA_VERSION,
    EpistemicGraphError,
    evaluate_epistemic_graph,
    validate_epistemic_graph,
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
from .research_cycle import (
    CYCLE_POLICY_VERSION,
    CYCLE_SCHEMA_VERSION,
    ResearchCycleError,
    run_research_cycle,
)
from .research_program import (
    MISSION_SCHEMA_VERSION,
    PROGRAM_POLICY_VERSION,
    PROGRAM_SCHEMA_VERSION,
    REASONING_PROPOSAL_SCHEMA_VERSION,
    ResearchProgramError,
    build_research_program,
    validate_reasoning_proposal,
    validate_reasoning_proposal_file,
    validate_research_mission,
)
from .target_reference_sensitivity import (
    TargetReferenceSensitivityError,
    build_target_reference_sensitivity,
)

__all__ = [
    "ACTION_REGISTRY_SCHEMA_VERSION",
    "ACTION_REPORT_FILENAME",
    "AUTHORIZATION_POLICY_VERSION",
    "AUTHORIZATION_SCHEMA_VERSION",
    "CYCLE_POLICY_VERSION",
    "CYCLE_SCHEMA_VERSION",
    "EXECUTION_POLICY_VERSION",
    "EXECUTION_SCHEMA_VERSION",
    "GRAPH_POLICY_VERSION",
    "GRAPH_SCHEMA_VERSION",
    "LEDGER_FILENAME",
    "MISSION_SCHEMA_VERSION",
    "PLANNING_ADAPTER_VERSION",
    "PLANNING_DECISION_SCHEMA_VERSION",
    "PLANNING_STATE_SCHEMA_VERSION",
    "PLANNING_STATE_VERSION",
    "PROGRAM_POLICY_VERSION",
    "PROGRAM_SCHEMA_VERSION",
    "REASONING_PROPOSAL_SCHEMA_VERSION",
    "STATE_FILENAME",
    "TRANSITION_POLICY_VERSION",
    "TRANSITION_SCHEMA_VERSION",
    "ActionAuthorizationError",
    "AuthorizedExecutionError",
    "EpistemicGraphError",
    "NasaActionPolicyError",
    "NasaAuditActionError",
    "NasaProtocolStratificationActionError",
    "NasaTargetReferenceActionError",
    "PlanningAdapterError",
    "PlanningStateError",
    "PlanningTransitionError",
    "ResearchCycleError",
    "ResearchLoopError",
    "ResearchProgramError",
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
    "build_research_program",
    "build_target_reference_sensitivity",
    "describe_action",
    "determine_research_transition",
    "evaluate_epistemic_graph",
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
    "run_research_cycle",
    "validate_action_registry",
    "validate_epistemic_graph",
    "validate_reasoning_proposal",
    "validate_reasoning_proposal_file",
    "validate_research_mission",
    "verify_nasa_audit_action_report",
    "verify_nasa_protocol_stratification_report",
    "verify_nasa_target_reference_report",
    "verify_research_loop",
]
