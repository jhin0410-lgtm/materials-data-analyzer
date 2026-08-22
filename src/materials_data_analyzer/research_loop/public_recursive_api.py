"""Supported public facade for recursive autonomous research composition.

This module deliberately re-exports only production trust-boundary functions. Acceptance
replays and downstream callers must use this facade rather than importing private
``_build_recursive_*`` / ``_advance_recursive_*`` helpers or constructing verified
execution records themselves.

The facade does not create scientific authority. Planning remains deterministic and
non-executing; execution still requires the existing typed authorization chain; graph
transitions remain authenticated diagnostic transitions; and re-diagnosis must rebuild
from exact predecessor provenance.
"""
from __future__ import annotations

from .authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from .authenticated_transition_consumer import authenticate_transition_bundle
from .autonomous_inquiry import build_autonomous_inquiry_plan
from .authorized_execution import execute_authorized_action
from .discrepancy_planning_handoff_policy import (
    build_policy_hardened_discrepancy_planning_handoff,
    validate_policy_hardened_discrepancy_planning_handoff,
)
from .epistemic_graph import evaluate_epistemic_graph
from .heat_execution_verifier import verify_heat_execution_handoff
from .model_evidence_discrepancy_physics_policy import (
    build_physics_hardened_model_evidence_discrepancy_report,
    validate_physics_hardened_model_evidence_discrepancy_report,
)
from .recursive_research_cycle_evidence import (
    advance_recursive_cycle_after_verified_transition,
)
from .recursive_research_cycle_rediagnosis import (
    complete_recursive_cycle_with_rediagnosis,
)
from .validated_recursive_cycle_planning import (
    build_validated_recursive_planning_checkpoint,
    validate_validated_recursive_planning_checkpoint,
)

# Stable public aliases use the architecture vocabulary rather than implementation-module
# names. These aliases intentionally point to the strongest installed policy boundary.
build_model_evidence_discrepancy_report = (
    build_physics_hardened_model_evidence_discrepancy_report
)
validate_model_evidence_discrepancy_report = (
    validate_physics_hardened_model_evidence_discrepancy_report
)
build_discrepancy_planning_handoff = (
    build_policy_hardened_discrepancy_planning_handoff
)
validate_discrepancy_planning_handoff = (
    validate_policy_hardened_discrepancy_planning_handoff
)

__all__ = [
    "advance_recursive_cycle_after_verified_transition",
    "apply_authenticated_epistemic_transition_files",
    "authenticate_transition_bundle",
    "build_autonomous_inquiry_plan",
    "build_discrepancy_planning_handoff",
    "build_model_evidence_discrepancy_report",
    "build_validated_recursive_planning_checkpoint",
    "complete_recursive_cycle_with_rediagnosis",
    "evaluate_epistemic_graph",
    "execute_authorized_action",
    "validate_discrepancy_planning_handoff",
    "validate_model_evidence_discrepancy_report",
    "validate_validated_recursive_planning_checkpoint",
    "verify_heat_execution_handoff",
]
