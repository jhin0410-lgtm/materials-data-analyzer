"""Checksum-bound acquisition entry point for the public Co-Cr corrosion dataset."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from platform_core.output_safety import transactional_output_directory

from .zenodo_evidence_acquisition import (
    AUTO,
    acquire_zenodo_files,
    fetch_zenodo_record_metadata,
    normalize_zenodo_record_metadata,
    plan_zenodo_file_acquisition,
)

SCHEMA_VERSION = "1.0"


class CocrCorrosionZenodoEpisodeError(ValueError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CocrCorrosionZenodoEpisodeError(f"{field} must be exact non-empty text")
    return value


def validate_cocr_config(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CocrCorrosionZenodoEpisodeError("config must be object")
    if value.get("schema_version") != "1.0":
        raise CocrCorrosionZenodoEpisodeError("schema_version mismatch")
    zenodo = value.get("zenodo")
    boundaries = value.get("scientific_boundaries")
    if not isinstance(zenodo, Mapping) or not isinstance(boundaries, Mapping):
        raise CocrCorrosionZenodoEpisodeError("zenodo/boundaries must be objects")
    record_id = zenodo.get("record_id")
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise CocrCorrosionZenodoEpisodeError("record_id must be positive integer")
    selected = zenodo.get("selected_files")
    if not isinstance(selected, Mapping) or len(selected) != 6:
        raise CocrCorrosionZenodoEpisodeError("selected_files must contain six files")
    normalized_files: dict[str, str] = {}
    for name, digest in selected.items():
        filename = _text(name, "selected file name")
        checksum = _text(digest, f"MD5 for {filename}").lower()
        if len(checksum) != 32 or any(ch not in "0123456789abcdef" for ch in checksum):
            raise CocrCorrosionZenodoEpisodeError(f"invalid MD5 for {filename}")
        normalized_files[filename] = checksum
    required_false = {
        "control_and_wear_repeat_independence_assumed",
        "reference_electrode_assumed",
        "equivalent_circuit_model_assumed",
        "converted_lpr_treated_as_independent_measurement",
        "microscopy_surface_linkage_assumed",
        "automatic_scientific_promotion",
        "model_training_authorized_on_acquisition",
    }
    for field in required_false:
        if boundaries.get(field) is not False:
            raise CocrCorrosionZenodoEpisodeError(f"{field} must remain false")
    return {
        "schema_version": "1.0",
        "episode_id": _text(value.get("episode_id"), "episode_id"),
        "research_question": _text(value.get("research_question"), "research_question"),
        "zenodo": {
            "record_id": record_id,
            "version_doi": _text(zenodo.get("version_doi"), "version_doi").lower(),
            "selected_files": normalized_files,
        },
        "scientific_boundaries": dict(boundaries),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_cocr_corrosion_zenodo_episode(
    *, config: Mapping[str, Any], output_dir: str | Path, overwrite: bool = False
) -> dict[str, Any]:
    cfg = validate_cocr_config(config)
    zenodo = cfg["zenodo"]
    selected_names = list(zenodo["selected_files"])
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        recognized_markers=("cocr_corrosion_episode_summary.json",),
    ) as staging:
        metadata_bytes, metadata_url = fetch_zenodo_record_metadata(zenodo["record_id"])
        normalized = normalize_zenodo_record_metadata(
            metadata_bytes=metadata_bytes,
            request_url=metadata_url,
            expected_record_id=zenodo["record_id"],
            expected_doi=zenodo["version_doi"],
        )
        if normalized["record_decision"] != AUTO:
            raise CocrCorrosionZenodoEpisodeError(
                "record is not AUTO under current Zenodo policy: "
                f"license_ids={normalized.get('license_ids')}, "
                f"reason_codes={normalized.get('record_reason_codes')}"
            )
        by_key = {item["key"]: item for item in normalized["files"]}
        if any(name not in by_key for name in selected_names):
            missing = [name for name in selected_names if name not in by_key]
            raise CocrCorrosionZenodoEpisodeError(f"selected files missing: {missing}")
        for name, expected_md5 in zenodo["selected_files"].items():
            source = by_key[name]
            if source["source_checksum_algorithm"] != "md5":
                raise CocrCorrosionZenodoEpisodeError(
                    f"source checksum algorithm changed for {name}"
                )
            if source["source_checksum_digest"] != expected_md5:
                raise CocrCorrosionZenodoEpisodeError(
                    f"source MD5 changed for {name}"
                )
        plan = plan_zenodo_file_acquisition(normalized, selected_files=selected_names)
        if any(item["decision"] != AUTO for item in plan["items"]):
            raise CocrCorrosionZenodoEpisodeError(
                f"not all selected files are AUTO: {plan['items']}"
            )
        acquisition = acquire_zenodo_files(
            metadata_bytes=metadata_bytes,
            normalized_record=normalized,
            selected_files=selected_names,
            output_dir=staging / "acquisition",
        )
        _write_json(staging / "zenodo_record_normalized.json", normalized)
        _write_json(staging / "zenodo_acquisition_plan.json", plan)
        summary = {
            "schema_version": SCHEMA_VERSION,
            "episode_id": cfg["episode_id"],
            "record_id": normalized["record_id"],
            "doi": normalized["doi"],
            "source_license_ids": normalized.get("source_license_ids", normalized["license_ids"]),
            "license_ids": normalized["license_ids"],
            "record_metadata_sha256": normalized["record_metadata_sha256"],
            "acquired_files": [
                {
                    "key": item["key"],
                    "size_bytes": item["size_bytes"],
                    "source_checksum_algorithm": item["source_checksum_algorithm"],
                    "source_checksum_digest": item["source_checksum_digest"],
                    "local_sha256": item["local_sha256"],
                }
                for item in acquisition["files"]
            ],
            "acquired_file_count": len(acquisition["files"]),
            "repeat_independence_audited": False,
            "reference_electrode_audited": False,
            "equivalent_circuit_model_validated": False,
            "microscopy_linkage_audited": False,
            "scientific_support_established": False,
            "scientific_status_changed": False,
            "requires_scientific_intake": True,
        }
        summary["summary_sha256"] = hashlib.sha256(
            json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        _write_json(staging / "cocr_corrosion_episode_summary.json", summary)
        return summary


__all__ = [
    "CocrCorrosionZenodoEpisodeError",
    "run_cocr_corrosion_zenodo_episode",
    "validate_cocr_config",
]
