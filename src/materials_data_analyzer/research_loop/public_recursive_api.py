"""Supported public facade for recursive autonomous research composition.

Acceptance replays and downstream callers use this module instead of importing private
recursive checkpoint/progression helpers or constructing verified execution records.
Scientific authority remains separated from planning and execution throughout.
"""
from __future__ import annotations

from .action_registry import load_action_registry
from .authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from .authenticated_transition_consumer import authenticate_transition_bundle
from .autonomous_inquiry import build_autonomous_inquiry_plan
from .authorized_execution import execute_authorized_action
from .epistemic_graph import evaluate_epistemic_graph
from .heat_execution_verifier import verify_heat_execution_handoff
from .heat_transition_verification import (
    HEAT_TRANSITION_VERIFIER_ID,
    REFERENCE_HEAT_NUMERICAL_VALIDITY_TARGET,
    build_heat_transition_verification_decision,
    publish_heat_transition_verification_decision,
)
from .in625_execution_verifier import verify_in625_execution_handoff
from .kernel import initialize_research_loop, load_research_state
from .public_recursive_acceptance_boundary import (
    build_external_evidence_waiting_program_state,
    build_public_recursive_replay_manifest,
)
from .public_recursive_discrepancy import (
    build_public_recursive_discrepancy_report,
    validate_public_recursive_discrepancy_report,
)
from .public_recursive_external_evidence import (
    build_external_evidence_recursive_planner_program_state,
)
from .public_recursive_planning import (
    PublicRecursivePlanningError,
    build_heat_recursive_planner_program_state,
    build_public_candidate_match_record,
    build_public_recursive_discrepancy_planning_handoff,
    build_public_recursive_planning_checkpoint,
    validate_public_recursive_discrepancy_planning_handoff,
    validate_public_recursive_planning_checkpoint,
    validate_public_recursive_planning_context,
)
from .public_recursive_planning_context_boundary import (
    build_public_recursive_planning_context,
)
from .public_recursive_progression import (
    PublicRecursiveProgressionError,
    advance_public_recursive_cycle_after_verified_transition,
    complete_public_recursive_cycle_with_rediagnosis,
    validate_public_recursive_progression,
)
from .scientific_simulation_registry import repository_heat_conduction_contract

# Architecture vocabulary aliases point to the strongest public composition boundary.
build_model_evidence_discrepancy_report = build_public_recursive_discrepancy_report
validate_model_evidence_discrepancy_report = validate_public_recursive_discrepancy_report
build_discrepancy_planning_handoff = build_public_recursive_discrepancy_planning_handoff
validate_discrepancy_planning_handoff = validate_public_recursive_discrepancy_planning_handoff
build_validated_recursive_planning_checkpoint = build_public_recursive_planning_checkpoint
validate_validated_recursive_planning_checkpoint = validate_public_recursive_planning_checkpoint
advance_recursive_cycle_after_verified_transition = (
    advance_public_recursive_cycle_after_verified_transition
)
complete_recursive_cycle_with_rediagnosis = complete_public_recursive_cycle_with_rediagnosis

__all__ = [
    "HEAT_TRANSITION_VERIFIER_ID",
    "REFERENCE_HEAT_NUMERICAL_VALIDITY_TARGET",
    "PublicRecursivePlanningError",
    "PublicRecursiveProgressionError",
    "advance_public_recursive_cycle_after_verified_transition",
    "advance_recursive_cycle_after_verified_transition",
    "apply_authenticated_epistemic_transition_files",
    "authenticate_transition_bundle",
    "build_autonomous_inquiry_plan",
    "build_discrepancy_planning_handoff",
    "build_external_evidence_recursive_planner_program_state",
    "build_external_evidence_waiting_program_state",
    "build_heat_recursive_planner_program_state",
    "build_heat_transition_verification_decision",
    "build_model_evidence_discrepancy_report",
    "build_public_candidate_match_record",
    "build_public_recursive_discrepancy_planning_handoff",
    "build_public_recursive_discrepancy_report",
    "build_public_recursive_planning_checkpoint",
    "build_public_recursive_planning_context",
    "build_public_recursive_replay_manifest",
    "build_validated_recursive_planning_checkpoint",
    "complete_public_recursive_cycle_with_rediagnosis",
    "complete_recursive_cycle_with_rediagnosis",
    "evaluate_epistemic_graph",
    "execute_authorized_action",
    "initialize_research_loop",
    "load_action_registry",
    "load_research_state",
    "publish_heat_transition_verification_decision",
    "repository_heat_conduction_contract",
    "validate_discrepancy_planning_handoff",
    "validate_model_evidence_discrepancy_report",
    "validate_public_recursive_discrepancy_planning_handoff",
    "validate_public_recursive_discrepancy_report",
    "validate_public_recursive_planning_checkpoint",
    "validate_public_recursive_planning_context",
    "validate_public_recursive_progression",
    "validate_validated_recursive_planning_checkpoint",
    "verify_heat_execution_handoff",
    "verify_in625_execution_handoff",
]
