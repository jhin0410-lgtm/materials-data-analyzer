"""Extend the proven autonomous IN625 core with exact NIST mds2-2923 acquisition.

The original production driver remains the audited core for Zenodo acquisition, typed
registration, quality review, and the physical-comparability gate.  This wrapper runs that
core through its generated comparability result, then executes NIST acquisition only when the
exact next action is mds2-2923 geometry evidence and a separately mission-pinned NIST policy
qualifies.  The extension therefore adds capability without turning the core into a generic
network dispatcher.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .autonomous_production_driver import (
    run_autonomous_production as run_base_autonomous_production,
)
from .in625_physical_comparability_assessment import (
    ACTION_CLASS as COMPARABILITY_ACTION_CLASS,
)
from .nist_mds2_2923_network_policy import (
    ACTION_CLASS as NIST_ACQUISITION_ACTION_CLASS,
    CANDIDATE_ID as NIST_CANDIDATE_ID,
    POLICY_ID as NIST_POLICY_ID,
    authenticate_nist_mds2_2923_network_policy,
)
from .nist_mds2_2923_post_acquisition_rediagnosis import (
    NEXT_ACTION_CLASS as POST_NIST_NEXT_ACTION_CLASS,
    build_nist_mds2_2923_post_acquisition_rediagnosis,
)
from .nist_mds2_2923_production_acquisition import (
    build_nist_mds2_2923_network_authorization,
    execute_authorized_nist_mds2_2923_acquisition,
)
from .nist_mds2_2923_scientific_intake import audit_mds2_2923

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.2"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.2"
NIST_POLICY_PATH = "configs/research/nist_mds2_2923_network_acquisition_policy.v1.json"
NIST_FRONTIER_PATH = "configs/research/in625_external_physical_source_frontier.v1.json"

_AVAILABLE_ACTION_CLASSES = (
    "external_evidence_search",
    COMPARABILITY_ACTION_CLASS,
    NIST_ACQUISITION_ACTION_CLASS,
)


class AutonomousProductionNistExtensionError(ValueError):
    """Raised when the NIST production extension cannot preserve exact authority."""


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionNistExtensionError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousProductionNistExtensionError(f"{field} root must be an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionNistExtensionError(message)


def _resolved_output(root: Path, output_root: str | Path) -> Path:
    path = Path(output_root).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionNistExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return path


def _maximum_cycle_stop(next_action_class: str) -> dict[str, Any]:
    return {
        "status": "stopped",
        "reason_code": "maximum_cycles_reached",
        "requested_action_class": next_action_class,
        "available_production_action_classes": list(_AVAILABLE_ACTION_CLASSES),
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }


def _bounded_capability_stop(next_action_class: str) -> dict[str, Any]:
    _require(
        next_action_class not in _AVAILABLE_ACTION_CLASSES,
        "bounded stop received an action already implemented by the NIST production extension",
    )
    return {
        "status": "stopped",
        "reason_code": "registered_capability_unavailable_for_current_next_action",
        "requested_action_class": next_action_class,
        "available_production_action_classes": list(_AVAILABLE_ACTION_CLASSES),
        "scope": "exact_current_autonomous_production_capability_set",
        "global_evidence_unavailability_claimed": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 4,
) -> dict[str, Any]:
    """Run the production core and, when generated, exact NIST cycle 3."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 8
    ):
        raise AutonomousProductionNistExtensionError(
            "max_cycles must be an integer from 1 to 8"
        )

    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionNistExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    observed_mission_sha = hashlib.sha256(mission.read_bytes()).hexdigest()
    _require(
        observed_mission_sha == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )

    # Preserve the already-proven core.  Cycle 2 executes the comparability gate and stops
    # by cycle budget before the old driver's intentionally unavailable cycle-3 placeholder.
    base_cycles = min(max_cycles, 2)
    base_manifest = run_base_autonomous_production(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=base_cycles,
    )
    if max_cycles <= 2:
        return base_manifest

    output = _resolved_output(root, output_root)
    base_manifest = _read_json(
        output / "autonomous-production-manifest.json",
        "base autonomous production manifest",
    )
    comparability = _read_json(
        output / "physical-comparability-assessment.json",
        "physical comparability assessment",
    )
    _require(
        base_manifest.get("generated_next_action_class")
        == NIST_ACQUISITION_ACTION_CLASS,
        "base production result did not generate exact NIST acquisition action",
    )
    _require(
        base_manifest.get("preferred_geometry_candidate_id") == NIST_CANDIDATE_ID,
        "base production result selected an unexpected NIST candidate",
    )
    _require(
        comparability.get("next_action", {}).get("action_class")
        == NIST_ACQUISITION_ACTION_CLASS,
        "comparability assessment did not generate exact NIST acquisition action",
    )
    _require(
        comparability.get("next_action", {}).get("candidate_id") == NIST_CANDIDATE_ID,
        "comparability assessment NIST candidate drifted",
    )
    cycles = base_manifest.get("cycles")
    _require(isinstance(cycles, list) and len(cycles) == 2, "base cycle history drifted")

    policy_path = (root / NIST_POLICY_PATH).resolve(strict=True)
    frontier_path = (root / NIST_FRONTIER_PATH).resolve(strict=True)
    qualification = authenticate_nist_mds2_2923_network_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        policy_path=policy_path,
        frontier_path=frontier_path,
    )
    _require(
        qualification["network_access_performed"] is False,
        "NIST policy qualification claimed prior network access",
    )
    _write_json(output / "nist-network-policy-qualification.json", qualification)

    authorization = build_nist_mds2_2923_network_authorization(qualification)
    _require(
        authorization["network_access_performed"] is False,
        "NIST authorization claimed prior network access",
    )
    _write_json(output / "nist-network-authorization.json", authorization)

    nist_output = output / "nist-mds2-2923"
    acquisition = execute_authorized_nist_mds2_2923_acquisition(
        authorization=authorization,
        output_root=nist_output,
    )
    _write_json(output / "nist-network-acquisition-receipt.json", acquisition)
    _require(
        acquisition["network_requests_performed"] == 3,
        "NIST production network path did not use exactly three requests",
    )
    _require(
        acquisition["all_acquisition_provenance_authenticated"] is True,
        "NIST acquisition provenance did not authenticate",
    )

    artifact_paths = acquisition.get("artifact_paths")
    _require(isinstance(artifact_paths, Mapping), "NIST artifact path map is missing")
    readme_path = Path(str(artifact_paths.get("2923_README.txt"))).resolve(strict=True)
    workbook_path = Path(
        str(artifact_paths.get("Master_TrackList_Measurements.xlsx"))
    ).resolve(strict=True)
    metadata_path = Path(str(acquisition.get("metadata_path"))).resolve(strict=True)
    for path in (readme_path, workbook_path, metadata_path):
        try:
            path.relative_to(output)
        except ValueError as exc:
            raise AutonomousProductionNistExtensionError(
                "NIST acquired evidence escaped production output root"
            ) from exc

    intake = audit_mds2_2923(
        workbook_bytes=workbook_path.read_bytes(),
        readme_bytes=readme_path.read_bytes(),
        nerdm_metadata_bytes=metadata_path.read_bytes(),
    )
    _require(
        intake["in625_inventory"]["measurement_row_count"] == 178,
        "NIST scientific intake measurement-row count drifted",
    )
    _require(
        intake["in625_inventory"]["physical_track_count"] == 106,
        "NIST scientific intake physical-track count drifted",
    )
    _require(
        intake["issue_76"]["eligible"] is False
        and intake["issue_76"]["exact_target_cells_satisfied"] == 0,
        "NIST intake improperly promoted Issue #76",
    )
    _require(
        intake["measurement_semantics"]["calibration_conversion_performed"] is False,
        "NIST intake performed prohibited calibration conversion",
    )
    _write_json(output / "nist-scientific-intake.json", intake)

    rediagnosis = build_nist_mds2_2923_post_acquisition_rediagnosis(
        acquisition_receipt=acquisition,
        scientific_intake=intake,
    )
    _write_json(output / "nist-post-acquisition-rediagnosis.json", rediagnosis)
    _require(
        rediagnosis["next_action"]["action_class"] == POST_NIST_NEXT_ACTION_CLASS,
        "post-NIST re-diagnosis generated unexpected next action",
    )

    cycle2 = cycles[-1]
    cycle3: dict[str, Any] = {
        "cycle_index": 3,
        "predecessor_cycle_sha256": cycle2["cycle_sha256"],
        "input_blocker": "response_compatible_geometry_evidence_not_acquired",
        "selected_action_class": NIST_ACQUISITION_ACTION_CLASS,
        "handler": "nist_mds2_2923_exact_pdr_acquire_and_scientific_intake",
        "capability_available": True,
        "candidate_id": NIST_CANDIDATE_ID,
        "network_policy_id": NIST_POLICY_ID,
        "network_policy_sha256": qualification["policy_sha256"],
        "network_authorization_sha256": authorization["authorization_sha256"],
        "network_acquisition_receipt_sha256": acquisition["receipt_sha256"],
        "scientific_intake_sha256": intake["report_sha256_without_self_field"],
        "measurement_row_count": 178,
        "dataset_local_physical_track_count": 106,
        "issue_76_exact_target_cells_satisfied": 0,
        "calibration_conversion_performed": False,
        "cross_machine_pooling_performed": False,
        "output_blocker": rediagnosis["current_blocker"]["code"],
        "output_next_action_class": rediagnosis["next_action"]["action_class"],
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle3["cycle_sha256"] = _canonical_sha(cycle3)
    cycles.append(cycle3)

    if max_cycles < 4:
        stop = _maximum_cycle_stop(rediagnosis["next_action"]["action_class"])
    else:
        stop = _bounded_capability_stop(rediagnosis["next_action"]["action_class"])
        cycle4: dict[str, Any] = {
            "cycle_index": 4,
            "predecessor_cycle_sha256": cycle3["cycle_sha256"],
            "input_blocker": rediagnosis["current_blocker"]["code"],
            "selected_action_class": rediagnosis["next_action"]["action_class"],
            "capability_available": False,
            "eligible_evidence_lanes": rediagnosis["next_action"][
                "eligible_evidence_lanes"
            ],
            "paper_evidence_role": rediagnosis["next_action"]["paper_evidence_role"],
            "stop_reason_code": stop["reason_code"],
            "global_evidence_unavailability_claimed": False,
            "new_verified_information": False,
            "scientific_status_changed": False,
        }
        cycle4["cycle_sha256"] = _canonical_sha(cycle4)
        cycles.append(cycle4)

    manifest = dict(base_manifest)
    manifest.pop("manifest_sha256", None)
    manifest.update(
        {
            "schema_version": AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
            "policy_version": AUTONOMOUS_PRODUCTION_POLICY_VERSION,
            "cycles": cycles,
            "stop": stop,
            "nist_mds2_2923_policy_sha256": qualification["policy_sha256"],
            "nist_mds2_2923_metadata_sha256": acquisition["metadata_sha256"],
            "nist_mds2_2923_acquisition_receipt_sha256": acquisition[
                "receipt_sha256"
            ],
            "nist_mds2_2923_scientific_intake_sha256": intake[
                "report_sha256_without_self_field"
            ],
            "nist_mds2_2923_measurement_row_count": 178,
            "nist_mds2_2923_physical_track_count": 106,
            "nist_mds2_2923_machine_measurement_counts": {
                "AMMT": 34,
                "EOS M270": 144,
            },
            "nist_mds2_2923_machine_physical_track_counts": {
                "AMMT": 34,
                "EOS M270": 72,
            },
            "response_compatible_geometry_evidence_acquired": True,
            "geometry_condition_mapping_established": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "calibration_conversion_performed": False,
            "cross_machine_pooling_performed": False,
            "paper_and_other_source_lanes_remain_allowed": True,
            "paper_evidence_promoted_to_row_level_authority": False,
            "final_blocker": rediagnosis["current_blocker"]["code"],
            "generated_next_action_class": rediagnosis["next_action"]["action_class"],
            "scientific_status_changed": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
        }
    )
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    _write_json(output / "bounded-stop.json", stop)
    _write_json(output / "autonomous-production-manifest.json", manifest)
    return manifest


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionNistExtensionError",
    "run_autonomous_production",
]
