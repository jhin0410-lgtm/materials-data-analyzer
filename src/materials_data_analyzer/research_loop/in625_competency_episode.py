"""IN625 competency-episode progression after verified spot-size sensitivity.

This module does not add a new planner or epistemic kernel.  It consumes the exact
authenticated bootstrap/planning iteration plus one independently verified local-analysis
result and projects the new information back into the existing ProviderState ->
research-agent planning path.

The scientific update is deliberately narrow: the mds2 source itself demonstrates that
spot diameter is a varying protocol variable across the target subset.  That observation
does not establish causality or cross-source equivalence; it sharpens the protocol evidence
requirement and prevents the planner from repeatedly designing the same within-source
sensitivity analysis without new protocol evidence.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .evidence_packet import canonical_sha256
from .evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    adapt_authenticated_planning_gaps,
)
from .evidence_provider_planning import build_provider_planner_program_state
from .in625_spot_size_sensitivity import ACTION_TYPE
from .research_agent import build_research_agent_iteration

EPISODE_PROGRESSION_SCHEMA_VERSION = "1.0"
EPISODE_PROGRESSION_POLICY_VERSION = "1.0"


class In625CompetencyEpisodeError(ValueError):
    """Raised when a successor benchmark state is not provenance-preserving."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625CompetencyEpisodeError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return value


def _authenticate_full_snapshot(
    value: Mapping[str, Any],
    *,
    trusted_sha256: str,
    self_hash_field: str,
    field: str,
) -> tuple[dict[str, Any], str]:
    trusted = _sha(trusted_sha256, f"trusted_{field}_sha256")
    snapshot = copy.deepcopy(dict(value))
    _require(
        canonical_sha256(snapshot) == trusted,
        f"{field} does not match external trust-root SHA-256",
    )
    unsigned = copy.deepcopy(snapshot)
    embedded = _sha(unsigned.pop(self_hash_field, None), f"{field}.{self_hash_field}")
    _require(
        canonical_sha256(unsigned) == embedded,
        f"{field} embedded self-hash mismatch",
    )
    return snapshot, embedded


def _base_program(question: str) -> dict[str, Any]:
    return {
        "mission": {
            "mission_id": "in625-autonomous-scientist-competency-benchmark-v1",
            "research_question": question,
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            },
        },
        "generated_goals": [],
    }


def _refine_protocol_gap(planning_state: Mapping[str, Any]) -> dict[str, Any]:
    state = copy.deepcopy(dict(planning_state))
    gaps = state.get("unresolved_evidence_gaps")
    _require(isinstance(gaps, list), "planning_state unresolved_evidence_gaps are missing")
    matched = 0
    for raw in gaps:
        if not isinstance(raw, dict):
            continue
        if raw.get("gap_id") != "in625-benchmark:protocol-spot-uncertainty":
            continue
        matched += 1
        raw["requirement"] = (
            "Acquire authoritative source evidence binding the exact spot-diameter "
            "definition/value, measurement geometry, acquisition protocol and measurement-error "
            "semantics between the NIST AM-Bench trace and the mds2 target experiment. "
            "The authenticated mds2 subset already proves spot diameter is a varying "
            "source-native protocol variable, so it may not be omitted or assumed transferable."
        )
        raw["action_class_hint"] = "external_evidence_search"
    _require(matched == 1, "protocol/spot planning gap must occur exactly once")
    state["scientific_status_changed"] = False
    state["direct_numerical_cross_source_validation_authorized"] = False
    state["directly_comparable_mds2_rows"] = 0
    state["issue_76_exact_target_cells_satisfied"] = 0
    return state


def _refine_hypotheses(
    portfolio: object,
    *,
    sensitivity_result_sha256: str,
) -> list[dict[str, Any]]:
    _require(isinstance(portfolio, list), "hypothesis portfolio is missing")
    refined = copy.deepcopy(portfolio)
    seen_protocol = 0
    seen_artifact = 0
    for item in refined:
        if not isinstance(item, dict):
            continue
        if item.get("hypothesis_id") == "H_protocol_comparability":
            seen_protocol += 1
            item["status"] = "unsupported_with_verified_spot_context_requirement"
            item["verified_positive"] = False
            item["blocking_observation"] = (
                "authenticated_mds2_spot_variable_present_protocol_mapping_still_unresolved"
            )
            item["diagnostic_result_sha256"] = sensitivity_result_sha256
        if item.get("hypothesis_id") == "H_artifact_or_lineage":
            seen_artifact += 1
            item["status"] = "active_methodological_alternative_with_verified_context_sensitivity"
            item["diagnostic_result_sha256"] = sensitivity_result_sha256
    _require(
        seen_protocol == 1 and seen_artifact == 1,
        "required benchmark hypotheses are missing",
    )
    return refined


def build_in625_post_sensitivity_reassessment(
    *,
    bootstrap: Mapping[str, Any],
    trusted_bootstrap_sha256: str,
    first_iteration: Mapping[str, Any],
    trusted_iteration_sha256: str,
    sensitivity_result: Mapping[str, Any],
    trusted_result_sha256: str,
) -> dict[str, Any]:
    """Re-plan from changed verified evidence without promoting comparability."""

    bootstrap_snapshot, bootstrap_embedded = _authenticate_full_snapshot(
        bootstrap,
        trusted_sha256=trusted_bootstrap_sha256,
        self_hash_field="bootstrap_sha256",
        field="bootstrap",
    )
    iteration_snapshot, iteration_embedded = _authenticate_full_snapshot(
        first_iteration,
        trusted_sha256=trusted_iteration_sha256,
        self_hash_field="iteration_sha256",
        field="iteration",
    )
    result_snapshot, result_embedded = _authenticate_full_snapshot(
        sensitivity_result,
        trusted_sha256=trusted_result_sha256,
        self_hash_field="result_sha256",
        field="result",
    )

    _require(
        iteration_snapshot.get("bootstrap_sha256") == bootstrap_embedded,
        "first iteration does not descend from the authenticated bootstrap",
    )
    plan = iteration_snapshot.get("plan")
    _require(isinstance(plan, Mapping), "first iteration plan is missing")
    selected = plan.get("selected_next_action")
    _require(isinstance(selected, Mapping), "first iteration selected action is missing")
    _require(
        selected.get("action_class") == "sensitivity_analysis",
        "first iteration did not select the sensitivity design",
    )
    _require(
        result_snapshot.get("action_type") == ACTION_TYPE,
        "verified result is not the IN625 spot-size sensitivity action",
    )
    analysis = result_snapshot.get("analysis")
    interpretation = result_snapshot.get("scientific_interpretation")
    boundary = result_snapshot.get("authority_boundary")
    _require(isinstance(analysis, Mapping), "spot-size analysis block is missing")
    _require(isinstance(interpretation, Mapping), "spot-size interpretation block is missing")
    _require(isinstance(boundary, Mapping), "spot-size authority boundary is missing")
    _require(
        analysis.get("row_count") == 18
        and analysis.get("physical_track_count") == 18
        and analysis.get("spot_level_count") == 7,
        "verified spot-size support signature drifted",
    )
    _require(
        interpretation.get("protocol_spot_context_can_be_ignored") is False
        and interpretation.get("protocol_equivalence_established") is False
        and interpretation.get("cross_source_numerical_validation_authorized") is False
        and interpretation.get("issue_76_exact_target_cells_satisfied") == 0,
        "spot-size result widened scientific authority",
    )
    _require(
        boundary.get("scientific_status_promoted") is False
        and boundary.get("causal_claim_created") is False
        and boundary.get("cross_source_authority_created") is False,
        "spot-size result authority boundary drifted",
    )

    planning_state = _refine_protocol_gap(
        bootstrap_snapshot.get("planning_state", {})
        if isinstance(bootstrap_snapshot.get("planning_state"), Mapping)
        else {}
    )
    provider = adapt_authenticated_planning_gaps(
        planning_state,
        trusted_state_sha256=canonical_sha256(planning_state),
    )
    provider_input = AuthenticatedProviderStateInput(
        state=provider,
        trusted_provider_state_sha256=provider["provider_state_sha256"],
    )
    question = str(bootstrap_snapshot.get("research_question"))
    program = build_provider_planner_program_state(
        _base_program(question),
        [provider_input],
    )
    next_plan = build_research_agent_iteration(
        program,
        previous_plan=plan,
        budget_units=8.0,
        minimum_utility=0.01,
        max_iterations=8,
    )

    result: dict[str, Any] = {
        "schema_version": EPISODE_PROGRESSION_SCHEMA_VERSION,
        "policy_version": EPISODE_PROGRESSION_POLICY_VERSION,
        "episode_stage": "verified_action_reassessment",
        "ancestry": {
            "bootstrap_sha256": bootstrap_embedded,
            "first_iteration_sha256": iteration_embedded,
            "verified_sensitivity_result_sha256": result_embedded,
            "provider_state_sha256": provider["provider_state_sha256"],
            "program_state_sha256": canonical_sha256(program),
        },
        "hypothesis_portfolio": _refine_hypotheses(
            bootstrap_snapshot.get("hypothesis_portfolio"),
            sensitivity_result_sha256=result_embedded,
        ),
        "updated_planning_state": planning_state,
        "next_plan": next_plan,
        "scientific_conclusion": {
            "bounded_statement": (
                "Authenticated within-mds2 evidence establishes that spot diameter is a "
                "varying protocol variable in the 195 W / 800 mm/s AMMT subset. This does "
                "not establish spot-size causality or cross-source protocol equivalence; "
                "direct NIST-vs-mds2 numerical validation remains unauthorized."
            ),
            "new_verified_information": True,
            "direct_numerical_cross_source_validation_authorized": False,
            "directly_comparable_mds2_rows": 0,
            "issue_76_exact_target_cells_satisfied": 0,
            "calibrated_power_relation_established": False,
            "protocol_equivalence_established": False,
            "hypothesis_truth_established": False,
        },
        "authority_boundary": {
            "new_empirical_measurements_created": False,
            "scientific_status_promoted": False,
            "automatic_execution_authorized": False,
            "physical_experiment_executed": False,
            "simulation_treated_as_empirical": False,
        },
    }
    result["reassessment_sha256"] = canonical_sha256(result)
    return result


__all__ = [
    "EPISODE_PROGRESSION_POLICY_VERSION",
    "EPISODE_PROGRESSION_SCHEMA_VERSION",
    "In625CompetencyEpisodeError",
    "build_in625_post_sensitivity_reassessment",
]
