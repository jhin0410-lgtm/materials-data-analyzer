"""Extend autonomous production with verified capability expansion and research resumption."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import calibration_protocol_bridge_capability as bridge
from .autonomous_production_multisource_extension import (
    run_autonomous_production as run_multisource_autonomous_production,
)
from .capability_expansion import (
    build_capability_gap,
    build_capability_specification,
)
from .capability_registry import (
    build_initial_capability_registry,
    promote_verified_capability,
)
from .capability_resolver import resolve_or_discover_capability
from .capability_verifier import verify_bounded_capability_candidate
from .in625_geometry_condition_mapping_assessment import NEXT_ACTION_CLASS

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.5"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.5"
_AVAILABLE_ACTION_CLASSES = (
    "external_evidence_search",
    "reviewed_physical_comparability_assessment",
    "nist_mds2_2923_geometry_evidence_acquisition",
    "reviewed_geometry_condition_mapping_assessment",
)
_VERIFIED_PRIMITIVES = (
    "exact_multisource_policy_authentication",
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
)


class AutonomousProductionCapabilityExtensionError(ValueError):
    """Raised when capability expansion cannot preserve predecessor authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionCapabilityExtensionError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionCapabilityExtensionError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousProductionCapabilityExtensionError(f"{field} root must be an object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _resolved_output(root: Path, output_root: str | Path) -> Path:
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=True)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionCapabilityExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _stop(
    *,
    reason_code: str,
    requested_action_class: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "stopped",
        "reason_code": reason_code,
        "requested_action_class": requested_action_class,
        "scope": "current_verified_capability_registry_and_bounded_factory_catalogue",
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }
    if extra:
        result.update(extra)
    return result


def _finalize_manifest(
    *,
    output: Path,
    manifest: dict[str, Any],
    cycles: list[dict[str, Any]],
    stop: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    final_manifest = dict(manifest)
    final_manifest.pop("manifest_sha256", None)
    final_manifest.update(
        {
            "schema_version": AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
            "policy_version": AUTONOMOUS_PRODUCTION_POLICY_VERSION,
            "cycles": cycles,
            "stop": stop,
            "scientific_status_changed": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
            **updates,
        }
    )
    final_manifest["manifest_sha256"] = _canonical_sha(final_manifest)
    _write_json(output / "bounded-stop.json", stop)
    _write_json(output / "autonomous-production-manifest.json", final_manifest)
    return final_manifest


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 7,
) -> dict[str, Any]:
    """Run research, capability expansion, verified promotion, execution, and re-diagnosis."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 8
    ):
        raise AutonomousProductionCapabilityExtensionError(
            "max_cycles must be an integer from 1 to 8"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionCapabilityExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    _require(
        hashlib.sha256(mission.read_bytes()).hexdigest() == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )

    if max_cycles <= 4:
        return run_multisource_autonomous_production(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=expected_mission_sha256,
            output_root=output_root,
            max_cycles=max_cycles,
        )

    run_multisource_autonomous_production(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=4,
    )
    output = _resolved_output(root, output_root)
    manifest = _read_json(
        output / "autonomous-production-manifest.json",
        "multi-source production manifest",
    )
    mapping = _read_json(
        output / "geometry-condition-mapping-assessment.json",
        "geometry condition mapping assessment",
    )
    prior_source_evidence = _read_json(
        output / "multisource-source-acquisition.json",
        "multi-source source acquisition",
    )
    _require(
        manifest.get("generated_next_action_class") == NEXT_ACTION_CLASS,
        "multi-source predecessor next action drifted",
    )
    next_action = mapping.get("next_action")
    _require(isinstance(next_action, dict), "mapping next_action must be an object")
    _require(
        next_action.get("action_class") == NEXT_ACTION_CLASS,
        "mapping next action class drifted",
    )
    _require(
        manifest.get("directly_comparable_mds2_rows") == 0
        and manifest.get("issue_76_exact_target_cells_satisfied") == 0,
        "capability expansion predecessor scientific boundary drifted",
    )
    cycles = manifest.get("cycles")
    _require(
        isinstance(cycles, list) and len(cycles) == 4,
        "predecessor cycle history drifted",
    )

    gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=mapping,
        available_action_classes=_AVAILABLE_ACTION_CLASSES,
    )
    specification = build_capability_specification(gap)
    initial_registry = build_initial_capability_registry(
        verified_action_classes=_AVAILABLE_ACTION_CLASSES
    )
    resolution = resolve_or_discover_capability(
        registry=initial_registry,
        capability_specification=specification,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-gap.json", gap)
    _write_json(output / "capability-specification.json", specification)
    _write_json(output / "capability-registry-initial.json", initial_registry)
    _write_json(output / "capability-resolution.json", resolution)
    candidate = resolution.get("candidate")
    if isinstance(candidate, dict):
        _write_json(output / "capability-candidate.json", candidate)

    predecessor_cycle = cycles[-1]
    _require(
        isinstance(predecessor_cycle, dict)
        and isinstance(predecessor_cycle.get("cycle_sha256"), str),
        "predecessor cycle binding is missing",
    )
    cycle5: dict[str, Any] = {
        "cycle_index": 5,
        "predecessor_cycle_sha256": predecessor_cycle["cycle_sha256"],
        "input_blocker": "experiment_specific_calibration_protocol_bridge_not_established",
        "selected_action_class": NEXT_ACTION_CLASS,
        "capability_available": False,
        "capability_gap_class": gap["gap_class"],
        "capability_gap_sha256": gap["capability_gap_sha256_without_self_field"],
        "capability_specification_sha256": specification[
            "capability_specification_sha256_without_self_field"
        ],
        "resolution_status": resolution["resolution_status"],
        "bounded_candidate_discovered": isinstance(candidate, dict),
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle5["cycle_sha256"] = _canonical_sha(cycle5)
    cycles.append(cycle5)

    base_updates = {
        "capability_gap_emitted": True,
        "capability_gap_class": gap["gap_class"],
        "capability_gap_sha256": gap["capability_gap_sha256_without_self_field"],
        "capability_specification_emitted": True,
        "capability_specification_sha256": specification[
            "capability_specification_sha256_without_self_field"
        ],
        "capability_candidate_discovered": isinstance(candidate, dict),
        "capability_candidate_promoted": False,
        "research_action_resumed_after_capability_expansion": False,
        "generated_next_action_class": NEXT_ACTION_CLASS,
    }
    if max_cycles == 5:
        return _finalize_manifest(
            output=output,
            manifest=manifest,
            cycles=cycles,
            stop=_stop(
                reason_code="maximum_cycles_reached",
                requested_action_class=NEXT_ACTION_CLASS,
                extra={"capability_expansion_ready": isinstance(candidate, dict)},
            ),
            updates=base_updates,
        )
    _require(
        isinstance(candidate, dict),
        "no bounded candidate available for first expansion acceptance action",
    )

    verification = verify_bounded_capability_candidate(
        capability_specification=specification,
        candidate=candidate,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        perform_real_source_smoke=True,
    )
    _write_json(output / "capability-verification.json", verification)
    _require(
        verification.get("promotion_eligible") is True,
        "bounded capability candidate failed independent verification",
    )
    promoted_registry = promote_verified_capability(
        registry=initial_registry,
        candidate=candidate,
        verification_receipt=verification,
    )
    _write_json(output / "capability-registry-promoted.json", promoted_registry)
    post_promotion_resolution = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=specification,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(
        output / "capability-post-promotion-resolution.json",
        post_promotion_resolution,
    )
    _require(
        post_promotion_resolution.get("resolution_status")
        == "verified_capability_resolved"
        and post_promotion_resolution.get("implementation_id")
        == bridge.IMPLEMENTATION_ID,
        "promoted capability did not resolve exact blocked action",
    )

    bridge_result = bridge.execute_bridge_capability(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        mapping_assessment=mapping,
        prior_evidence=prior_source_evidence,
    )
    _write_json(
        output / "calibration-protocol-bridge-capability-result.json",
        bridge_result,
    )
    _require(
        bridge_result.get("bridge_established") is False,
        "bridge capability improperly established equivalence",
    )
    _require(
        bridge_result.get("directly_comparable_mds2_rows") == 0
        and bridge_result.get("issue_76_exact_target_cells_satisfied") == 0,
        "bridge capability changed protected scientific boundaries",
    )
    refined_action = bridge_result.get("next_action")
    _require(
        isinstance(refined_action, dict),
        "bridge capability did not generate a refined next action",
    )
    refined_action_class = refined_action.get("action_class")
    _require(
        refined_action_class == bridge.NEXT_ACTION_CLASS,
        "bridge capability refined action class drifted",
    )
    cycle6: dict[str, Any] = {
        "cycle_index": 6,
        "predecessor_cycle_sha256": cycle5["cycle_sha256"],
        "input_blocker": "missing_source_adapter",
        "selected_action_class": NEXT_ACTION_CLASS,
        "capability_available": True,
        "capability_candidate_sha256": candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        "capability_verification_sha256": verification[
            "capability_verification_sha256_without_self_field"
        ],
        "promoted_registry_sha256": promoted_registry[
            "capability_registry_sha256_without_self_field"
        ],
        "implementation_id": bridge.IMPLEMENTATION_ID,
        "research_action_resumed": True,
        "network_requests_performed": bridge_result["network_requests_performed"],
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "output_next_action_class": refined_action_class,
        "new_verified_information": bool(
            bridge_result["new_source_version_information"]
        ),
        "scientific_status_changed": False,
    }
    cycle6["cycle_sha256"] = _canonical_sha(cycle6)
    cycles.append(cycle6)
    resumed_updates = {
        **base_updates,
        "capability_candidate_promoted": True,
        "capability_verification_sha256": verification[
            "capability_verification_sha256_without_self_field"
        ],
        "promoted_capability_registry_sha256": promoted_registry[
            "capability_registry_sha256_without_self_field"
        ],
        "research_action_resumed_after_capability_expansion": True,
        "bridge_capability_execution_sha256": bridge_result[
            "report_sha256_without_self_field"
        ],
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "generated_next_action_class": refined_action_class,
    }
    if max_cycles == 6:
        return _finalize_manifest(
            output=output,
            manifest=manifest,
            cycles=cycles,
            stop=_stop(
                reason_code="maximum_cycles_reached",
                requested_action_class=str(refined_action_class),
            ),
            updates=resumed_updates,
        )

    second_gap = build_capability_gap(
        requested_action=refined_action,
        predecessor_report=bridge_result,
        available_action_classes=tuple(_AVAILABLE_ACTION_CLASSES) + (NEXT_ACTION_CLASS,),
    )
    second_specification = build_capability_specification(second_gap)
    second_resolution = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=second_specification,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-gap-2.json", second_gap)
    _write_json(output / "capability-specification-2.json", second_specification)
    _write_json(output / "capability-resolution-2.json", second_resolution)
    cycle7: dict[str, Any] = {
        "cycle_index": 7,
        "predecessor_cycle_sha256": cycle6["cycle_sha256"],
        "input_blocker": "experiment_specific_calibration_record_not_discovered",
        "selected_action_class": refined_action_class,
        "capability_available": False,
        "capability_gap_class": second_gap["gap_class"],
        "capability_gap_sha256": second_gap[
            "capability_gap_sha256_without_self_field"
        ],
        "capability_specification_sha256": second_specification[
            "capability_specification_sha256_without_self_field"
        ],
        "resolution_status": second_resolution["resolution_status"],
        "bounded_candidate_discovered": second_resolution.get("candidate") is not None,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle7["cycle_sha256"] = _canonical_sha(cycle7)
    cycles.append(cycle7)
    stop = _stop(
        reason_code="no_bounded_capability_candidate_available",
        requested_action_class=str(refined_action_class),
        extra={
            "capability_gap_class": second_gap["gap_class"],
            "capability_gap_sha256": second_gap[
                "capability_gap_sha256_without_self_field"
            ],
            "capability_specification_sha256": second_specification[
                "capability_specification_sha256_without_self_field"
            ],
            "unrestricted_discovery_performed": False,
            "arbitrary_code_generation_performed": False,
        },
    )
    return _finalize_manifest(
        output=output,
        manifest=manifest,
        cycles=cycles,
        stop=stop,
        updates={
            **resumed_updates,
            "second_capability_gap_emitted": True,
            "second_capability_gap_class": second_gap["gap_class"],
            "second_capability_candidate_discovered": False,
            "generated_next_action_class": refined_action_class,
        },
    )


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionCapabilityExtensionError",
    "run_autonomous_production",
]
