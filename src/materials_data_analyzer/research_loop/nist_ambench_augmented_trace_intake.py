"""Provenance-bound intake for NIST AM-Bench 2018-02 Stage 1 trace augmentation.

This module authenticates bytes and explicit provenance bindings only. It cannot
prove that a self-declared record was physically measured; that boundary is
reported explicitly and scientific status remains Diagnostic.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

SCHEMA_VERSION = "1.0"
CONTRACT_ID = "nist_ambench_2018_02_stage1_augmented_trace_intake"
POWER = "actual_laser_power_w"
SPEED = "scan_speed_mm_s"
TARGET_CELLS = (
    (137.9, 800.0),
    (137.9, 1200.0),
    (179.2, 400.0),
)
TARGET_CELL_IDS = {
    (137.9, 800.0): "stage1_p137_9_v800",
    (137.9, 1200.0): "stage1_p137_9_v1200",
    (179.2, 400.0): "stage1_p179_2_v400",
}
ALLOWED_EVIDENCE_KINDS = {
    "measured_physical_candidate",
    "synthetic_fixture",
    "reference_only",
    "diagnostic",
}
EXPECTED_MEASUREMENT_UNITS = {
    "melt_pool_width_mean": "um",
    "melt_pool_depth_mean": "um",
}
REQUIRED_STATUS_KEYS = (
    "deviation_observed",
    "interruption_observed",
    "censored",
    "failed_acquisition",
    "saturated",
    "excluded",
)
PROCESS_REQUIRED_STRINGS = (
    "sample_id",
    "trace_id",
    "condition_id",
    "build_id",
    "run_id",
    "block_id",
    "controlled_process_settings_id",
    "machine_id",
    "optics_config_id",
    "calibration_id",
    "calibration_reference",
    "software_config_id",
    "material",
    "material_lot_id",
    "geometry_id",
    "preparation_history_id",
    "spatial_location",
    "evidence_kind",
    "source_kind",
    "source_authority",
    "source_record_id",
    "source_reference",
)
CHAR_REQUIRED_STRINGS = (
    "sample_id",
    "trace_id",
    "method",
    "acquisition_settings_id",
    "preprocessing_id",
    "exclusion_policy_id",
    "measurement_schema_id",
    "evidence_kind",
    "source_kind",
    "source_authority",
    "source_record_id",
    "source_reference",
)


class IntakeValidationError(ValueError):
    """Raised when augmented evidence fails closed validation."""


@dataclass(frozen=True)
class VerifiedArtifact:
    path: str
    sha256: str
    size_bytes: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required_string(record: dict[str, Any], key: str, label: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IntakeValidationError(f"{label} requires non-blank {key}.")
    return value.strip()


def _finite_positive(record: dict[str, Any], key: str, label: str) -> float:
    value = record.get(key)
    if isinstance(value, bool):
        raise IntakeValidationError(f"{label} {key} must be numeric.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise IntakeValidationError(f"{label} {key} must be numeric.") from exc
    if not math.isfinite(result) or result <= 0:
        raise IntakeValidationError(f"{label} {key} must be finite and positive.")
    return result


def _validate_status(value: Any, label: str) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise IntakeValidationError(f"{label} status must be an object.")
    extra = sorted(set(value) - set(REQUIRED_STATUS_KEYS))
    missing = [key for key in REQUIRED_STATUS_KEYS if key not in value]
    if missing or extra:
        raise IntakeValidationError(
            f"{label} status schema mismatch; missing={missing}, extra={extra}."
        )
    result: dict[str, bool] = {}
    for key in REQUIRED_STATUS_KEYS:
        if not isinstance(value[key], bool):
            raise IntakeValidationError(f"{label} status {key} must be boolean.")
        result[key] = value[key]
    return result


def _relative_artifact_path(path_text: Any, label: str) -> PurePosixPath:
    if not isinstance(path_text, str) or not path_text.strip():
        raise IntakeValidationError(f"{label} artifact path must be non-blank.")
    text = path_text.strip()
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        raise IntakeValidationError(
            f"{label} artifact path must use a relative POSIX path."
        )
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise IntakeValidationError(f"{label} artifact path escapes the intake root.")
    return path


class _ArtifactVerifier:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self._cache: dict[str, VerifiedArtifact] = {}

    def verify(self, binding: Any, label: str) -> VerifiedArtifact:
        if not isinstance(binding, dict):
            raise IntakeValidationError(f"{label} raw_artifact must be an object.")
        path = _relative_artifact_path(binding.get("path"), label)
        expected_sha = binding.get("sha256")
        expected_size = binding.get("size_bytes")
        if not isinstance(expected_sha, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_sha
        ):
            raise IntakeValidationError(f"{label} raw_artifact sha256 is invalid.")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise IntakeValidationError(
                f"{label} raw_artifact size_bytes must be a non-negative integer."
            )

        key = path.as_posix()
        cached = self._cache.get(key)
        if cached is None:
            candidate = self.root.joinpath(*path.parts)
            if candidate.is_symlink():
                raise IntakeValidationError(
                    f"{label} artifact path may not be a symlink."
                )
            try:
                resolved = candidate.resolve(strict=True)
            except FileNotFoundError as exc:
                raise IntakeValidationError(
                    f"{label} artifact does not exist: {key}."
                ) from exc
            try:
                resolved.relative_to(self.root)
            except ValueError as exc:
                raise IntakeValidationError(
                    f"{label} artifact resolves outside the intake root."
                ) from exc
            if not resolved.is_file():
                raise IntakeValidationError(f"{label} artifact is not a regular file.")
            data = resolved.read_bytes()
            cached = VerifiedArtifact(
                path=key, sha256=_sha256(data), size_bytes=len(data)
            )
            self._cache[key] = cached

        if cached.sha256.lower() != expected_sha.lower():
            raise IntakeValidationError(f"{label} raw_artifact checksum mismatch.")
        if cached.size_bytes != expected_size:
            raise IntakeValidationError(f"{label} raw_artifact size mismatch.")
        return cached

    @property
    def artifacts(self) -> list[VerifiedArtifact]:
        return [self._cache[key] for key in sorted(self._cache)]


def _canonical_manifest(manifest: dict[str, Any]) -> bytes:
    normalized = json.loads(json.dumps(manifest))
    for key in ("process_records", "characterization_records"):
        records = normalized.get(key)
        if isinstance(records, list):
            for record in records:
                if key == "characterization_records" and isinstance(record, dict):
                    measurements = record.get("measurements")
                    if isinstance(measurements, list):
                        measurements.sort(key=lambda item: str(item.get("name", "")))
            records.sort(
                key=lambda record: (
                    str(record.get("sample_id", "")),
                    str(record.get("trace_id", "")),
                )
            )
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def load_manifest_bytes(
    manifest_path: str | Path,
    intake_root: str | Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    root = Path(intake_root).resolve(strict=True)
    source = Path(manifest_path)
    if not source.is_absolute():
        source = root / source
    try:
        resolved = source.resolve(strict=True)
    except FileNotFoundError as exc:
        raise IntakeValidationError(f"Manifest not found: {source}.") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise IntakeValidationError(
            "Manifest must be contained by the intake root."
        ) from exc
    if source.is_symlink() or not resolved.is_file():
        raise IntakeValidationError("Manifest must be a regular, non-symlink file.")
    raw = resolved.read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntakeValidationError("Manifest must be valid UTF-8 JSON.") from exc
    if not isinstance(manifest, dict):
        raise IntakeValidationError("Manifest root must be a JSON object.")
    return manifest, {
        "raw_manifest_sha256": _sha256(raw),
        "canonical_manifest_sha256": _sha256(_canonical_manifest(manifest)),
    }


def _validate_artifact_binding(
    record: dict[str, Any],
    verifier: _ArtifactVerifier,
    label: str,
) -> VerifiedArtifact:
    return verifier.verify(record.get("raw_artifact"), label)


def _validate_evidence(record: dict[str, Any], label: str) -> None:
    evidence_kind = _required_string(record, "evidence_kind", label)
    if evidence_kind not in ALLOWED_EVIDENCE_KINDS:
        raise IntakeValidationError(
            f"{label} evidence_kind must be one of {sorted(ALLOWED_EVIDENCE_KINDS)}."
        )
    _required_string(record, "source_kind", label)
    _required_string(record, "source_authority", label)
    _required_string(record, "source_record_id", label)
    _required_string(record, "source_reference", label)


def _validate_process_record(
    record: Any,
    index: int,
    verifier: _ArtifactVerifier,
) -> dict[str, Any]:
    label = f"process_records[{index}]"
    if not isinstance(record, dict):
        raise IntakeValidationError(f"{label} must be an object.")
    out = dict(record)
    for key in PROCESS_REQUIRED_STRINGS:
        out[key] = _required_string(record, key, label)
    _validate_evidence(out, label)
    if out["material"] != "IN625":
        raise IntakeValidationError(
            f"{label} material must be IN625 for this contract."
        )
    if record.get("power_unit") != "W":
        raise IntakeValidationError(f"{label} power_unit must be exactly 'W'.")
    if record.get("speed_unit") != "mm/s":
        raise IntakeValidationError(f"{label} speed_unit must be exactly 'mm/s'.")
    target_power = _finite_positive(record, "target_laser_power_w", label)
    achieved_power = _finite_positive(record, "achieved_laser_power_w", label)
    speed = _finite_positive(record, "scan_speed_mm_s", label)
    target_key = (target_power, speed)
    if target_key not in TARGET_CELL_IDS:
        raise IntakeValidationError(
            f"{label} condition {(target_power, speed)} is not an approved Stage 1 cell."
        )
    if out["condition_id"] != TARGET_CELL_IDS[target_key]:
        raise IntakeValidationError(
            f"{label} condition_id does not match the predeclared Stage 1 cell."
        )
    out["target_laser_power_w"] = target_power
    out["achieved_laser_power_w"] = achieved_power
    out["scan_speed_mm_s"] = speed
    out["status"] = _validate_status(record.get("status"), label)
    artifact = _validate_artifact_binding(out, verifier, label)
    out["raw_artifact"] = {
        "path": artifact.path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }
    return out


def _validate_measurements(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise IntakeValidationError(f"{label} measurements must be a non-empty list.")
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for i, item in enumerate(value):
        item_label = f"{label} measurements[{i}]"
        if not isinstance(item, dict):
            raise IntakeValidationError(f"{item_label} must be an object.")
        name = _required_string(item, "name", item_label)
        unit = _required_string(item, "unit", item_label)
        expected_unit = EXPECTED_MEASUREMENT_UNITS.get(name)
        if expected_unit is not None and unit != expected_unit:
            raise IntakeValidationError(
                f"{item_label} unit must be exactly {expected_unit!r} for {name}."
            )
        if name in names:
            raise IntakeValidationError(
                f"{label} contains duplicate measurement name {name}."
            )
        names.add(name)
        raw_value = item.get("value")
        if isinstance(raw_value, bool):
            raise IntakeValidationError(f"{item_label} value must be numeric.")
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise IntakeValidationError(f"{item_label} value must be numeric.") from exc
        if not math.isfinite(numeric):
            raise IntakeValidationError(f"{item_label} value must be finite.")
        result.append({"name": name, "value": numeric, "unit": unit})
    return sorted(result, key=lambda item: item["name"])


def _validate_characterization_record(
    record: Any,
    index: int,
    verifier: _ArtifactVerifier,
) -> dict[str, Any]:
    label = f"characterization_records[{index}]"
    if not isinstance(record, dict):
        raise IntakeValidationError(f"{label} must be an object.")
    out = dict(record)
    for key in CHAR_REQUIRED_STRINGS:
        out[key] = _required_string(record, key, label)
    _validate_evidence(out, label)
    out["status"] = _validate_status(record.get("status"), label)
    out["measurements"] = _validate_measurements(record.get("measurements"), label)
    artifact = _validate_artifact_binding(out, verifier, label)
    out["raw_artifact"] = {
        "path": artifact.path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }
    return out


def _ensure_unique(records: list[dict[str, Any]], label: str) -> None:
    for key in ("sample_id", "trace_id"):
        values = [record[key] for record in records]
        if len(values) != len(set(values)):
            raise IntakeValidationError(f"{label} contains duplicate {key} values.")
    pairs = [(record["sample_id"], record["trace_id"]) for record in records]
    if len(pairs) != len(set(pairs)):
        raise IntakeValidationError(
            f"{label} contains duplicate sample_id/trace_id pairs."
        )


def _status_union(
    process_status: dict[str, bool],
    char_status: dict[str, bool],
) -> dict[str, bool]:
    return {
        key: bool(process_status[key] or char_status[key])
        for key in REQUIRED_STATUS_KEYS
    }


def _record_is_successful(status: dict[str, bool]) -> bool:
    return not any(status[key] for key in REQUIRED_STATUS_KEYS)


def validate_augmented_manifest(
    manifest_path: str | Path,
    intake_root: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest, manifest_hashes = load_manifest_bytes(manifest_path, intake_root)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise IntakeValidationError(
            f"schema_version must be exactly {SCHEMA_VERSION!r}."
        )
    if manifest.get("contract_id") != CONTRACT_ID:
        raise IntakeValidationError(f"contract_id must be exactly {CONTRACT_ID!r}.")
    process_raw = manifest.get("process_records")
    char_raw = manifest.get("characterization_records")
    if not isinstance(process_raw, list) or not process_raw:
        raise IntakeValidationError("process_records must be a non-empty list.")
    if not isinstance(char_raw, list) or not char_raw:
        raise IntakeValidationError(
            "characterization_records must be a non-empty list."
        )

    verifier = _ArtifactVerifier(Path(intake_root))
    process = [
        _validate_process_record(record, i, verifier)
        for i, record in enumerate(process_raw)
    ]
    chars = [
        _validate_characterization_record(record, i, verifier)
        for i, record in enumerate(char_raw)
    ]
    _ensure_unique(process, "process_records")
    _ensure_unique(chars, "characterization_records")

    process_by_key = {(r["sample_id"], r["trace_id"]): r for r in process}
    chars_by_key = {(r["sample_id"], r["trace_id"]): r for r in chars}
    if set(process_by_key) != set(chars_by_key):
        missing_char = sorted(set(process_by_key) - set(chars_by_key))
        missing_process = sorted(set(chars_by_key) - set(process_by_key))
        raise IntakeValidationError(
            "Process-characterization identity sets must match exactly; "
            f"missing_characterization={missing_char}, missing_process={missing_process}."
        )

    achieved_by_condition: dict[str, set[float]] = {}
    for record in process:
        achieved_by_condition.setdefault(record["condition_id"], set()).add(
            record["achieved_laser_power_w"]
        )
    incoherent = {
        key: sorted(values)
        for key, values in achieved_by_condition.items()
        if len(values) != 1
    }
    if incoherent:
        raise IntakeValidationError(
            "Each condition_id must have one explicit achieved calibrated power; "
            f"incoherent={incoherent}."
        )

    joined: list[dict[str, Any]] = []
    for key in sorted(process_by_key):
        p = process_by_key[key]
        c = chars_by_key[key]
        status = _status_union(p["status"], c["status"])
        evidence_kinds = {p["evidence_kind"], c["evidence_kind"]}
        measured_candidate = evidence_kinds == {"measured_physical_candidate"}
        structural_eligible = _record_is_successful(status)
        joined.append(
            {
                "sample_id": p["sample_id"],
                "trace_id": p["trace_id"],
                "case_id": p["condition_id"],
                "target_laser_power_w": p["target_laser_power_w"],
                POWER: p["achieved_laser_power_w"],
                SPEED: p["scan_speed_mm_s"],
                "build_id": p["build_id"],
                "run_id": p["run_id"],
                "block_id": p["block_id"],
                "material": p["material"],
                "material_lot_id": p["material_lot_id"],
                "geometry_id": p["geometry_id"],
                "preparation_history_id": p["preparation_history_id"],
                "spatial_location": p["spatial_location"],
                "machine_id": p["machine_id"],
                "optics_config_id": p["optics_config_id"],
                "calibration_id": p["calibration_id"],
                "calibration_reference": p["calibration_reference"],
                "software_config_id": p["software_config_id"],
                "controlled_process_settings_id": p[
                    "controlled_process_settings_id"
                ],
                "process_evidence_kind": p["evidence_kind"],
                "characterization_evidence_kind": c["evidence_kind"],
                "process_source_kind": p["source_kind"],
                "characterization_source_kind": c["source_kind"],
                "process_source_authority": p["source_authority"],
                "characterization_source_authority": c["source_authority"],
                "process_source_record_id": p["source_record_id"],
                "characterization_source_record_id": c["source_record_id"],
                "process_source_reference": p["source_reference"],
                "characterization_source_reference": c["source_reference"],
                "process_artifact_path": p["raw_artifact"]["path"],
                "process_artifact_sha256": p["raw_artifact"]["sha256"],
                "process_artifact_size_bytes": p["raw_artifact"]["size_bytes"],
                "characterization_method": c["method"],
                "characterization_acquisition_settings_id": c[
                    "acquisition_settings_id"
                ],
                "characterization_preprocessing_id": c["preprocessing_id"],
                "characterization_exclusion_policy_id": c["exclusion_policy_id"],
                "characterization_measurement_schema_id": c["measurement_schema_id"],
                "characterization_measurements_json": json.dumps(
                    c["measurements"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "characterization_artifact_path": c["raw_artifact"]["path"],
                "characterization_artifact_sha256": c["raw_artifact"]["sha256"],
                "characterization_artifact_size_bytes": c["raw_artifact"][
                    "size_bytes"
                ],
                **{f"status__{name}": value for name, value in status.items()},
                "structural_audit_eligible": structural_eligible,
                "declared_measured_physical_candidate": measured_candidate,
                "physical_origin_authenticated_by_software": False,
            }
        )

    joined_table = pd.DataFrame(joined).sort_values(
        ["case_id", "sample_id", "trace_id"]
    ).reset_index(drop=True)

    target_counts: dict[str, dict[str, int]] = {}
    for cell in TARGET_CELLS:
        cell_id = TARGET_CELL_IDS[cell]
        mask = joined_table["case_id"].eq(cell_id)
        structural = mask & joined_table["structural_audit_eligible"]
        measured = structural & joined_table["declared_measured_physical_candidate"]
        target_counts[cell_id] = {
            "total_traceable_records": int(mask.sum()),
            "structural_eligible_records": int(structural.sum()),
            "declared_measured_physical_candidates": int(measured.sum()),
            "software_authenticated_physical_records": 0,
        }

    stage1_structural_complete = all(
        value["structural_eligible_records"] >= 3 for value in target_counts.values()
    )
    declared_measured_complete = all(
        value["declared_measured_physical_candidates"] >= 3
        for value in target_counts.values()
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "status": "validated",
        "evidence_level": "Diagnostic",
        **manifest_hashes,
        "canonical_ordering": {
            "records": ["case_id", "sample_id", "trace_id"],
            "canonical_manifest_record_arrays_sorted_by": ["sample_id", "trace_id"],
            "raw_manifest_sha256_is_byte_order_sensitive": True,
        },
        "identity_validation": {
            "process_record_count": len(process),
            "characterization_record_count": len(chars),
            "one_to_one_join": True,
            "row_order_join_used": False,
            "filename_join_used": False,
        },
        "artifact_validation": {
            "verified_artifact_count": len(verifier.artifacts),
            "artifacts": [
                {
                    "path": artifact.path,
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in verifier.artifacts
            ],
            "bytes_read_once_per_unique_artifact": True,
        },
        "stage1": {
            "required_cells": [
                {
                    "condition_id": TARGET_CELL_IDS[cell],
                    "target_laser_power_w": cell[0],
                    "scan_speed_mm_s": cell[1],
                    "minimum_valid_trace_count": 3,
                }
                for cell in TARGET_CELLS
            ],
            "counts": target_counts,
            "structural_trace_requirement_complete": stage1_structural_complete,
            "declared_measured_candidate_requirement_complete": (
                declared_measured_complete
            ),
            "physical_origin_authenticated_by_software": False,
            "scientific_stage1_complete": False,
        },
        "scientific_boundary": {
            "self_declared_physical_metadata_is_independent_proof": False,
            "software_authenticates": [
                "manifest bytes and canonical binding",
                "artifact bytes, sha256, and size",
                "root containment",
                "schema and explicit units",
                "sample_id/trace_id one-to-one process-characterization identity",
                "predeclared Stage 1 condition assignment",
                (
                    "preservation of deviation/interruption/censor/failure/"
                    "saturation/exclusion status"
                ),
            ],
            "software_does_not_authenticate": [
                "physical origin of a self-declared measurement",
                "instrument operation",
                "scientific validity of the reported measurement values",
                "causal or predictive claims",
            ],
            "issue_76_may_be_closed_by_this_report_alone": False,
        },
        "software_validation": {
            "network_access_performed": False,
            "model_trained": False,
            "response_values_generated": False,
            "optimization_performed": False,
            "unit_conversion_performed": False,
            "silent_exclusion_performed": False,
        },
    }
    return joined_table, report


def combine_with_frozen_baseline(
    baseline: pd.DataFrame,
    stage1_joined: pd.DataFrame,
) -> pd.DataFrame:
    required_baseline = {"sample_id", "case_id", POWER, SPEED}
    missing = sorted(required_baseline - set(baseline.columns))
    if missing:
        raise IntakeValidationError(
            f"Frozen baseline is missing required columns: {missing}."
        )
    if len(baseline) != 10:
        raise IntakeValidationError("Frozen NIST baseline must contain exactly 10 traces.")
    if baseline["sample_id"].astype(str).duplicated().any():
        raise IntakeValidationError("Frozen baseline sample_id values must be unique.")
    if stage1_joined["sample_id"].astype(str).duplicated().any():
        raise IntakeValidationError("Stage 1 sample_id values must be unique.")
    overlap = sorted(
        set(baseline["sample_id"].astype(str))
        & set(stage1_joined["sample_id"].astype(str))
    )
    if overlap:
        raise IntakeValidationError(
            f"Stage 1 sample_id values collide with frozen baseline: {overlap}."
        )

    baseline_copy = baseline.copy()
    baseline_copy["evidence_origin"] = "frozen_nist_baseline"
    baseline_copy["structural_audit_eligible"] = True
    baseline_copy["declared_measured_physical_candidate"] = True
    baseline_copy["physical_origin_authenticated_by_software"] = False
    stage1_copy = stage1_joined.copy()
    stage1_copy["evidence_origin"] = "augmented_stage1_intake"

    combined = pd.concat([baseline_copy, stage1_copy], ignore_index=True, sort=False)
    return combined.sort_values(
        ["case_id", "sample_id"], kind="mergesort"
    ).reset_index(drop=True)


def structural_audit_input(augmented: pd.DataFrame) -> pd.DataFrame:
    if "structural_audit_eligible" not in augmented.columns:
        raise IntakeValidationError(
            "Augmented table lacks structural_audit_eligible status."
        )
    selected = augmented.loc[augmented["structural_audit_eligible"].eq(True)].copy()
    return selected.sort_values(
        ["case_id", "sample_id"], kind="mergesort"
    ).reset_index(drop=True)


def deterministic_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
