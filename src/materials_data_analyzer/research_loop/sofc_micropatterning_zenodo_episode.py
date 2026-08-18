"""Checksum-bound acquisition entry point for the public SOFC micropatterning dataset."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from platform_core.output_safety import transactional_output_directory

from .safe_archive_inventory import inspect_zip_archive
from .zenodo_evidence_acquisition import (
    AUTO,
    acquire_zenodo_files,
    fetch_zenodo_record_metadata,
    normalize_zenodo_record_metadata,
    plan_zenodo_file_acquisition,
)

SCHEMA_VERSION = "1.0"
ARCHIVE_NAME = "Dataset.zip"
README_NAME = "readme.txt"


class SofcMicropatterningZenodoEpisodeError(ValueError):
    """Raised when the SOFC episode would have to weaken its source contract."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SofcMicropatterningZenodoEpisodeError(f"{field} must be exact non-empty text")
    return value


def _md5(value: object, field: str) -> str:
    digest = _text(value, field).lower()
    if len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
        raise SofcMicropatterningZenodoEpisodeError(f"{field} must be 32 lowercase hex")
    return digest


def validate_sofc_config(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema_version") != "1.0":
        raise SofcMicropatterningZenodoEpisodeError("config schema mismatch")
    zenodo = value.get("zenodo")
    boundaries = value.get("scientific_boundaries")
    if not isinstance(zenodo, Mapping) or not isinstance(boundaries, Mapping):
        raise SofcMicropatterningZenodoEpisodeError("zenodo/boundaries must be objects")
    record_id = zenodo.get("record_id")
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise SofcMicropatterningZenodoEpisodeError("record_id must be positive integer")
    selected = zenodo.get("selected_files")
    if not isinstance(selected, Mapping) or set(selected) != {ARCHIVE_NAME, README_NAME}:
        raise SofcMicropatterningZenodoEpisodeError("selected_files must pin Dataset.zip and readme.txt")
    for field in (
        "filename_is_sample_identity",
        "image_count_is_independent_n",
        "csv_row_count_is_independent_n",
        "sem_to_performance_join_by_order_or_filename",
        "derived_analysis_is_independent_physical_evidence",
        "automatic_scientific_promotion",
        "model_training_authorized_on_acquisition",
    ):
        if boundaries.get(field) is not False:
            raise SofcMicropatterningZenodoEpisodeError(f"{field} must remain false")
    return {
        "schema_version": "1.0",
        "episode_id": _text(value.get("episode_id"), "episode_id"),
        "research_question": _text(value.get("research_question"), "research_question"),
        "zenodo": {
            "record_id": record_id,
            "version_doi": _text(zenodo.get("version_doi"), "version_doi").lower(),
            "selected_files": {
                name: _md5(selected[name], f"MD5 for {name}")
                for name in (ARCHIVE_NAME, README_NAME)
            },
        },
        "scientific_boundaries": dict(boundaries),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_sofc_micropatterning_zenodo_episode(
    *, config: Mapping[str, Any], output_dir: str | Path, overwrite: bool = False
) -> dict[str, Any]:
    cfg = validate_sofc_config(config)
    zenodo = cfg["zenodo"]
    selected_names = [ARCHIVE_NAME, README_NAME]
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        recognized_markers=("sofc_micropatterning_episode_summary.json",),
    ) as staging:
        metadata_bytes, metadata_url = fetch_zenodo_record_metadata(zenodo["record_id"])
        normalized = normalize_zenodo_record_metadata(
            metadata_bytes=metadata_bytes,
            request_url=metadata_url,
            expected_record_id=zenodo["record_id"],
            expected_doi=zenodo["version_doi"],
        )
        if normalized["record_decision"] != AUTO:
            raise SofcMicropatterningZenodoEpisodeError(
                "record is not AUTO under existing Zenodo policy: "
                f"licenses={normalized.get('license_ids')}, reasons={normalized.get('record_reason_codes')}"
            )
        by_key = {item["key"]: item for item in normalized["files"]}
        for name in selected_names:
            if name not in by_key:
                raise SofcMicropatterningZenodoEpisodeError(f"selected file missing: {name}")
            source = by_key[name]
            if source["source_checksum_algorithm"] != "md5":
                raise SofcMicropatterningZenodoEpisodeError(f"source checksum algorithm changed for {name}")
            if source["source_checksum_digest"] != zenodo["selected_files"][name]:
                raise SofcMicropatterningZenodoEpisodeError(f"source MD5 changed for {name}")
        plan = plan_zenodo_file_acquisition(normalized, selected_files=selected_names)
        if len(plan["items"]) != 2 or any(item["decision"] != AUTO for item in plan["items"]):
            raise SofcMicropatterningZenodoEpisodeError(f"selected files are not all AUTO: {plan['items']}")
        acquisition = acquire_zenodo_files(
            metadata_bytes=metadata_bytes,
            normalized_record=normalized,
            selected_files=selected_names,
            output_dir=staging / "acquisition",
        )
        records = {item["key"]: item for item in acquisition["files"]}
        archive_path = staging / "acquisition" / "files" / ARCHIVE_NAME
        inventory = inspect_zip_archive(archive_path)
        if inventory["archive_sha256"] != records[ARCHIVE_NAME]["local_sha256"]:
            raise SofcMicropatterningZenodoEpisodeError("archive inventory is not bound to acquired bytes")
        readme_path = staging / "acquisition" / "files" / README_NAME
        readme_bytes = readme_path.read_bytes()
        if hashlib.sha256(readme_bytes).hexdigest() != records[README_NAME]["local_sha256"]:
            raise SofcMicropatterningZenodoEpisodeError("README bytes differ from acquisition manifest")
        _write_json(staging / "zenodo_record_normalized.json", normalized)
        _write_json(staging / "zenodo_acquisition_plan.json", plan)
        _write_json(staging / "archive_inventory.json", inventory)
        summary = {
            "schema_version": SCHEMA_VERSION,
            "episode_id": cfg["episode_id"],
            "record_id": normalized["record_id"],
            "doi": normalized["doi"],
            "source_license_ids": normalized.get("source_license_ids", normalized["license_ids"]),
            "license_ids": normalized["license_ids"],
            "record_metadata_sha256": normalized["record_metadata_sha256"],
            "acquired_file_count": len(records),
            "archive_sha256": records[ARCHIVE_NAME]["local_sha256"],
            "archive_size_bytes": records[ARCHIVE_NAME]["size_bytes"],
            "readme_sha256": records[README_NAME]["local_sha256"],
            "readme_size_bytes": records[README_NAME]["size_bytes"],
            "archive_member_count": inventory["member_count"],
            "archive_text_candidate_count": inventory["text_candidate_count"],
            "archive_text_hashed_count": inventory["text_hashed_count"],
            "bulk_extraction_performed": inventory["bulk_extraction_performed"],
            "sample_image_lineage_audited": False,
            "replicate_independence_established": False,
            "derived_representation_audited": False,
            "scientific_support_established": False,
            "scientific_status_changed": False,
            "requires_scientific_intake": True,
        }
        summary["summary_sha256"] = hashlib.sha256(
            (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        _write_json(staging / "sofc_micropatterning_episode_summary.json", summary)
        return summary


__all__ = [
    "SofcMicropatterningZenodoEpisodeError",
    "run_sofc_micropatterning_zenodo_episode",
    "validate_sofc_config",
]
