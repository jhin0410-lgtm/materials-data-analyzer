"""Independently bind and replay the eight-source cycle-6 bridge reacquisition.

Cycle 6 performs a fresh network reacquisition after capability promotion.  Its scientific and
operational interpretation must therefore be derived from the exact responses observed in that
cycle, not from an attacker-rehashable source digest or source-version-change list.  The producer
retains those responses inside the self-hashed bridge result; this gate replays the nested evidence
through the independently reviewed multisource witness and then rebuilds the complete bridge report
from authenticated cycle-4 prior evidence.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import calibration_protocol_bridge_capability as _bridge
from .autonomous_production_multisource_reviewed_witness import (
    AutonomousProductionMultisourceReviewedWitnessError,
    verify_multisource_acquisition_against_reviewed_witness,
)

AutonomousProductionCycle6ReacquisitionBindingError = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionCycle6ReacquisitionBindingError(message)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def verify_cycle6_reacquisition_boundaries(output_root: str | Path) -> None:
    """Replay cycle-6 exact responses and rebuild every bridge/source-version conclusion."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    if len(cycles) < 6:
        return

    bridge_result = _merge_gate._load(
        root, "calibration-protocol-bridge-capability-result.json"
    )
    bridge_sha = _merge_gate._verify_self_hash(
        bridge_result,
        "report_sha256_without_self_field",
        label="cycle-6 bridge capability result",
    )
    _require(
        manifest.get("bridge_capability_execution_sha256") == bridge_sha,
        "manifest bridge execution digest does not bind the cycle-6 bridge result",
    )

    reacquired = _mapping(
        bridge_result.get("reacquired_source_evidence"),
        label="cycle-6 retained reacquisition evidence",
    )
    reacquired_sha = _merge_gate._verify_self_hash(
        reacquired,
        "report_sha256_without_self_field",
        label="cycle-6 retained reacquisition evidence",
    )
    _require(
        bridge_result.get("reacquired_source_report_sha256") == reacquired_sha,
        "bridge result does not bind the exact retained cycle-6 reacquisition report",
    )
    _require(
        reacquired.get("source_bytes_persisted") is True
        and reacquired.get("retained_source_bytes_count") == 8
        and reacquired.get("network_requests_performed") == 8,
        "cycle-6 reacquisition did not retain the complete eight-source execution",
    )

    try:
        verify_multisource_acquisition_against_reviewed_witness(reacquired)
    except AutonomousProductionMultisourceReviewedWitnessError as exc:
        raise AutonomousProductionCycle6ReacquisitionBindingError(
            f"cycle-6 reacquisition failed independent retained-source replay: {exc}"
        ) from exc

    prior = _merge_gate._load(root, "multisource-source-acquisition.json")
    _merge_gate._verify_self_hash(
        prior,
        "report_sha256_without_self_field",
        label="cycle-4 prior multisource evidence",
    )
    try:
        verify_multisource_acquisition_against_reviewed_witness(prior)
    except AutonomousProductionMultisourceReviewedWitnessError as exc:
        raise AutonomousProductionCycle6ReacquisitionBindingError(
            f"cycle-4 prior evidence failed independent retained-source replay: {exc}"
        ) from exc

    mapping = _merge_gate._load(root, "geometry-condition-mapping-assessment.json")
    _merge_gate._verify_self_hash(
        mapping,
        "report_sha256_without_self_field",
        label="geometry-condition mapping assessment",
    )
    try:
        expected_bridge = _bridge.build_bridge_frontier_report(
            mapping_assessment=mapping,
            reacquired_evidence=reacquired,
            prior_evidence=prior,
        )
    except _bridge.CalibrationProtocolBridgeCapabilityError as exc:
        raise AutonomousProductionCycle6ReacquisitionBindingError(
            f"cycle-6 bridge result could not be canonically rebuilt: {exc}"
        ) from exc
    _require(
        _canonical_bytes(bridge_result) == _canonical_bytes(expected_bridge),
        "cycle-6 bridge/source-version conclusions drifted from retained reacquisition replay",
    )

    cycle6 = _mapping(cycles[5], label="cycle 6")
    _require(cycle6.get("cycle_index") == 6, "cycle-6 index drifted")
    _require(
        cycle6.get("network_requests_performed")
        == expected_bridge["network_requests_performed"],
        "cycle 6 network history drifted from retained reacquisition evidence",
    )
    _require(
        cycle6.get("new_verified_information")
        is bool(expected_bridge["new_source_version_information"]),
        "cycle 6 new-information state drifted from authenticated source-version comparison",
    )
    next_action = _mapping(expected_bridge.get("next_action"), label="cycle-6 rebuilt next action")
    next_action_class = next_action.get("action_class")
    _require(
        cycle6.get("output_next_action_class") == next_action_class,
        "cycle-6 next action drifted from rebuilt bridge result",
    )
    if len(cycles) == 6:
        _require(
            manifest.get("generated_next_action_class") == next_action_class,
            "cycle-6 terminal manifest next action drifted from rebuilt bridge result",
        )
    else:
        cycle7 = _mapping(cycles[6], label="cycle 7")
        _require(
            cycle7.get("cycle_index") == 7
            and cycle7.get("selected_action_class") == next_action_class,
            "cycle-7 selected action does not continue the rebuilt cycle-6 frontier",
        )
    _require(
        cycle6.get("bridge_established") is False
        and cycle6.get("directly_comparable_mds2_rows") == 0
        and cycle6.get("issue_76_exact_target_cells_satisfied") == 0
        and manifest.get("bridge_established") is False
        and manifest.get("directly_comparable_mds2_rows") == 0
        and manifest.get("issue_76_exact_target_cells_satisfied") == 0,
        "cycle-6 retained evidence widened protected scientific authority",
    )


__all__ = [
    "AutonomousProductionCycle6ReacquisitionBindingError",
    "verify_cycle6_reacquisition_boundaries",
]
