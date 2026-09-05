"""Trusted factory/verifier replay for capability promotions one and two.

Round 6 reconstructs the registry successor chain, but a self-consistently rewritten
candidate plus verification receipt could still become the input to that reconstruction.
This layer removes that persisted-artifact authority.  For the first two production
promotions it rebuilds the candidate from the finite trusted factory catalogue and reruns
the authoritative verifier, including its exact-source smoke.  Only byte-for-byte equal
persisted candidate/verification artifacts are allowed to feed registry promotion.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import calibration_protocol_bridge_capability as bridge
from . import capability_verifier as _capability_verifier
from . import nist_ammt_calibration_source_discovery as discovery
from .capability_registry import CapabilityRegistryError, promote_verified_capability
from .capability_resolver import (
    CapabilityResolverError,
    resolve_or_discover_capability,
)

AutonomousProductionExactHeadRound7Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_MISSION_PATH = "configs/research/autonomous_in625_production_mission.v1.json"
_TRUSTED_PRIMITIVES: dict[str, Sequence[str]] = {
    bridge.ACTION_CLASS: bridge.REQUIRED_VERIFIED_PRIMITIVES,
    discovery.ACTION_CLASS: discovery.REQUIRED_VERIFIED_PRIMITIVES,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound7Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _trusted_mission_binding() -> tuple[Path, Path, str]:
    repository_root = _merge_gate._trusted_repository_root().resolve(strict=True)
    mission_path = (repository_root / _MISSION_PATH).resolve(strict=True)
    try:
        mission_path.relative_to(repository_root)
    except ValueError as exc:
        raise AutonomousProductionExactHeadRound7Error(
            "trusted autonomous mission escaped the repository checkout"
        ) from exc
    _require(mission_path.is_file(), "trusted autonomous mission is missing")
    return (
        repository_root,
        mission_path,
        hashlib.sha256(mission_path.read_bytes()).hexdigest(),
    )


def _replay_trusted_candidate_and_verification(
    *,
    step: int,
    registry: Mapping[str, Any],
    specification: Mapping[str, Any],
    persisted_candidate: Mapping[str, Any],
    persisted_verification: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    action_class = specification.get("requested_action_class")
    primitives = _TRUSTED_PRIMITIVES.get(action_class) if isinstance(action_class, str) else None
    _require(
        primitives is not None,
        f"capability promotion {step} has no trusted replay primitive contract",
    )
    try:
        resolution = resolve_or_discover_capability(
            registry=registry,
            capability_specification=specification,
            available_verified_primitives=primitives,
        )
    except (CapabilityRegistryError, CapabilityResolverError) as exc:
        raise AutonomousProductionExactHeadRound7Error(
            f"capability promotion {step} trusted factory replay failed: {exc}"
        ) from exc
    _require(
        resolution.get("resolution_status") == "bounded_candidate_discovered",
        f"capability promotion {step} trusted factory did not produce a candidate",
    )
    candidate = _mapping(
        resolution.get("candidate"),
        label=f"capability promotion {step} replayed candidate",
    )
    _require(
        dict(persisted_candidate) == dict(candidate),
        f"capability promotion {step} candidate drifted from trusted factory replay",
    )

    repository_root, mission_path, mission_sha = _trusted_mission_binding()
    try:
        verification = _capability_verifier.verify_bounded_capability_candidate(
            capability_specification=specification,
            candidate=candidate,
            available_verified_primitives=primitives,
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=mission_sha,
            perform_real_source_smoke=True,
        )
    except (ValueError, OSError) as exc:
        raise AutonomousProductionExactHeadRound7Error(
            f"capability promotion {step} authoritative verifier replay failed: {exc}"
        ) from exc
    _require(
        dict(persisted_verification) == verification,
        f"capability promotion {step} verification drifted from authoritative replay",
    )
    return dict(candidate), verification


def verify_exact_head_round7_boundaries(output_root: str | Path) -> None:
    """Replay promotion 1/2 producers before accepting their persisted registry lineage."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    if len(cycles_value) < 6:
        return
    cycles = [
        _mapping(value, label=f"cycle {index}")
        for index, value in enumerate(cycles_value, start=1)
    ]

    persisted_initial = _merge_gate._load(root, "capability-registry-initial.json")
    expected_registry = _round6.build_initial_capability_registry(
        verified_action_classes=_round6._INITIAL_VERIFIED_ACTIONS,
    )
    _require(
        persisted_initial == expected_registry,
        "initial capability registry drifted before trusted promotion replay",
    )

    for step, promotion in enumerate(_round6._PROMOTIONS[:2], start=1):
        suffix, action_class, implementation_id, cycle_index, manifest_field = promotion
        if len(cycles) < cycle_index:
            break
        specification = _merge_gate._load(
            root,
            _round6._name("capability-specification", suffix),
        )
        candidate = _merge_gate._load(
            root,
            _round6._name("capability-candidate", suffix),
        )
        verification = _merge_gate._load(
            root,
            _round6._name("capability-verification", suffix),
        )
        _require(
            specification.get("requested_action_class") == action_class,
            f"capability promotion {step} specification action drifted",
        )
        _require(
            candidate.get("implementation_id") == implementation_id,
            f"capability promotion {step} implementation identity drifted",
        )
        replayed_candidate, replayed_verification = (
            _replay_trusted_candidate_and_verification(
                step=step,
                registry=expected_registry,
                specification=specification,
                persisted_candidate=candidate,
                persisted_verification=verification,
            )
        )
        try:
            successor = promote_verified_capability(
                registry=expected_registry,
                candidate=replayed_candidate,
                verification_receipt=replayed_verification,
            )
        except CapabilityRegistryError as exc:
            raise AutonomousProductionExactHeadRound7Error(
                f"capability promotion {step} canonical promotion failed: {exc}"
            ) from exc
        persisted_successor = _merge_gate._load(
            root,
            _round6._name("capability-registry-promoted", suffix),
        )
        _require(
            persisted_successor == successor,
            f"capability promotion {step} registry drifted from trusted replay successor",
        )
        registry_sha = successor["capability_registry_sha256_without_self_field"]
        _require(
            cycles[cycle_index - 1].get("promoted_registry_sha256") == registry_sha,
            f"cycle {cycle_index} trusted replay registry binding drifted",
        )
        if manifest_field is not None:
            _require(
                manifest.get(manifest_field) == registry_sha,
                f"manifest capability promotion {step} trusted registry binding drifted",
            )
        expected_registry = successor


__all__ = [
    "AutonomousProductionExactHeadRound7Error",
    "verify_exact_head_round7_boundaries",
]
