"""Fail-closed intake for cross-source physical IN625 LPBF evidence.

Records are admitted only when their source identity, experiment family, machine,
material state, power semantics, calibration semantics, and process coordinate
are already declared by the source registry. Numerical proximity or equal
energy density never creates experimental identity.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from .in625_external_physical_evidence import (
    NIST_STAGE1_TARGETS,
    PhysicalEvidenceRegistryError,
    classify_candidate,
    validate_registry,
)

ALLOWED_RESPONSE_UNITS = {
    "melt_pool_width": "um",
    "melt_pool_depth": "um",
    "melt_pool_length": "um",
    "track_width": "um",
    "track_height": "um",
}


class PhysicalEvidenceIntakeError(ValueError):
    """Raised when a cross-source record violates the provenance contract."""


def _required_string(record: dict[str, Any], key: str, label: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PhysicalEvidenceIntakeError(f"{label} requires non-blank {key}.")
    return value.strip()


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise PhysicalEvidenceIntakeError(f"{label} must be numeric.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PhysicalEvidenceIntakeError(f"{label} must be numeric.") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "finite and positive" if positive else "finite"
        raise PhysicalEvidenceIntakeError(f"{label} must be {qualifier}.")
    return result


def _relative_posix_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise PhysicalEvidenceIntakeError(f"{label} path must be non-blank.")
    text = value.strip()
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        raise PhysicalEvidenceIntakeError(f"{label} path must be relative POSIX.")
    path = PurePosixPath(text)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise PhysicalEvidenceIntakeError(f"{label} path escapes the intake root.")
    return path


def _verify_artifact(binding: Any, root: Path, label: str) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise PhysicalEvidenceIntakeError(f"{label} must be an object.")
    relative = _relative_posix_path(binding.get("path"), label)
    expected_sha = binding.get("sha256")
    expected_size = binding.get("size_bytes")
    if not isinstance(expected_sha, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", expected_sha
    ):
        raise PhysicalEvidenceIntakeError(f"{label}.sha256 is invalid.")
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 0
    ):
        raise PhysicalEvidenceIntakeError(
            f"{label}.size_bytes must be a non-negative integer."
        )

    candidate = root.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise PhysicalEvidenceIntakeError(f"{label} may not reference a symlink.")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PhysicalEvidenceIntakeError(
            f"{label} does not exist: {relative.as_posix()}."
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PhysicalEvidenceIntakeError(f"{label} resolves outside intake root.") from exc
    if not resolved.is_file():
        raise PhysicalEvidenceIntakeError(f"{label} must reference a regular file.")

    payload = resolved.read_bytes()
    observed_sha = hashlib.sha256(payload).hexdigest()
    if observed_sha.lower() != expected_sha.lower():
        raise PhysicalEvidenceIntakeError(f"{label} checksum mismatch.")
    if len(payload) != expected_size:
        raise PhysicalEvidenceIntakeError(f"{label} size mismatch.")
    return {
        "path": relative.as_posix(),
        "sha256": observed_sha,
        "size_bytes": len(payload),
    }


def _candidate_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    validated = validate_registry(registry)
    return {candidate["candidate_id"]: candidate for candidate in validated["candidates"]}


def _declared_process_points(candidate: dict[str, Any]) -> set[tuple[float, float]]:
    return {
        (float(point["laser_power_w"]), float(point["scan_speed_mm_s"]))
        for point in candidate["process_points"]
    }


def _validate_record(
    record: Any,
    index: int,
    candidates: dict[str, dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    label = f"records[{index}]"
    if not isinstance(record, dict):
        raise PhysicalEvidenceIntakeError(f"{label} must be an object.")
    out = dict(record)
    for key in (
        "record_id",
        "candidate_id",
        "experiment_family_id",
        "replication_unit_id",
        "source_locator",
        "machine_id",
        "material",
        "material_state",
        "power_semantics",
        "calibration_binding",
        "response_name",
        "response_unit",
    ):
        out[key] = _required_string(record, key, label)

    candidate = candidates.get(out["candidate_id"])
    if candidate is None:
        raise PhysicalEvidenceIntakeError(
            f"{label} references unknown candidate_id {out['candidate_id']!r}."
        )
    bindings = {
        "experiment_family_id": "experiment_family_id",
        "machine_id": "machine_id",
        "material_state": "material_state",
        "power_semantics": "power_semantics",
        "calibration_binding": "calibration_binding",
    }
    for record_key, candidate_key in bindings.items():
        if out[record_key] != candidate[candidate_key]:
            raise PhysicalEvidenceIntakeError(
                f"{label} {record_key} differs from source registry."
            )
    if out["material"] != "IN625":
        raise PhysicalEvidenceIntakeError(f"{label} material must be exactly IN625.")

    out["laser_power_w"] = _finite(
        record.get("laser_power_w"), f"{label}.laser_power_w", positive=True
    )
    out["scan_speed_mm_s"] = _finite(
        record.get("scan_speed_mm_s"), f"{label}.scan_speed_mm_s", positive=True
    )
    point = (out["laser_power_w"], out["scan_speed_mm_s"])
    declared_points = _declared_process_points(candidate)
    if point not in declared_points:
        raise PhysicalEvidenceIntakeError(
            f"{label} process point {point} is not declared by the source registry."
        )

    out["response_value"] = _finite(
        record.get("response_value"), f"{label}.response_value"
    )
    expected_unit = ALLOWED_RESPONSE_UNITS.get(out["response_name"])
    if expected_unit is None:
        raise PhysicalEvidenceIntakeError(
            f"{label} unsupported response_name {out['response_name']!r}."
        )
    if out["response_unit"] != expected_unit:
        raise PhysicalEvidenceIntakeError(
            f"{label} response_unit must be {expected_unit!r} for {out['response_name']}."
        )

    independent = record.get("independent_physical_replicate")
    if not isinstance(independent, bool):
        raise PhysicalEvidenceIntakeError(
            f"{label}.independent_physical_replicate must be boolean."
        )
    out["independent_physical_replicate"] = independent

    artifact = record.get("source_artifact")
    if candidate["extraction_mode"] == "raw_dataset":
        if artifact is None:
            raise PhysicalEvidenceIntakeError(
                f"{label} raw_dataset evidence requires source_artifact bytes."
            )
        out["source_artifact"] = _verify_artifact(
            artifact, root, f"{label}.source_artifact"
        )
    elif artifact is not None:
        out["source_artifact"] = _verify_artifact(
            artifact, root, f"{label}.source_artifact"
        )

    out["evidence_stratum"] = classify_candidate(candidate)
    out["is_exact_stage1_coordinate"] = point in NIST_STAGE1_TARGETS
    out["eligible_for_issue_76"] = (
        out["evidence_stratum"] == "exact_benchmark_compatible"
        and out["machine_id"] == "nist-ammt"
        and out["material_state"] == "bare_plate"
        and out["power_semantics"] == "achieved_calibrated_actual"
        and out["calibration_binding"] == "authoritative_for_this_experiment"
        and out["is_exact_stage1_coordinate"]
        and independent
    )
    return out


def validate_physical_evidence_records(
    records: Any,
    registry: dict[str, Any],
    intake_root: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate records and report replication, confounding, and #76 support."""
    try:
        candidates = _candidate_map(registry)
    except PhysicalEvidenceRegistryError as exc:
        raise PhysicalEvidenceIntakeError(str(exc)) from exc
    root = Path(intake_root).resolve(strict=True)
    if not isinstance(records, list) or not records:
        raise PhysicalEvidenceIntakeError("records must be a non-empty list.")
    validated = [
        _validate_record(record, index, candidates, root)
        for index, record in enumerate(records)
    ]

    record_ids = [record["record_id"] for record in validated]
    if len(record_ids) != len(set(record_ids)):
        raise PhysicalEvidenceIntakeError("record_id values must be unique.")

    physical_keys: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for record in validated:
        key = (
            record["experiment_family_id"],
            record["replication_unit_id"],
            record["response_name"],
        )
        physical_keys[key].append(record["record_id"])
    overlaps = [
        {
            "experiment_family_id": key[0],
            "replication_unit_id": key[1],
            "response_name": key[2],
            "record_ids": sorted(ids),
        }
        for key, ids in sorted(physical_keys.items())
        if len(ids) > 1
    ]

    stage1_units: dict[tuple[float, float], set[tuple[str, str]]] = {
        target: set() for target in NIST_STAGE1_TARGETS
    }
    for record in validated:
        if record["eligible_for_issue_76"]:
            target = (record["laser_power_w"], record["scan_speed_mm_s"])
            stage1_units[target].add(
                (record["experiment_family_id"], record["replication_unit_id"])
            )
    stage1_cells = []
    for target, required in NIST_STAGE1_TARGETS.items():
        observed = len(stage1_units[target])
        stage1_cells.append(
            {
                "actual_laser_power_w": target[0],
                "scan_speed_mm_s": target[1],
                "required_independent_traces": required,
                "eligible_independent_traces": observed,
                "complete": observed >= required,
            }
        )

    machine_ids = sorted({record["machine_id"] for record in validated})
    material_states = sorted({record["material_state"] for record in validated})
    power_semantics = sorted({record["power_semantics"] for record in validated})
    experiment_families = sorted(
        {record["experiment_family_id"] for record in validated}
    )
    return validated, {
        "record_count": len(validated),
        "independent_experiment_family_count": len(experiment_families),
        "experiment_families": experiment_families,
        "machine_ids": machine_ids,
        "material_states": material_states,
        "power_semantics": power_semantics,
        "duplicate_physical_response_views": overlaps,
        "naive_cross_source_pooling_allowed": (
            len(machine_ids) == 1
            and len(material_states) == 1
            and len(power_semantics) == 1
            and len(experiment_families) == 1
            and not overlaps
        ),
        "required_explicit_model_factors": {
            "machine_id": len(machine_ids) > 1,
            "material_state": len(material_states) > 1,
            "power_semantics": len(power_semantics) > 1,
            "experiment_family_id": len(experiment_families) > 1,
        },
        "issue_76_stage1": {
            "cells": stage1_cells,
            "complete": all(cell["complete"] for cell in stage1_cells),
            "cross_machine_numeric_match_is_eligible": False,
            "energy_density_equivalence_is_eligible": False,
            "repeated_measurements_on_one_track_are_independent": False,
        },
        "scientific_boundary": {
            "source_registry_controls_process_coordinates": True,
            "record_self_declaration_can_upgrade_source_stratum": False,
            "different_machine_settings_can_be_relabelled_as_ammt_calibrated_power": False,
            "duplicate_publication_and_repository_views_can_double_count": False,
        },
    }
