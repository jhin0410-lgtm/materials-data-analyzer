"""Extend autonomous production through provenance-derived calibration candidate acquisition."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import calibration_protocol_bridge_capability as bridge
from . import nist_ammt_calibration_candidate_acquisition as candidate_acquisition
from . import nist_ammt_calibration_source_discovery as discovery
from .autonomous_production_recursive_capability_extension import (
    run_autonomous_production as run_recursive_capability_production,
)
from .capability_expansion import build_capability_gap, build_capability_specification
from .capability_registry import promote_verified_capability
from .capability_resolver import resolve_or_discover_capability
from .capability_verifier import verify_bounded_capability_candidate
from .nist_ammt_calibration_candidate_bridge_assessment import (
    NEXT_ACTION_CLASS,
    build_calibration_candidate_bridge_assessment,
)
from .nist_ammt_candidate_acquisition_policy import (
    authenticate_nist_ammt_candidate_acquisition_policy,
)

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.7"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.7"
_BASE_ACTION_CLASSES = (
    "external_evidence_search",
    "reviewed_physical_comparability_assessment",
    "nist_mds2_2923_geometry_evidence_acquisition",
    "reviewed_geometry_condition_mapping_assessment",
    bridge.ACTION_CLASS,
    discovery.ACTION_CLASS,
)
_VERIFIED_PRIMITIVES = (
    "exact_multisource_policy_authentication",
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
    "mission_pinned_source_index_authentication",
    "bounded_official_index_retrieval",
    "provenance_bound_candidate_ranking",
    "authenticated_discovery_report_binding",
    "derived_candidate_url_authorization",
    "candidate_page_local_download_derivation",
    "bounded_nist_pdf_acquisition",
    "provenance_bound_calibration_intake",
)


class AutonomousProductionCandidateAcquisitionExtensionError(ValueError):
    """Raised when candidate acquisition cannot preserve recursive authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionCandidateAcquisitionExtensionError(message)


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
        raise AutonomousProductionCandidateAcquisitionExtensionError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousProductionCandidateAcquisitionExtensionError(
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
        raise AutonomousProductionCandidateAcquisitionExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _validate_self_hash(value: Mapping[str, Any], field: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _stop(reason_code: str, action_class: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "stopped",
        "reason_code": reason_code,
        "requested_action_class": action_class,
        "scope": "verified_registry_and_mission_pinned_derived_authority",
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
    max_cycles: int = 10,
) -> dict[str, Any]:
    """Run three independently verified capability expansion/resumption cycles on real evidence."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 10
    ):
        raise AutonomousProductionCandidateAcquisitionExtensionError(
            "max_cycles must be an integer from 1 to 10"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionCandidateAcquisitionExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    _require(
        hashlib.sha256(mission.read_bytes()).hexdigest() == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )

    if max_cycles <= 8:
        return run_recursive_capability_production(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=expected_mission_sha256,
            output_root=output_root,
            max_cycles=max_cycles,
        )

    run_recursive_capability_production(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=8,
    )
    output = _resolved_output(root, output_root)
    manifest = _read_json(
        output / "autonomous-production-manifest.json",
        "recursive capability manifest",
    )
    discovery_report = _read_json(
        output / "calibration-record-source-discovery.json",
        "calibration source discovery report",
    )
    registry = _read_json(
        output / "capability-registry-promoted-2.json",
        "second promoted capability registry",
    )
    third_gap = _read_json(output / "capability-gap-3.json", "third capability gap")
    third_spec = _read_json(
        output / "capability-specification-3.json",
        "third capability specification",
    )
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and len(cycles) == 8, "recursive cycle history drifted")
    _require(
        manifest.get("generated_next_action_class") == candidate_acquisition.ACTION_CLASS
        and manifest.get("third_capability_gap_emitted") is True
        and manifest.get("candidate_urls_gain_acquisition_authority") is False,
        "recursive predecessor did not stop at derived candidate acquisition frontier",
    )
    _require(
        manifest.get("directly_comparable_mds2_rows") == 0
        and manifest.get("issue_76_exact_target_cells_satisfied") == 0
        and manifest.get("bridge_established") is False,
        "predecessor scientific boundary drifted",
    )
    discovery_sha = _validate_self_hash(
        discovery_report,
        "report_sha256_without_self_field",
    )
    _require(
        manifest.get("nist_ammt_source_discovery_sha256") == discovery_sha,
        "manifest discovery binding drifted",
    )
    _validate_self_hash(third_gap, "capability_gap_sha256_without_self_field")
    _validate_self_hash(third_spec, "capability_specification_sha256_without_self_field")
    _require(
        third_gap.get("requested_action_class") == candidate_acquisition.ACTION_CLASS
        and third_spec.get("requested_action_class") == candidate_acquisition.ACTION_CLASS,
        "third capability gap/spec action class drifted",
    )

    resolution = resolve_or_discover_capability(
        registry=registry,
        capability_specification=third_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    candidate = resolution.get("candidate")
    _require(
        resolution.get("resolution_status") == "bounded_candidate_discovered"
        and isinstance(candidate, dict),
        "no bounded derived candidate-acquisition capability was discovered",
    )
    _write_json(output / "capability-resolution-3-derived.json", resolution)
    _write_json(output / "capability-candidate-3.json", candidate)

    cycle9: dict[str, Any] = {
        "cycle_index": 9,
        "predecessor_cycle_sha256": cycles[-1]["cycle_sha256"],
        "input_blocker": "candidate_acquisition_capability_not_established",
        "selected_action_class": candidate_acquisition.ACTION_CLASS,
        "capability_available": False,
        "capability_gap_class": third_gap["gap_class"],
        "capability_gap_sha256": third_gap["capability_gap_sha256_without_self_field"],
        "capability_specification_sha256": third_spec[
            "capability_specification_sha256_without_self_field"
        ],
        "resolution_status": resolution["resolution_status"],
        "bounded_candidate_discovered": True,
        "capability_candidate_sha256": candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        "caller_authored_url_used": False,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle9["cycle_sha256"] = _canonical_sha(cycle9)
    cycles.append(cycle9)

    if max_cycles == 9:
        return _finalize(
            output=output,
            manifest=manifest,
            cycles=cycles,
            stop=_stop(
                "maximum_cycles_reached",
                candidate_acquisition.ACTION_CLASS,
                capability_expansion_ready=True,
            ),
            updates={
                "third_capability_candidate_discovered": True,
                "third_capability_candidate_promoted": False,
                "third_research_action_resumed": False,
                "generated_next_action_class": candidate_acquisition.ACTION_CLASS,
            },
        )

    verification = verify_bounded_capability_candidate(
        capability_specification=third_spec,
        candidate=candidate,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        perform_real_source_smoke=True,
        verification_context={
            "discovery_report": discovery_report,
            "predecessor_manifest": manifest,
        },
    )
    _write_json(output / "capability-verification-3.json", verification)
    _require(
        verification.get("promotion_eligible") is True,
        "derived candidate-acquisition capability failed independent verification",
    )
    promoted_registry = promote_verified_capability(
        registry=registry,
        candidate=candidate,
        verification_receipt=verification,
    )
    _write_json(output / "capability-registry-promoted-3.json", promoted_registry)
    resolved = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=third_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-post-promotion-resolution-3.json", resolved)
    _require(
        resolved.get("resolution_status") == "verified_capability_resolved"
        and resolved.get("implementation_id") == candidate_acquisition.IMPLEMENTATION_ID,
        "promoted candidate-acquisition capability did not resolve exact blocked action",
    )

    qualification = authenticate_nist_ammt_candidate_acquisition_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
    )
    _write_json(
        output / "nist-ammt-candidate-acquisition-policy-qualification.json",
        qualification,
    )
    authorization = candidate_acquisition.build_derived_candidate_authorization(
        qualification=qualification,
        discovery_report=discovery_report,
        predecessor_manifest=manifest,
    )
    _write_json(output / "nist-ammt-derived-candidate-authorization.json", authorization)
    acquisition = candidate_acquisition.execute_derived_candidate_acquisition(
        authorization=authorization,
    )
    _write_json(output / "nist-ammt-calibration-candidate-acquisition.json", acquisition)
    assessment = build_calibration_candidate_bridge_assessment(
        acquisition_report=acquisition,
        predecessor_manifest=manifest,
    )
    _write_json(output / "nist-ammt-calibration-candidate-bridge-assessment.json", assessment)
    _require(
        assessment["experiment_specific_bridge"]["bridge_established"] is False
        and assessment["gate_decision"]["directly_comparable_mds2_rows"] == 0
        and assessment["gate_decision"]["issue_76_exact_target_cells_satisfied"] == 0,
        "candidate assessment improperly promoted scientific comparability",
    )
    next_action = assessment.get("next_action")
    _require(isinstance(next_action, dict), "candidate assessment next action is missing")
    next_action_class = next_action.get("action_class")
    _require(next_action_class == NEXT_ACTION_CLASS, "candidate assessment next action drifted")

    cycle10: dict[str, Any] = {
        "cycle_index": 10,
        "predecessor_cycle_sha256": cycle9["cycle_sha256"],
        "input_blocker": "missing_source_adapter",
        "selected_action_class": candidate_acquisition.ACTION_CLASS,
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
        "implementation_id": candidate_acquisition.IMPLEMENTATION_ID,
        "research_action_resumed": True,
        "network_requests_performed": acquisition["network_requests_performed"],
        "candidate_url_derived_from_discovery": True,
        "full_text_url_derived_from_candidate_page": True,
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "output_next_action_class": next_action_class,
        "new_verified_information": assessment["new_verified_information"],
        "scientific_status_changed": False,
    }
    cycle10["cycle_sha256"] = _canonical_sha(cycle10)
    cycles.append(cycle10)

    fourth_gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=assessment,
        available_action_classes=tuple(_BASE_ACTION_CLASSES)
        + (candidate_acquisition.ACTION_CLASS,),
    )
    fourth_spec = build_capability_specification(fourth_gap)
    fourth_resolution = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=fourth_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-gap-4.json", fourth_gap)
    _write_json(output / "capability-specification-4.json", fourth_spec)
    _write_json(output / "capability-resolution-4.json", fourth_resolution)
    _require(
        fourth_resolution.get("resolution_status") == "no_bounded_candidate_available",
        "reference-chain assessment unexpectedly gained unaudited capability",
    )

    stop = _stop(
        "capability_expansion_required",
        str(next_action_class),
        capability_gap_class=fourth_gap["gap_class"],
        capability_gap_sha256=fourth_gap["capability_gap_sha256_without_self_field"],
        capability_specification_sha256=fourth_spec[
            "capability_specification_sha256_without_self_field"
        ],
        bounded_candidate_discovered=False,
        caller_authored_url_used=False,
        arbitrary_code_generation_performed=False,
    )
    return _finalize(
        output=output,
        manifest=manifest,
        cycles=cycles,
        stop=stop,
        updates={
            "third_capability_candidate_discovered": True,
            "third_capability_candidate_promoted": True,
            "third_capability_verification_sha256": verification[
                "capability_verification_sha256_without_self_field"
            ],
            "third_promoted_capability_registry_sha256": promoted_registry[
                "capability_registry_sha256_without_self_field"
            ],
            "third_research_action_resumed": True,
            "derived_candidate_acquisition_executed": True,
            "derived_candidate_acquisition_sha256": acquisition[
                "report_sha256_without_self_field"
            ],
            "calibration_candidate_bridge_assessment_sha256": assessment[
                "report_sha256_without_self_field"
            ],
            "calibration_methodology_established": assessment["evidence_scope"][
                "digital_camera_in_situ_calibration_methodology_established"
            ],
            "exact_mds2_experiment_identity_established": False,
            "exact_machine_setting_to_calibrated_power_relation_established": False,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "fourth_capability_gap_emitted": True,
            "fourth_capability_candidate_discovered": False,
            "generated_next_action_class": next_action_class,
            "final_blocker": "experiment_identity_reference_chain_capability_not_established",
        },
    )


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionCandidateAcquisitionExtensionError",
    "run_autonomous_production",
]
