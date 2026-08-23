"""Recursively expand verified capabilities and resume the generated materials-research action."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import calibration_protocol_bridge_capability as bridge
from . import nist_ammt_calibration_source_discovery as discovery
from .autonomous_production_capability_extension import (
    run_autonomous_production as run_first_capability_expansion,
)
from .capability_expansion import build_capability_gap, build_capability_specification
from .capability_registry import promote_verified_capability
from .capability_resolver import resolve_or_discover_capability
from .capability_verifier import verify_bounded_capability_candidate
from .nist_ammt_source_discovery_policy import (
    authenticate_nist_ammt_source_discovery_policy,
)

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.6"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.6"
_BASE_ACTION_CLASSES = (
    "external_evidence_search",
    "reviewed_physical_comparability_assessment",
    "nist_mds2_2923_geometry_evidence_acquisition",
    "reviewed_geometry_condition_mapping_assessment",
)
_VERIFIED_PRIMITIVES = (
    "exact_multisource_policy_authentication",
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
    "mission_pinned_source_index_authentication",
    "bounded_official_index_retrieval",
    "provenance_bound_candidate_ranking",
)


class AutonomousProductionRecursiveCapabilityExtensionError(ValueError):
    """Raised when recursive capability expansion cannot preserve exact authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionRecursiveCapabilityExtensionError(message)


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
        raise AutonomousProductionRecursiveCapabilityExtensionError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousProductionRecursiveCapabilityExtensionError(
            f"{field} root must be an object"
        )
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
        raise AutonomousProductionRecursiveCapabilityExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _stop(reason_code: str, action_class: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "stopped",
        "reason_code": reason_code,
        "requested_action_class": action_class,
        "scope": "verified_registry_and_mission_pinned_bounded_factory_catalogue",
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
        **extra,
    }


def _finalize(
    *,
    output: Path,
    manifest: dict[str, Any],
    cycles: list[dict[str, Any]],
    stop: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    result = dict(manifest)
    result.pop("manifest_sha256", None)
    result.update(
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
    result["manifest_sha256"] = _canonical_sha(result)
    _write_json(output / "bounded-stop.json", stop)
    _write_json(output / "autonomous-production-manifest.json", result)
    return result


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 8,
) -> dict[str, Any]:
    """Run two independent capability-expansion/promote/resume cycles on real evidence."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 8
    ):
        raise AutonomousProductionRecursiveCapabilityExtensionError(
            "max_cycles must be an integer from 1 to 8"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionRecursiveCapabilityExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    _require(
        hashlib.sha256(mission.read_bytes()).hexdigest() == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )

    if max_cycles <= 6:
        return run_first_capability_expansion(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=expected_mission_sha256,
            output_root=output_root,
            max_cycles=max_cycles,
        )

    run_first_capability_expansion(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=6,
    )
    output = _resolved_output(root, output_root)
    manifest = _read_json(
        output / "autonomous-production-manifest.json",
        "first capability-expansion manifest",
    )
    bridge_result = _read_json(
        output / "calibration-protocol-bridge-capability-result.json",
        "calibration/protocol bridge result",
    )
    registry = _read_json(
        output / "capability-registry-promoted.json",
        "first promoted capability registry",
    )
    cycles = manifest.get("cycles")
    _require(
        isinstance(cycles, list) and len(cycles) == 6,
        "first expansion cycle history drifted",
    )
    _require(
        manifest.get("research_action_resumed_after_capability_expansion") is True
        and manifest.get("bridge_established") is False
        and manifest.get("directly_comparable_mds2_rows") == 0
        and manifest.get("issue_76_exact_target_cells_satisfied") == 0,
        "first expansion scientific boundary drifted",
    )
    next_action = bridge_result.get("next_action")
    _require(isinstance(next_action, dict), "bridge result next action is missing")
    _require(
        next_action.get("action_class") == discovery.ACTION_CLASS,
        "bridge result did not generate exact NIST source-discovery action",
    )

    second_gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=bridge_result,
        available_action_classes=tuple(_BASE_ACTION_CLASSES) + (bridge.ACTION_CLASS,),
    )
    second_spec = build_capability_specification(second_gap)
    second_resolution = resolve_or_discover_capability(
        registry=registry,
        capability_specification=second_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    second_candidate = second_resolution.get("candidate")
    _require(
        isinstance(second_candidate, dict),
        "no bounded candidate was discovered for mission-pinned NIST source discovery",
    )
    _write_json(output / "capability-gap-2.json", second_gap)
    _write_json(output / "capability-specification-2.json", second_spec)
    _write_json(output / "capability-resolution-2.json", second_resolution)
    _write_json(output / "capability-candidate-2.json", second_candidate)

    cycle7: dict[str, Any] = {
        "cycle_index": 7,
        "predecessor_cycle_sha256": cycles[-1]["cycle_sha256"],
        "input_blocker": "experiment_specific_calibration_record_not_discovered",
        "selected_action_class": discovery.ACTION_CLASS,
        "capability_available": False,
        "capability_gap_class": second_gap["gap_class"],
        "capability_gap_sha256": second_gap["capability_gap_sha256_without_self_field"],
        "capability_specification_sha256": second_spec[
            "capability_specification_sha256_without_self_field"
        ],
        "resolution_status": second_resolution["resolution_status"],
        "bounded_candidate_discovered": True,
        "capability_candidate_sha256": second_candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle7["cycle_sha256"] = _canonical_sha(cycle7)
    cycles.append(cycle7)
    if max_cycles == 7:
        return _finalize(
            output=output,
            manifest=manifest,
            cycles=cycles,
            stop=_stop(
                "maximum_cycles_reached",
                discovery.ACTION_CLASS,
                capability_expansion_ready=True,
            ),
            updates={
                "second_capability_gap_emitted": True,
                "second_capability_candidate_discovered": True,
                "second_capability_candidate_promoted": False,
                "second_research_action_resumed": False,
                "generated_next_action_class": discovery.ACTION_CLASS,
            },
        )

    second_verification = verify_bounded_capability_candidate(
        capability_specification=second_spec,
        candidate=second_candidate,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        perform_real_source_smoke=True,
    )
    _write_json(output / "capability-verification-2.json", second_verification)
    _require(
        second_verification.get("promotion_eligible") is True,
        "NIST source-discovery candidate failed independent verification",
    )
    promoted_registry = promote_verified_capability(
        registry=registry,
        candidate=second_candidate,
        verification_receipt=second_verification,
    )
    _write_json(output / "capability-registry-promoted-2.json", promoted_registry)
    resolved = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=second_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-post-promotion-resolution-2.json", resolved)
    _require(
        resolved.get("resolution_status") == "verified_capability_resolved"
        and resolved.get("implementation_id") == discovery.IMPLEMENTATION_ID,
        "promoted NIST discovery capability did not resolve the exact blocked action",
    )

    qualification = authenticate_nist_ammt_source_discovery_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
    )
    _write_json(output / "nist-ammt-source-discovery-policy-qualification.json", qualification)
    discovery_result = discovery.discover_nist_ammt_calibration_sources(
        qualification=qualification,
    )
    _write_json(output / "calibration-record-source-discovery.json", discovery_result)
    _require(
        discovery_result.get("candidate_count", 0) > 0,
        "official NIST AMMT index yielded no bounded candidates",
    )
    _require(
        discovery_result.get("candidate_links_followed") == 0
        and discovery_result.get("candidate_urls_gain_acquisition_authority") is False
        and discovery_result.get("unrestricted_search_performed") is False,
        "source discovery improperly widened acquisition authority",
    )
    _require(
        discovery_result.get("scientific_status_changed") is False,
        "source discovery improperly changed scientific status",
    )
    third_action = discovery_result.get("next_action")
    _require(isinstance(third_action, dict), "source discovery next action is missing")
    third_action_class = third_action.get("action_class")
    _require(
        third_action_class == discovery.NEXT_ACTION_CLASS,
        "source discovery next action class drifted",
    )

    cycle8: dict[str, Any] = {
        "cycle_index": 8,
        "predecessor_cycle_sha256": cycle7["cycle_sha256"],
        "input_blocker": "missing_source_adapter",
        "selected_action_class": discovery.ACTION_CLASS,
        "capability_available": True,
        "capability_candidate_sha256": second_candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        "capability_verification_sha256": second_verification[
            "capability_verification_sha256_without_self_field"
        ],
        "promoted_registry_sha256": promoted_registry[
            "capability_registry_sha256_without_self_field"
        ],
        "implementation_id": discovery.IMPLEMENTATION_ID,
        "research_action_resumed": True,
        "network_requests_performed": discovery_result["network_requests_performed"],
        "discovery_candidate_count": discovery_result["candidate_count"],
        "candidate_links_followed": 0,
        "candidate_urls_gain_acquisition_authority": False,
        "output_next_action_class": third_action_class,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle8["cycle_sha256"] = _canonical_sha(cycle8)
    cycles.append(cycle8)

    third_gap = build_capability_gap(
        requested_action=third_action,
        predecessor_report=discovery_result,
        available_action_classes=tuple(_BASE_ACTION_CLASSES)
        + (bridge.ACTION_CLASS, discovery.ACTION_CLASS),
    )
    third_spec = build_capability_specification(third_gap)
    third_resolution = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=third_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-gap-3.json", third_gap)
    _write_json(output / "capability-specification-3.json", third_spec)
    _write_json(output / "capability-resolution-3.json", third_resolution)
    _require(
        third_resolution.get("resolution_status") == "no_bounded_candidate_available",
        "candidate-acquisition capability unexpectedly gained authority",
    )

    stop = _stop(
        "capability_expansion_required",
        str(third_action_class),
        capability_gap_class=third_gap["gap_class"],
        capability_gap_sha256=third_gap["capability_gap_sha256_without_self_field"],
        capability_specification_sha256=third_spec[
            "capability_specification_sha256_without_self_field"
        ],
        bounded_candidate_discovered=False,
        unrestricted_discovery_performed=False,
        arbitrary_code_generation_performed=False,
    )
    return _finalize(
        output=output,
        manifest=manifest,
        cycles=cycles,
        stop=stop,
        updates={
            "second_capability_gap_emitted": True,
            "second_capability_candidate_discovered": True,
            "second_capability_candidate_promoted": True,
            "second_capability_verification_sha256": second_verification[
                "capability_verification_sha256_without_self_field"
            ],
            "second_promoted_capability_registry_sha256": promoted_registry[
                "capability_registry_sha256_without_self_field"
            ],
            "second_research_action_resumed": True,
            "nist_ammt_source_discovery_executed": True,
            "nist_ammt_source_discovery_sha256": discovery_result[
                "report_sha256_without_self_field"
            ],
            "nist_ammt_source_discovery_candidate_count": discovery_result[
                "candidate_count"
            ],
            "candidate_urls_gain_acquisition_authority": False,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "issue_76_exact_target_cells_satisfied": 0,
            "third_capability_gap_emitted": True,
            "third_capability_candidate_discovered": False,
            "generated_next_action_class": third_action_class,
            "final_blocker": "candidate_acquisition_capability_not_established",
        },
    )


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionRecursiveCapabilityExtensionError",
    "run_autonomous_production",
]
