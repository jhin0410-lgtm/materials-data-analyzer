"""Bounded live acquisition episode for the public SSRM titanium nitriding dataset.

This source-specific adapter delegates transfer policy to the generic Zenodo acquisition
layer and archive safety to ``safe_archive_inventory``.  It intentionally stops before
assigning sample identity, cross-technique aliquot equivalence, replicate independence,
or scientific support.
"""

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
    ZenodoEvidenceAcquisitionError,
    acquire_zenodo_files,
    fetch_zenodo_record_metadata,
    normalize_zenodo_record_metadata,
    plan_zenodo_file_acquisition,
)

SCHEMA_VERSION = "1.0"


class SsrmTitaniumZenodoEpisodeError(ValueError):
    """Raised when the SSRM episode would have to weaken its source contract."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SsrmTitaniumZenodoEpisodeError(f"{field} must be exact non-empty text")
    return value


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SsrmTitaniumZenodoEpisodeError(f"{field} must be a non-empty list")
    result: list[str] = []
    for item in value:
        text = _text(item, f"{field} item")
        if text in result:
            raise SsrmTitaniumZenodoEpisodeError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def validate_ssrm_episode_config(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SsrmTitaniumZenodoEpisodeError("episode config must be an object")
    required = {
        "schema_version",
        "episode_id",
        "research_question",
        "zenodo",
        "source_scope",
        "scientific_boundaries",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise SsrmTitaniumZenodoEpisodeError("episode config schema mismatch")
    zenodo = value["zenodo"]
    if not isinstance(zenodo, Mapping):
        raise SsrmTitaniumZenodoEpisodeError("zenodo config must be an object")
    expected_zenodo = {
        "record_id",
        "version_doi",
        "selected_archive",
        "expected_source_checksum_algorithm",
        "expected_source_checksum_digest",
        "required_license",
    }
    if set(zenodo) != expected_zenodo:
        raise SsrmTitaniumZenodoEpisodeError("zenodo config keys do not match schema")
    record_id = zenodo["record_id"]
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise SsrmTitaniumZenodoEpisodeError("zenodo.record_id must be positive integer")
    digest = _text(
        zenodo["expected_source_checksum_digest"],
        "zenodo.expected_source_checksum_digest",
    ).lower()
    if len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
        raise SsrmTitaniumZenodoEpisodeError("expected source MD5 must be 32 lowercase hex")
    if _text(
        zenodo["expected_source_checksum_algorithm"],
        "zenodo.expected_source_checksum_algorithm",
    ).lower() != "md5":
        raise SsrmTitaniumZenodoEpisodeError("SSRM source checksum expectation must remain MD5")
    scope = value["source_scope"]
    if not isinstance(scope, Mapping):
        raise SsrmTitaniumZenodoEpisodeError("source_scope must be an object")
    boundaries = value["scientific_boundaries"]
    if not isinstance(boundaries, Mapping):
        raise SsrmTitaniumZenodoEpisodeError("scientific_boundaries must be an object")
    for field in (
        "filename_is_sample_identity",
        "cross_technique_identical_aliquot_assumed",
        "replicate_independence_assumed",
        "automatic_scientific_promotion",
        "model_training_authorized_on_acquisition",
    ):
        if boundaries.get(field) is not False:
            raise SsrmTitaniumZenodoEpisodeError(f"{field} must remain false")
    pressure = scope.get("declared_nitrogen_pressure_bar")
    max_hours = scope.get("declared_max_process_time_hours")
    if pressure != 50 or max_hours != 10:
        raise SsrmTitaniumZenodoEpisodeError("declared SSRM process bounds changed")
    return {
        "schema_version": "1.0",
        "episode_id": _text(value["episode_id"], "episode_id"),
        "research_question": _text(value["research_question"], "research_question"),
        "zenodo": {
            "record_id": record_id,
            "version_doi": _text(zenodo["version_doi"], "zenodo.version_doi").lower(),
            "selected_archive": _text(zenodo["selected_archive"], "zenodo.selected_archive"),
            "expected_source_checksum_algorithm": "md5",
            "expected_source_checksum_digest": digest,
            "required_license": _text(zenodo["required_license"], "zenodo.required_license").lower(),
        },
        "source_scope": {
            "materials": _strings(scope.get("materials"), "source_scope.materials"),
            "process_family": _text(scope.get("process_family"), "source_scope.process_family"),
            "declared_nitrogen_pressure_bar": pressure,
            "declared_max_process_time_hours": max_hours,
            "modalities_to_audit": _strings(
                scope.get("modalities_to_audit"), "source_scope.modalities_to_audit"
            ),
        },
        "scientific_boundaries": dict(boundaries),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_ssrm_titanium_zenodo_episode(
    *,
    config: Mapping[str, Any],
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    cfg = validate_ssrm_episode_config(config)
    zenodo = cfg["zenodo"]
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        recognized_markers=("ssrm_titanium_episode_summary.json",),
    ) as staging:
        metadata_bytes, metadata_url = fetch_zenodo_record_metadata(zenodo["record_id"])
        normalized = normalize_zenodo_record_metadata(
            metadata_bytes=metadata_bytes,
            request_url=metadata_url,
            expected_record_id=zenodo["record_id"],
            expected_doi=zenodo["version_doi"],
        )
        if normalized["record_decision"] != AUTO:
            raise SsrmTitaniumZenodoEpisodeError(
                f"Zenodo record is not AUTO under existing policy: {normalized['record_reason_codes']}"
            )
        if normalized["license_ids"] != [zenodo["required_license"]]:
            raise SsrmTitaniumZenodoEpisodeError(
                f"Zenodo license changed: {normalized['license_ids']}"
            )
        files = [
            item
            for item in normalized["files"]
            if item["key"] == zenodo["selected_archive"]
        ]
        if len(files) != 1:
            raise SsrmTitaniumZenodoEpisodeError("selected SSRM archive is not unique")
        selected = files[0]
        if (
            selected["source_checksum_algorithm"]
            != zenodo["expected_source_checksum_algorithm"]
            or selected["source_checksum_digest"]
            != zenodo["expected_source_checksum_digest"]
        ):
            raise SsrmTitaniumZenodoEpisodeError(
                "Zenodo source checksum no longer matches pinned SSRM archive"
            )
        plan = plan_zenodo_file_acquisition(
            normalized,
            selected_files=[zenodo["selected_archive"]],
        )
        if len(plan["items"]) != 1 or plan["items"][0]["decision"] != AUTO:
            raise SsrmTitaniumZenodoEpisodeError(
                f"selected SSRM archive is not eligible for automatic acquisition: {plan['items']}"
            )
        acquisition = acquire_zenodo_files(
            metadata_bytes=metadata_bytes,
            normalized_record=normalized,
            selected_files=[zenodo["selected_archive"]],
            output_dir=staging / "acquisition",
        )
        archive_record = acquisition["files"][0]
        archive_path = staging / "acquisition" / "files" / zenodo["selected_archive"]
        inventory = inspect_zip_archive(archive_path)
        if inventory["archive_sha256"] != archive_record["local_sha256"]:
            raise SsrmTitaniumZenodoEpisodeError(
                "archive inventory bytes differ from acquired Zenodo bytes"
            )
        _write_json(staging / "zenodo_record_normalized.json", normalized)
        _write_json(staging / "zenodo_acquisition_plan.json", plan)
        _write_json(staging / "archive_inventory.json", inventory)
        summary = {
            "schema_version": SCHEMA_VERSION,
            "episode_id": cfg["episode_id"],
            "record_id": normalized["record_id"],
            "doi": normalized["doi"],
            "license_ids": normalized["license_ids"],
            "record_metadata_sha256": normalized["record_metadata_sha256"],
            "archive_file": zenodo["selected_archive"],
            "source_checksum_algorithm": archive_record["source_checksum_algorithm"],
            "source_checksum_digest": archive_record["source_checksum_digest"],
            "archive_sha256": archive_record["local_sha256"],
            "archive_size_bytes": archive_record["size_bytes"],
            "archive_member_count": inventory["member_count"],
            "archive_text_candidate_count": inventory["text_candidate_count"],
            "archive_text_hashed_count": inventory["text_hashed_count"],
            "bulk_extraction_performed": inventory["bulk_extraction_performed"],
            "source_scope": cfg["source_scope"],
            "semantic_lineage_audited": False,
            "cross_technique_identical_aliquot_established": False,
            "replicate_independence_established": False,
            "scientific_support_established": False,
            "scientific_status_changed": False,
            "requires_scientific_intake": True,
        }
        summary["summary_sha256"] = hashlib.sha256(
            (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        ).hexdigest()
        _write_json(staging / "ssrm_titanium_episode_summary.json", summary)
        return summary


__all__ = [
    "SCHEMA_VERSION",
    "SsrmTitaniumZenodoEpisodeError",
    "run_ssrm_titanium_zenodo_episode",
    "validate_ssrm_episode_config",
]
