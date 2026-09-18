"""Canonical trusted-producer and zero-network verifier replay for all capability promotions.

Round 6 reconstructs the registry successor chain, but persisted gap/specification/candidate/
verification artifacts can still be rewritten self-consistently.  This layer removes that
persisted-artifact authority before registry promotion:

* rebuild each promotion gap from its authenticated predecessor report and next action;
* rebuild the capability specification with the canonical compiler;
* rebuild the candidate from the finite trusted factory catalogue;
* rerun the authoritative verifier from the exact smoke bytes/request contract retained by the
  original live verification, with zero historical network requests; and
* accept only byte-for-byte equal persisted artifacts before canonical registry promotion.

All four production promotions are covered.  Missing, substituted, corrupted, extra, or
unconsumed retained smoke evidence fails closed and never changes scientific status.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import autonomous_production_exact_head_p2_round5 as _round5
from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import calibration_protocol_bridge_capability as bridge
from . import capability_smoke_replay_evidence as _smoke_replay
from . import capability_verifier as _capability_verifier
from . import mds2_2923_reference_chain_capability as reference_capability
from . import mds2_2923_reference_chain_capability_verifier as _reference_verifier
from . import nist_ammt_calibration_candidate_acquisition as candidate_acquisition
from . import nist_ammt_calibration_source_discovery as discovery
from .capability_expansion import build_capability_gap, build_capability_specification
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
    candidate_acquisition.ACTION_CLASS: candidate_acquisition.REQUIRED_VERIFIED_PRIMITIVES,
    reference_capability.ACTION_CLASS: reference_capability.REQUIRED_VERIFIED_PRIMITIVES,
}
_PREDECESSOR_REPORTS = (
    "geometry-condition-mapping-assessment.json",
    "calibration-protocol-bridge-capability-result.json",
    "calibration-record-source-discovery.json",
    "nist-ammt-calibration-candidate-bridge-assessment.json",
)


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


def _canonical_gap_and_specification(
    *,
    root: Path,
    step: int,
    action_class: str,
    registry: Mapping[str, Any],
    suffix: str,
) -> tuple[dict[str, Any], dict[str, Any], Mapping[str, Any]]:
    predecessor = _merge_gate._load(root, _PREDECESSOR_REPORTS[step - 1])
    _merge_gate._verify_self_hash(
        predecessor,
        "report_sha256_without_self_field",
        label=f"capability promotion {step} predecessor report",
    )
    next_action = _mapping(
        predecessor.get("next_action"),
        label=f"capability promotion {step} predecessor next action",
    )
    _require(
        next_action.get("action_class") == action_class,
        f"capability promotion {step} action drifted from authenticated predecessor",
    )
    expected_gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=predecessor,
        available_action_classes=_round5._verified_action_classes(registry),
    )
    persisted_gap = _merge_gate._load(root, _round6._name("capability-gap", suffix))
    _require(
        persisted_gap == expected_gap,
        f"capability promotion {step} gap drifted from canonical predecessor replay",
    )
    expected_specification = build_capability_specification(expected_gap)
    persisted_specification = _merge_gate._load(
        root,
        _round6._name("capability-specification", suffix),
    )
    _require(
        persisted_specification == expected_specification,
        f"capability promotion {step} specification drifted from canonical gap replay",
    )
    return expected_gap, expected_specification, predecessor


def _authenticate_replay_context(
    *,
    root: Path,
    step: int,
    action_class: str,
    specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    persisted_verification: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    mission_sha: str,
    cycles: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    evidence = persisted_verification.get("real_source_smoke_replay_evidence")
    _require(
        isinstance(evidence, Mapping),
        f"capability promotion {step} retained smoke replay evidence is missing",
    )
    spec_sha = specification.get("capability_specification_sha256_without_self_field")
    candidate_sha = candidate.get("capability_candidate_sha256_without_self_field")
    _require(
        isinstance(spec_sha, str) and len(spec_sha) == 64,
        f"capability promotion {step} canonical specification binding is missing",
    )
    _require(
        isinstance(candidate_sha, str) and len(candidate_sha) == 64,
        f"capability promotion {step} canonical candidate binding is missing",
    )
    try:
        _unused_fetcher, context = _smoke_replay.authenticate_smoke_replay_evidence(
            evidence,
            action_class=action_class,
            capability_specification_sha256=spec_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
        )
    except _smoke_replay.CapabilitySmokeReplayEvidenceError as exc:
        raise AutonomousProductionExactHeadRound7Error(
            f"capability promotion {step} retained smoke replay evidence failed authentication: {exc}"
        ) from exc

    replay_sha = evidence.get("smoke_replay_evidence_sha256_without_self_field")
    _require(
        persisted_verification.get("real_source_smoke_replay_evidence_sha256") == replay_sha,
        f"capability promotion {step} verification/replay-evidence binding drifted",
    )

    if step in (1, 2):
        _require(
            context is None,
            f"capability promotion {step} unexpectedly retained mutable verifier context",
        )
        return evidence, None

    _require(
        isinstance(context, Mapping),
        f"capability promotion {step} retained verifier context is missing",
    )
    if step == 3:
        retained_discovery = context.get("discovery_report")
        retained_manifest = context.get("predecessor_manifest")
        _require(
            isinstance(retained_discovery, Mapping)
            and dict(retained_discovery) == dict(predecessor),
            "capability promotion 3 retained discovery context was substituted",
        )
        _require(
            isinstance(retained_manifest, Mapping),
            "capability promotion 3 retained predecessor manifest is missing",
        )
        manifest_sha = retained_manifest.get("manifest_sha256")
        unsigned_manifest = dict(retained_manifest)
        unsigned_manifest.pop("manifest_sha256", None)
        _require(
            isinstance(manifest_sha, str)
            and len(manifest_sha) == 64
            and _merge_gate._canonical_sha(unsigned_manifest) == manifest_sha,
            "capability promotion 3 retained predecessor manifest self binding is invalid",
        )
        retained_cycles = retained_manifest.get("cycles")
        _require(
            isinstance(retained_cycles, list)
            and len(retained_cycles) == 8
            and [dict(item) for item in retained_cycles if isinstance(item, Mapping)]
            == [dict(item) for item in cycles[:8]],
            "capability promotion 3 retained predecessor cycle snapshot was substituted",
        )
        predecessor_sha = predecessor.get("report_sha256_without_self_field")
        _require(
            retained_manifest.get("nist_ammt_source_discovery_sha256") == predecessor_sha
            and retained_manifest.get("generated_next_action_class") == action_class
            and retained_manifest.get("third_capability_gap_emitted") is True
            and retained_manifest.get("directly_comparable_mds2_rows") == 0
            and retained_manifest.get("issue_76_exact_target_cells_satisfied") == 0
            and retained_manifest.get("bridge_established") is False
            and retained_manifest.get("scientific_status_changed") is False,
            "capability promotion 3 retained predecessor authority/science boundary drifted",
        )
        return evidence, context

    retained_calibration = context.get("calibration_candidate_assessment")
    _require(
        isinstance(retained_calibration, Mapping)
        and dict(retained_calibration) == dict(predecessor),
        "capability promotion 4 retained calibration context was substituted",
    )
    persisted_nist = _merge_gate._load(root, "nist-scientific-intake.json")
    persisted_multisource = _merge_gate._load(root, "multisource-source-acquisition.json")
    persisted_discovery = _merge_gate._load(root, "calibration-record-source-discovery.json")
    for key, expected in (
        ("nist_intake", persisted_nist),
        ("multisource_evidence", persisted_multisource),
        ("source_discovery_report", persisted_discovery),
    ):
        retained = context.get(key)
        _require(
            isinstance(retained, Mapping) and dict(retained) == expected,
            f"capability promotion 4 retained {key} context was substituted",
        )
    metadata_path = (root / "nist-mds2-2923" / "nerdm-metadata.json").resolve(strict=True)
    try:
        metadata_path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionExactHeadRound7Error(
            "capability promotion 4 persisted NERDm metadata escaped output root"
        ) from exc
    _require(metadata_path.is_file(), "capability promotion 4 persisted NERDm metadata is missing")
    _require(
        context.get("nerdm_metadata_bytes") == metadata_path.read_bytes(),
        "capability promotion 4 retained NERDm bytes were substituted",
    )
    return evidence, context


def _replay_trusted_candidate_and_verification(
    *,
    root: Path,
    step: int,
    registry: Mapping[str, Any],
    specification: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    persisted_candidate: Mapping[str, Any],
    persisted_verification: Mapping[str, Any],
    cycles: Sequence[Mapping[str, Any]],
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
    evidence, _context = _authenticate_replay_context(
        root=root,
        step=step,
        action_class=str(action_class),
        specification=specification,
        candidate=candidate,
        persisted_verification=persisted_verification,
        predecessor=predecessor,
        mission_sha=mission_sha,
        cycles=cycles,
    )
    try:
        if action_class == reference_capability.ACTION_CLASS:
            verification = _reference_verifier.verify_reference_chain_capability_candidate(
                capability_specification=specification,
                candidate=candidate,
                available_verified_primitives=primitives,
                repository_root=repository_root,
                mission_path=mission_path,
                expected_mission_sha256=mission_sha,
                verification_context=None,
                perform_real_source_smoke=False,
                retained_smoke_replay_evidence=evidence,
            )
        else:
            verification = _capability_verifier.verify_bounded_capability_candidate(
                capability_specification=specification,
                candidate=candidate,
                available_verified_primitives=primitives,
                repository_root=repository_root,
                mission_path=mission_path,
                expected_mission_sha256=mission_sha,
                perform_real_source_smoke=False,
                verification_context=None,
                retained_smoke_replay_evidence=evidence,
            )
    except (ValueError, OSError) as exc:
        raise AutonomousProductionExactHeadRound7Error(
            f"capability promotion {step} authoritative retained-evidence replay failed: {exc}"
        ) from exc
    _require(
        dict(persisted_verification) == verification,
        f"capability promotion {step} verification drifted from authoritative retained-evidence replay",
    )
    return dict(candidate), verification


def verify_exact_head_round7_boundaries(output_root: str | Path) -> None:
    """Canonically replay every reached capability promotion before registry lineage replay."""
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

    for step, promotion in enumerate(_round6._PROMOTIONS, start=1):
        suffix, action_class, implementation_id, cycle_index, manifest_field = promotion
        if len(cycles) < cycle_index:
            break
        _expected_gap, specification, predecessor = _canonical_gap_and_specification(
            root=root,
            step=step,
            action_class=action_class,
            registry=expected_registry,
            suffix=suffix,
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
            candidate.get("implementation_id") == implementation_id,
            f"capability promotion {step} implementation identity drifted",
        )
        replayed_candidate, replayed_verification = _replay_trusted_candidate_and_verification(
            root=root,
            step=step,
            registry=expected_registry,
            specification=specification,
            predecessor=predecessor,
            persisted_candidate=candidate,
            persisted_verification=verification,
            cycles=cycles,
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
