"""First real-evidence IN625 Autonomous Research Scientist competency episode.

This domain composer connects already-merged generic components.  It is not a new epistemic
kernel, planner, executor, or provider framework.

Inputs are externally authenticated NIST AM-Bench and mds2-2923 EvidencePackets plus an
externally pinned mds2 bridge/mapping state.  The composer:

1. revalidates both authority-bearing packets through their external expectation roots;
2. runs the generic Comparability Engine under one externally trusted direct-comparison claim;
3. reconstructs a competing hypothesis portfolio from authenticated bridge/gate booleans;
4. converts unresolved bridge requirements into the existing planning-only ProviderState;
5. invokes the existing self-directed research planner without preselecting a cycle sequence;
6. records a bounded conclusion that direct numerical comparison remains unauthorized until
   new verified evidence changes the state.

No action is executed here.  Any selected action must pass the existing independent
authorization/executor boundary in a successor step.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .comparability_engine import (
    AuthenticatedEvidenceInput,
    assess_comparability,
)
from .evidence_packet import canonical_sha256
from .evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    adapt_authenticated_planning_gaps,
)
from .evidence_provider_planning import build_provider_planner_program_state
from .research_agent import build_research_agent_iteration

BENCHMARK_SCHEMA_VERSION = "1.0"
BENCHMARK_POLICY_VERSION = "1.0"


class In625CompetencyBenchmarkError(ValueError):
    """Raised when benchmark state cannot be derived without widening authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625CompetencyBenchmarkError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return value


def _validate_self_hash(value: Mapping[str, Any], field: str) -> str:
    digest = _sha(value.get(field), field)
    unsigned = copy.deepcopy(dict(value))
    unsigned.pop(field, None)
    _require(canonical_sha256(unsigned) == digest, f"{field} is invalid")
    return digest


def _authenticate_bridge_state(
    bridge_state: Mapping[str, Any],
    *,
    trusted_bridge_state_sha256: str,
) -> dict[str, Any]:
    trusted = _sha(trusted_bridge_state_sha256, "trusted_bridge_state_sha256")
    snapshot = copy.deepcopy(dict(bridge_state))
    _require(
        canonical_sha256(snapshot) == trusted,
        "mds2 bridge state does not match external trust-root SHA-256",
    )
    if "report_sha256_without_self_field" in snapshot:
        _validate_self_hash(snapshot, "report_sha256_without_self_field")

    decision = snapshot.get("gate_decision")
    if decision is None:
        decision = snapshot.get("calibration_and_protocol_gate")
    _require(isinstance(decision, Mapping), "mds2 bridge gate decision is missing")

    required_false = (
        "direct_numerical_cross_source_validation_authorized",
        "cross_machine_pooling_authorized",
    )
    # Historical geometry mapping uses the shorter direct_numerical_validation_authorized key.
    direct = decision.get("direct_numerical_cross_source_validation_authorized")
    if direct is None:
        direct = decision.get("direct_numerical_validation_authorized")
    _require(direct is False, "mds2 bridge already authorizes direct numerical validation")
    _require(
        decision.get("directly_comparable_mds2_rows") == 0,
        "mds2 bridge already contains directly comparable rows",
    )
    _require(
        decision.get("issue_76_exact_target_cells_satisfied") == 0,
        "mds2 bridge already promotes Issue #76 target cells",
    )
    _require(
        decision.get("cross_machine_pooling_authorized") is False,
        "mds2 bridge already authorizes cross-machine pooling",
    )
    return snapshot


def _hypothesis_portfolio(bridge: Mapping[str, Any]) -> list[dict[str, Any]]:
    identity = bridge.get("experiment_identity")
    gate = bridge.get("calibration_and_protocol_gate")
    decision = bridge.get("gate_decision")
    if not isinstance(identity, Mapping):
        identity = {}
    if not isinstance(gate, Mapping):
        gate = decision if isinstance(decision, Mapping) else {}
    if not isinstance(decision, Mapping):
        decision = gate

    exact_identity = identity.get("exact_mds2_experiment_identity_established")
    if exact_identity is None:
        exact_identity = decision.get("exact_mds2_experiment_identity_established")
    calibration = gate.get("machine_setting_to_calibrated_power_relation_established")
    if calibration is None:
        calibration = decision.get("calibrated_actual_power_mapping_established")
    protocol = gate.get("protocol_equivalence_established")
    if protocol is None:
        protocol = decision.get("protocol_equivalence_established")
    spot = gate.get("spot_size_transfer_authorized")
    if spot is None:
        spot = decision.get("spot_size_mapping_established")

    for name, value in (
        ("exact experiment identity", exact_identity),
        ("calibrated-power bridge", calibration),
        ("protocol equivalence", protocol),
        ("spot-size bridge", spot),
    ):
        _require(value in {False, None}, f"{name} unexpectedly became established")

    return [
        {
            "hypothesis_id": "H_identity_bridge",
            "statement": (
                "The mds2 AMMT 195 W / 800 mm/s subset is explicitly bound to the "
                "same experiment/protocol context required by the declared comparison."
            ),
            "status": "unsupported_or_unresolved",
            "verified_positive": False,
            "blocking_observation": "exact_mds2_experiment_identity_established=false_or_unknown",
        },
        {
            "hypothesis_id": "H_calibration_transfer",
            "statement": (
                "An experiment-scoped machine-setting to calibrated physical-power relation "
                "exists and is transferable for the exact mds2 target experiment."
            ),
            "status": "unsupported_or_unresolved",
            "verified_positive": False,
            "blocking_observation": (
                "exact_machine_setting_to_calibrated_power_relation_established=false_or_unknown"
            ),
        },
        {
            "hypothesis_id": "H_protocol_comparability",
            "statement": (
                "Measurement geometry, spot-size semantics, protocol and response semantics "
                "are sufficiently matched or explicitly transformable."
            ),
            "status": "unsupported_or_unresolved",
            "verified_positive": False,
            "blocking_observation": "protocol_or_spot_size_equivalence=false_or_unknown",
        },
        {
            "hypothesis_id": "H_null_scope",
            "statement": (
                "Current evidence supports provenance/descriptive association only; direct "
                "quantitative cross-source validation remains unauthorized."
            ),
            "status": "currently_supported_bounded_state",
            "verified_positive": True,
            "blocking_observation": None,
        },
        {
            "hypothesis_id": "H_artifact_or_lineage",
            "statement": (
                "Apparent agreement can be explained by shared lineage, quantity aliasing, "
                "missing calibration, response granularity, or context loss rather than "
                "independent scientific support."
            ),
            "status": "active_methodological_alternative",
            "verified_positive": False,
            "blocking_observation": None,
        },
    ]


def _bridge_planning_state(bridge: Mapping[str, Any]) -> dict[str, Any]:
    identity = bridge.get("experiment_identity")
    gate = bridge.get("calibration_and_protocol_gate")
    decision = bridge.get("gate_decision")
    if not isinstance(identity, Mapping):
        identity = {}
    if not isinstance(gate, Mapping):
        gate = decision if isinstance(decision, Mapping) else {}
    if not isinstance(decision, Mapping):
        decision = gate

    gaps: list[dict[str, Any]] = []

    if identity.get("exact_mds2_experiment_identity_established") is not True:
        gaps.append(
            {
                "gap_id": "in625-benchmark:exact-experiment-identity",
                "requirement": (
                    "Acquire authoritative source evidence that can establish or falsify the "
                    "exact mds2-2923 AMMT row-to-experiment identity, including the Weaver/Naderi "
                    "reference chain; dataset-publication association alone is insufficient."
                ),
                "action_class_hint": "external_evidence_search",
            }
        )

    calibration = gate.get("machine_setting_to_calibrated_power_relation_established")
    if calibration is None:
        calibration = decision.get("calibrated_actual_power_mapping_established")
    if calibration is not True:
        gaps.append(
            {
                "gap_id": "in625-benchmark:calibrated-power-bridge",
                "requirement": (
                    "Acquire experiment-specific calibration evidence mapping the mds2 AMMT "
                    "180/195 W machine settings to achieved calibrated physical laser power; "
                    "do not substitute the AMB2018 corrected 137.9/179.2 W values across experiments."
                ),
                "action_class_hint": "external_evidence_search",
            }
        )

    protocol = gate.get("protocol_equivalence_established")
    if protocol is None:
        protocol = decision.get("protocol_equivalence_established")
    spot = gate.get("spot_size_transfer_authorized")
    if spot is None:
        spot = decision.get("spot_size_mapping_established")
    if protocol is not True or spot is not True:
        gaps.append(
            {
                "gap_id": "in625-benchmark:protocol-spot-uncertainty",
                "requirement": (
                    "Acquire authoritative measurement protocol, spot-size definition/value, "
                    "calibration, uncertainty, sample-preparation and acquisition context needed "
                    "to discriminate protocol equivalence from context aliasing."
                ),
                "action_class_hint": "external_evidence_search",
            }
        )

    gaps.append(
        {
            "gap_id": "in625-benchmark:nist-official-trace-provenance",
            "requirement": (
                "Acquire and byte-bind the official NIST AM-Bench 2018-02 high-resolution "
                "cross-section source assets/metadata (mds2-3830) to test whether the current "
                "reviewed trace transcription can be upgraded in provenance authority without "
                "changing its scientific scope."
            ),
            "action_class_hint": "external_evidence_search",
        }
    )

    return {
        "schema_version": "1.0",
        "state_type": "in625_competency_unresolved_evidence",
        "unresolved_evidence_gaps": gaps,
        "scientific_status_changed": False,
        "direct_numerical_cross_source_validation_authorized": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
    }


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


def build_in625_competency_bootstrap(
    *,
    nist_evidence: AuthenticatedEvidenceInput,
    mds2_evidence: AuthenticatedEvidenceInput,
    bridge_state: Mapping[str, Any],
    trusted_bridge_state_sha256: str,
    direct_comparison_claim: Mapping[str, Any],
    trusted_claim_scope_sha256: str,
) -> dict[str, Any]:
    """Build authenticated initial scientific state without creating an executable action."""

    bridge = _authenticate_bridge_state(
        bridge_state,
        trusted_bridge_state_sha256=trusted_bridge_state_sha256,
    )
    claim_trusted = _sha(
        trusted_claim_scope_sha256,
        "trusted_claim_scope_sha256",
    )
    _require(
        canonical_sha256(direct_comparison_claim) == claim_trusted,
        "direct comparison claim does not match external trust-root SHA-256",
    )

    assessment = assess_comparability(
        nist_evidence,
        mds2_evidence,
        claim_scope=direct_comparison_claim,
        trusted_claim_scope_sha256=claim_trusted,
    )
    portfolio = _hypothesis_portfolio(bridge)
    planning_state = _bridge_planning_state(bridge)

    result: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "policy_version": BENCHMARK_POLICY_VERSION,
        "episode_stage": "authenticated_initial_state",
        "research_question": (
            "Under what evidence conditions can NIST AM-Bench IN625 observations and "
            "mds2-2923/Weaver/Naderi evidence support direct quantitative comparison, "
            "and what is the highest-information next action while those conditions are unmet?"
        ),
        "input_bindings": {
            "nist_packet_sha256": nist_evidence.packet.get("packet_sha256"),
            "mds2_packet_sha256": mds2_evidence.packet.get("packet_sha256"),
            "bridge_state_sha256": trusted_bridge_state_sha256,
            "direct_comparison_claim_sha256": claim_trusted,
        },
        "hypothesis_portfolio": portfolio,
        "comparability_assessment": assessment,
        "planning_state": planning_state,
        "scientific_boundary": {
            "exact_mds2_experiment_identity_established": False,
            "exact_machine_setting_to_calibrated_power_relation_established": False,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "scientific_status_changed": False,
        },
        "authority_boundary": {
            "action_authorized": False,
            "execution_performed": False,
            "physical_experiment_executed": False,
            "simulation_treated_as_empirical": False,
        },
    }
    result["bootstrap_sha256"] = canonical_sha256(result)
    return result


def build_in625_competency_iteration(
    bootstrap: Mapping[str, Any],
    *,
    trusted_bootstrap_sha256: str,
    previous_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn one externally pinned bootstrap into a self-directed planning iteration."""

    trusted = _sha(trusted_bootstrap_sha256, "trusted_bootstrap_sha256")
    snapshot = copy.deepcopy(dict(bootstrap))
    _require(
        canonical_sha256(snapshot) == trusted,
        "benchmark bootstrap does not match external trust-root SHA-256",
    )
    embedded = _sha(snapshot.get("bootstrap_sha256"), "bootstrap_sha256")
    unsigned = copy.deepcopy(snapshot)
    unsigned.pop("bootstrap_sha256", None)
    _require(canonical_sha256(unsigned) == embedded, "benchmark bootstrap self-hash mismatch")

    planning_state = snapshot.get("planning_state")
    _require(isinstance(planning_state, Mapping), "benchmark planning_state is missing")
    planning_state_sha = canonical_sha256(planning_state)
    provider = adapt_authenticated_planning_gaps(
        planning_state,
        trusted_state_sha256=planning_state_sha,
    )
    provider_input = AuthenticatedProviderStateInput(
        state=provider,
        trusted_provider_state_sha256=provider["provider_state_sha256"],
    )
    program = build_provider_planner_program_state(
        _base_program(str(snapshot["research_question"])),
        [provider_input],
    )
    plan = build_research_agent_iteration(
        program,
        previous_plan=previous_plan,
        budget_units=8.0,
        minimum_utility=0.01,
        max_iterations=8,
    )

    result: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "policy_version": BENCHMARK_POLICY_VERSION,
        "episode_stage": "self_directed_planning_iteration",
        "bootstrap_sha256": embedded,
        "provider_state_sha256": provider["provider_state_sha256"],
        "program_state_sha256": canonical_sha256(program),
        "plan": plan,
        "scientific_boundary": copy.deepcopy(snapshot["scientific_boundary"]),
        "authority_boundary": {
            "selected_action_is_authorized": False,
            "request_compiled": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    result["iteration_sha256"] = canonical_sha256(result)
    return result


__all__ = [
    "BENCHMARK_POLICY_VERSION",
    "BENCHMARK_SCHEMA_VERSION",
    "In625CompetencyBenchmarkError",
    "build_in625_competency_bootstrap",
    "build_in625_competency_iteration",
]
