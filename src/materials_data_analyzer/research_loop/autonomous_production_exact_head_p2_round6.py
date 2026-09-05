"""Canonical capability-registry lineage closure for PR #233.

The terminal round-5 gate consumes the promoted capability registry as an authenticated
input.  A self-hashed registry is not sufficient authority by itself: each successor must be
the exact result of promoting one independently verified candidate from its authenticated
predecessor.  This verifier replays the complete production registry chain from the fixed
initial audited action set through all four promotions and their post-promotion resolutions.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from .capability_registry import (
    build_initial_capability_registry,
    promote_verified_capability,
)
from .capability_resolver import resolve_or_discover_capability

AutonomousProductionExactHeadRound6Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_INITIAL_VERIFIED_ACTIONS = (
    "external_evidence_search",
    "nist_mds2_2923_geometry_evidence_acquisition",
    "reviewed_geometry_condition_mapping_assessment",
    "reviewed_physical_comparability_assessment",
)

_PROMOTIONS = (
    (
        "",
        "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition",
        "ammt-calibration-bridge-existing-source-adapter-v1",
        6,
        "promoted_capability_registry_sha256",
    ),
    (
        "-2",
        "experiment_specific_calibration_record_source_discovery",
        "nist-ammt-curated-publication-index-discovery-v1",
        8,
        "second_promoted_capability_registry_sha256",
    ),
    (
        "-3",
        "experiment_specific_calibration_record_candidate_acquisition",
        "nist-ammt-derived-calibration-candidate-acquisition-v1",
        10,
        "third_promoted_capability_registry_sha256",
    ),
    (
        "-4",
        "mds2_2923_experiment_identity_reference_chain_assessment",
        "mds2-2923-experiment-identity-reference-chain-v1",
        12,
        None,
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound6Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _name(stem: str, suffix: str) -> str:
    return f"{stem}{suffix}.json"


def verify_exact_head_round6_boundaries(output_root: str | Path) -> None:
    """Replay the exact audited registry promotion lineage for a 12-cycle success run."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    if len(cycles_value) < 12:
        return
    cycles: list[Mapping[str, Any]] = []
    for index, raw_cycle in enumerate(cycles_value, start=1):
        cycles.append(_mapping(raw_cycle, label=f"cycle {index}"))

    persisted_initial = _merge_gate._load(root, "capability-registry-initial.json")
    _merge_gate._verify_self_hash(
        persisted_initial,
        "capability_registry_sha256_without_self_field",
        label="initial capability registry",
    )
    expected_registry = build_initial_capability_registry(
        verified_action_classes=_INITIAL_VERIFIED_ACTIONS,
    )
    _require(
        persisted_initial == expected_registry,
        "initial capability registry drifted from the fixed audited runtime action set",
    )

    for step, (suffix, action_class, implementation_id, cycle_index, manifest_field) in enumerate(
        _PROMOTIONS,
        start=1,
    ):
        specification = _merge_gate._load(root, _name("capability-specification", suffix))
        specification_sha = _merge_gate._verify_self_hash(
            specification,
            "capability_specification_sha256_without_self_field",
            label=f"capability promotion {step} specification",
        )
        candidate = _merge_gate._load(root, _name("capability-candidate", suffix))
        candidate_sha = _merge_gate._verify_self_hash(
            candidate,
            "capability_candidate_sha256_without_self_field",
            label=f"capability promotion {step} candidate",
        )
        verification = _merge_gate._load(root, _name("capability-verification", suffix))
        verification_sha = _merge_gate._verify_self_hash(
            verification,
            "capability_verification_sha256_without_self_field",
            label=f"capability promotion {step} verification",
        )

        _require(
            specification.get("requested_action_class") == action_class,
            f"capability promotion {step} specification action drifted",
        )
        _require(
            candidate.get("action_class") == action_class
            and candidate.get("implementation_id") == implementation_id
            and candidate.get("capability_specification_sha256") == specification_sha,
            f"capability promotion {step} candidate identity or specification binding drifted",
        )
        _require(
            verification.get("action_class") == action_class
            and verification.get("capability_specification_sha256") == specification_sha
            and verification.get("capability_candidate_sha256") == candidate_sha
            and verification.get("all_required_checks_passed") is True
            and verification.get("promotion_eligible") is True,
            f"capability promotion {step} verification binding or eligibility drifted",
        )

        canonical_successor = promote_verified_capability(
            registry=expected_registry,
            candidate=candidate,
            verification_receipt=verification,
        )
        persisted_successor = _merge_gate._load(
            root,
            _name("capability-registry-promoted", suffix),
        )
        _require(
            persisted_successor == canonical_successor,
            f"capability promotion {step} registry drifted from canonical successor",
        )

        expected_resolution = resolve_or_discover_capability(
            registry=canonical_successor,
            capability_specification=specification,
            available_verified_primitives=[],
        )
        persisted_resolution = _merge_gate._load(
            root,
            _name("capability-post-promotion-resolution", suffix),
        )
        _require(
            persisted_resolution == expected_resolution,
            f"capability promotion {step} post-promotion resolution drifted",
        )

        registry_sha = canonical_successor[
            "capability_registry_sha256_without_self_field"
        ]
        cycle = cycles[cycle_index - 1]
        _require(
            cycle.get("promoted_registry_sha256") == registry_sha,
            f"cycle {cycle_index} promoted registry binding drifted",
        )
        if manifest_field is not None:
            _require(
                manifest.get(manifest_field) == registry_sha,
                f"manifest capability promotion {step} registry binding drifted",
            )
        _require(
            verification.get("capability_verification_sha256_without_self_field")
            == verification_sha,
            f"capability promotion {step} verification self binding drifted",
        )
        expected_registry = canonical_successor


__all__ = [
    "AutonomousProductionExactHeadRound6Error",
    "verify_exact_head_round6_boundaries",
]
