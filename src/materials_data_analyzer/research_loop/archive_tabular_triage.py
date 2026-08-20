"""Bounded structural triage of tabular-looking members inside acquired ZIP evidence.

The triage layer does not trust filenames as scientific semantics and never bulk extracts.
It re-inventories the exact archive, re-reads only budgeted members through the verified
member reader, and applies generic delimited structural intake. Ranking is proposal-only
structural priority, never scientific relevance or analysis authorization.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .delimited_structural_intake import (
    DelimitedStructuralIntakeError,
    inspect_delimited_structure,
)
from .kernel import ResearchLoopError
from .safe_archive_inventory import SafeArchiveInventoryError, inspect_zip_archive
from .safe_archive_member_reader import (
    SafeArchiveMemberReaderError,
    read_verified_text_members,
)

ARCHIVE_TABULAR_TRIAGE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_TRIAGE_MEMBERS = 128
DEFAULT_MAX_TRIAGE_MEMBER_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_TRIAGE_TOTAL_BYTES = 16 * 1024 * 1024
_SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".dat"}


class ArchiveTabularTriageError(ResearchLoopError):
    """Raised when archive tabular triage cannot preserve its exact-byte boundary."""


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArchiveTabularTriageError(f"{field} must be a positive integer")
    return value


def _canonical_sha(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _prior_archive_sha(prior_inventory: Mapping[str, Any]) -> str:
    value = prior_inventory.get("archive_sha256")
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ArchiveTabularTriageError("prior inventory archive_sha256 is invalid")
    if prior_inventory.get("bulk_extraction_performed") is not False:
        raise ArchiveTabularTriageError("prior inventory violated no-bulk-extraction boundary")
    if prior_inventory.get("scientific_status_changed") is not False:
        raise ArchiveTabularTriageError("prior inventory changed scientific status")
    return value


def _candidate_members(inventory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    members = inventory.get("members")
    if not isinstance(members, list):
        raise ArchiveTabularTriageError("fresh archive inventory is malformed")
    selected: list[Mapping[str, Any]] = []
    for item in members:
        if not isinstance(item, Mapping):
            raise ArchiveTabularTriageError("fresh archive inventory member is malformed")
        path = item.get("path")
        suffix = item.get("suffix")
        if (
            isinstance(path, str)
            and isinstance(suffix, str)
            and suffix in _SUPPORTED_SUFFIXES
            and item.get("text_hash_status") == "hashed_within_budget"
            and item.get("utf8_decodable") is True
            and item.get("is_directory") is False
        ):
            selected.append(item)
    selected.sort(key=lambda item: str(item["path"]))
    return selected


def _structural_rank_key(item: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
    structure = item.get("structure")
    if not isinstance(structure, Mapping):
        return (1, 0, 0, 0, str(item.get("path", "")))
    profiles = structure.get("column_profiles")
    numeric_columns = 0
    if isinstance(profiles, list):
        for profile in profiles:
            if isinstance(profile, Mapping) and int(profile.get("numeric_count", 0)) > 0:
                numeric_columns += 1
    return (
        0 if structure.get("rectangular") is True else 1,
        -numeric_columns,
        -int(structure.get("maximum_column_count", 0)),
        -int(structure.get("data_row_count_if_first_row_is_header", 0)),
        str(item.get("path", "")),
    )


def triage_verified_archive_tables(
    archive_path: str | Path,
    prior_inventory: Mapping[str, Any],
    *,
    max_members: int = DEFAULT_MAX_TRIAGE_MEMBERS,
    max_member_bytes: int = DEFAULT_MAX_TRIAGE_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TRIAGE_TOTAL_BYTES,
) -> dict[str, Any]:
    """Discover structurally tabular archive members without source-specific member names."""
    max_members = _positive_int(max_members, "max_members")
    max_member_bytes = _positive_int(max_member_bytes, "max_member_bytes")
    max_total_bytes = _positive_int(max_total_bytes, "max_total_bytes")
    prior_sha = _prior_archive_sha(prior_inventory)

    try:
        fresh_inventory = inspect_zip_archive(archive_path)
    except (SafeArchiveInventoryError, OSError) as exc:
        raise ArchiveTabularTriageError("fresh safe archive inventory failed") from exc
    fresh_sha = fresh_inventory.get("archive_sha256")
    if fresh_sha != prior_sha:
        raise ArchiveTabularTriageError("archive SHA-256 differs from prior safe inventory")

    eligible = _candidate_members(fresh_inventory)
    read_paths: list[str] = []
    deferred: list[dict[str, Any]] = []
    selected_bytes = 0
    for item in eligible:
        path = item["path"]
        size = item.get("uncompressed_size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ArchiveTabularTriageError("candidate member size is invalid")
        if len(read_paths) >= max_members:
            deferred.append({"path": path, "reason": "triage_member_count_budget_exceeded"})
            continue
        if size > max_member_bytes:
            deferred.append({"path": path, "reason": "triage_member_byte_budget_exceeded"})
            continue
        if selected_bytes + size > max_total_bytes:
            deferred.append({"path": path, "reason": "triage_total_byte_budget_exceeded"})
            continue
        read_paths.append(path)
        selected_bytes += size

    try:
        verified = read_verified_text_members(
            archive_path,
            fresh_inventory,
            read_paths,
            max_member_bytes=max_member_bytes,
            max_total_bytes=max_total_bytes,
        )
    except (SafeArchiveMemberReaderError, OSError) as exc:
        raise ArchiveTabularTriageError("verified archive member read failed") from exc
    if verified.get("archive_sha256") != fresh_sha:
        raise ArchiveTabularTriageError("verified reader lost archive SHA binding")
    if verified.get("bulk_extraction_performed") is not False:
        raise ArchiveTabularTriageError("verified reader violated no-bulk-extraction boundary")

    results: list[dict[str, Any]] = []
    for record in verified.get("members", []):
        if not isinstance(record, Mapping):
            raise ArchiveTabularTriageError("verified member record is malformed")
        path = record.get("path")
        text = record.get("text")
        member_sha = record.get("sha256")
        if not isinstance(path, str) or not isinstance(text, str) or not isinstance(member_sha, str):
            raise ArchiveTabularTriageError("verified member record fields are malformed")
        exact_bytes = text.encode("utf-8")
        if hashlib.sha256(exact_bytes).hexdigest() != member_sha:
            raise ArchiveTabularTriageError("UTF-8 round-trip differs from verified member SHA-256")
        suffix = PurePosixPath(path).suffix.lower()
        delimiter_hint = "\t" if suffix == ".tsv" else None
        try:
            structure = inspect_delimited_structure(
                exact_bytes,
                delimiter_hint=delimiter_hint,
                max_bytes=max_member_bytes,
            )
        except DelimitedStructuralIntakeError as exc:
            results.append(
                {
                    "path": path,
                    "member_sha256": member_sha,
                    "size_bytes": record.get("size_bytes"),
                    "status": "not_safely_tabular",
                    "error": str(exc),
                    "scientific_status_changed": False,
                }
            )
            continue
        if structure.get("artifact_sha256") != member_sha:
            raise ArchiveTabularTriageError("structural intake lost verified member SHA binding")
        results.append(
            {
                "path": path,
                "member_sha256": member_sha,
                "size_bytes": record.get("size_bytes"),
                "status": "tabular_candidate",
                "structure": structure,
                "accepted_for_analysis": False,
                "scientific_status_changed": False,
            }
        )

    tabular = [item for item in results if item["status"] == "tabular_candidate"]
    tabular.sort(key=_structural_rank_key)
    ranked = []
    for rank, item in enumerate(tabular, start=1):
        ranked.append(
            {
                "proposal_rank": rank,
                "path": item["path"],
                "member_sha256": item["member_sha256"],
                "structural_rank_key": list(_structural_rank_key(item)[:-1]),
                "ranking_is_scientific_relevance": False,
            }
        )

    report: dict[str, Any] = {
        "schema_version": ARCHIVE_TABULAR_TRIAGE_SCHEMA_VERSION,
        "archive_sha256": fresh_sha,
        "prior_inventory_archive_sha256": prior_sha,
        "fresh_inventory_revalidated": True,
        "fresh_inventory_sha256": _canonical_sha(
            {key: value for key, value in fresh_inventory.items() if key != "archive_path"}
        ),
        "eligible_text_candidate_count": len(eligible),
        "verified_member_read_count": len(read_paths),
        "verified_member_read_bytes": selected_bytes,
        "tabular_candidate_count": len(tabular),
        "not_safely_tabular_count": sum(
            1 for item in results if item["status"] == "not_safely_tabular"
        ),
        "budget_deferred_count": len(deferred),
        "member_results": sorted(results, key=lambda item: str(item["path"])),
        "budget_deferred_members": deferred,
        "proposal_only_ranking": ranked,
        "bulk_extraction_performed": False,
        "accepted_for_analysis": False,
        "sample_identity_inferred": False,
        "replicate_independence_inferred": False,
        "measurement_semantics_interpreted": False,
        "ranking_is_scientific_relevance": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
        "limitations": [
            "Candidate selection uses only previously safe text status, suffix, byte budgets, and generic table structure.",
            "A high proposal rank does not establish scientific relevance, data quality, sample identity, units, calibration, or replicate independence.",
            "Domain-specific scientific intake or review remains required before analysis or claim promotion.",
        ],
    }
    report["triage_sha256"] = _canonical_sha(report)
    return report


__all__ = [
    "ARCHIVE_TABULAR_TRIAGE_SCHEMA_VERSION",
    "ArchiveTabularTriageError",
    "DEFAULT_MAX_TRIAGE_MEMBER_BYTES",
    "DEFAULT_MAX_TRIAGE_MEMBERS",
    "DEFAULT_MAX_TRIAGE_TOTAL_BYTES",
    "triage_verified_archive_tables",
]
