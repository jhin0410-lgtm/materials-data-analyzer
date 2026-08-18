"""Policy-bounded acquisition of published Zenodo evidence files.

Zenodo commonly publishes an MD5 content checksum.  This adapter verifies that checksum
*as MD5* and separately computes a local SHA-256 for downstream provenance.  It never
relabels a repository MD5 as SHA-256 and never treats download success as scientific
validation.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlparse

from platform_core.output_safety import transactional_output_directory

from .kernel import ResearchLoopError
from .public_data_acquisition import FetchResult, PublicFetcher, fetch_https_bytes

ZENODO_ACQUISITION_SCHEMA_VERSION = "1.0"
ZENODO_ACQUISITION_POLICY_VERSION = "1.1"
ZENODO_HOST = "zenodo.org"
ZENODO_RECORD_ENDPOINT = f"https://{ZENODO_HOST}/api/records"
ZENODO_METADATA_MAX_BYTES = 32 * 1024 * 1024
DEFAULT_ZENODO_FILE_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_ZENODO_TOTAL_MAX_BYTES = 768 * 1024 * 1024

AUTO = "AUTO"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
BLOCKED = "BLOCKED"

_CHECKSUM_RE = re.compile(r"^(?P<algorithm>[A-Za-z0-9_-]+):(?P<digest>[0-9a-fA-F]+)$")
_SUPPORTED_SOURCE_CHECKSUMS = {"md5", "sha256"}
_AUTO_LICENSE_IDS = {
    "cc0-1.0",
    "cc-by-3.0",
    "cc-by-4.0",
    "cc-by-sa-3.0",
    "cc-by-sa-4.0",
}
# Zenodo's legacy controlled vocabulary uses ``cc-zero`` for Creative Commons
# Zero 1.0 Universal. Preserve that exact source ID separately and canonicalize
# only for policy evaluation so source vocabulary is never silently rewritten.
_LICENSE_CANONICAL_ALIASES = {
    "cc-zero": "cc0-1.0",
}
_REVIEW_LICENSE_PREFIXES = (
    "cc-by-nc-",
    "cc-by-nd-",
    "cc-by-nc-sa-",
    "cc-by-nc-nd-",
)


class ZenodoEvidenceAcquisitionError(ResearchLoopError):
    """Raised when Zenodo content cannot be acquired without weakening policy."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ZenodoEvidenceAcquisitionError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZenodoEvidenceAcquisitionError(
            "Zenodo record metadata must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ZenodoEvidenceAcquisitionError("Zenodo record metadata root must be object")
    return value


def _text(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ZenodoEvidenceAcquisitionError(f"{field} must be non-empty text")
    if value != value.strip():
        raise ZenodoEvidenceAcquisitionError(f"{field} must not contain edge whitespace")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ZenodoEvidenceAcquisitionError(f"{field} must be a positive integer")
    return value


def _record_id(value: object) -> str:
    if isinstance(value, bool):
        raise ZenodoEvidenceAcquisitionError("record id must be numeric")
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return str(int(value))
    raise ZenodoEvidenceAcquisitionError("record id must be a positive numeric identifier")


def _doi(value: object, field: str, *, optional: bool = False) -> str | None:
    text = _text(value, field, optional=optional)
    if text is None:
        return None
    normalized = text.lower()
    if normalized.startswith("https://doi.org/"):
        normalized = normalized.removeprefix("https://doi.org/")
    if normalized.startswith("doi:"):
        normalized = normalized.removeprefix("doi:")
    if not normalized.startswith("10.") or "/" not in normalized:
        raise ZenodoEvidenceAcquisitionError(f"{field} must be a DOI")
    return normalized


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ZenodoEvidenceAcquisitionError(
            "Zenodo acquisition record must be canonical-JSON serializable"
        ) from exc


def _exact_zenodo_url(value: object, field: str) -> str:
    text = _text(value, field)
    assert text is not None
    parsed = urlparse(text)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ZenodoEvidenceAcquisitionError(f"{field} contains invalid port") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != ZENODO_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise ZenodoEvidenceAcquisitionError(
            f"{field} must remain on exact HTTPS host {ZENODO_HOST}"
        )
    return text


def zenodo_record_url(record_id: object) -> str:
    return f"{ZENODO_RECORD_ENDPOINT}/{_record_id(record_id)}"


def _license_ids(metadata: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for key in ("license", "rights"):
        raw = metadata.get(key)
        values: list[object]
        if isinstance(raw, list):
            values = list(raw)
        else:
            values = [raw]
        for item in values:
            candidates: list[object] = []
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, Mapping):
                candidates.extend(item.get(field) for field in ("id", "identifier"))
            for candidate in candidates:
                if isinstance(candidate, str) and candidate.strip():
                    normalized = candidate.strip().lower()
                    if normalized not in result:
                        result.append(normalized)
    return sorted(result)


def _canonical_license_ids(source_license_ids: Sequence[str]) -> list[str]:
    result: list[str] = []
    for source_id in source_license_ids:
        canonical = _LICENSE_CANONICAL_ALIASES.get(source_id, source_id)
        if canonical not in result:
            result.append(canonical)
    return sorted(result)


def _license_decision(license_ids: Sequence[str]) -> tuple[str, list[str]]:
    if not license_ids:
        return REVIEW_REQUIRED, ["license_not_explicit_in_record_metadata"]
    if any(item in _AUTO_LICENSE_IDS for item in license_ids):
        return AUTO, []
    if any(item.startswith(_REVIEW_LICENSE_PREFIXES) for item in license_ids):
        return REVIEW_REQUIRED, ["license_has_use_or_derivative_restriction"]
    return REVIEW_REQUIRED, ["license_not_in_automatic_reuse_allowlist"]


def _access_status(record: Mapping[str, Any], metadata: Mapping[str, Any]) -> tuple[str, list[str]]:
    access = record.get("access")
    if isinstance(access, Mapping):
        record_access = access.get("record")
        file_access = access.get("files")
        if record_access == "public" and file_access == "public":
            return AUTO, []
        if record_access in {"restricted", "embargoed"} or file_access in {
            "restricted",
            "embargoed",
        }:
            return BLOCKED, ["zenodo_record_or_files_not_public"]
        return REVIEW_REQUIRED, ["zenodo_access_not_explicitly_public"]

    legacy_access = metadata.get("access_right")
    if legacy_access == "open":
        return AUTO, []
    if legacy_access in {"restricted", "embargoed", "closed"}:
        return BLOCKED, ["zenodo_legacy_access_not_open"]
    return REVIEW_REQUIRED, ["zenodo_access_not_explicit_in_record"]


def _checksum(value: object, field: str) -> tuple[str, str]:
    text = _text(value, field)
    assert text is not None
    match = _CHECKSUM_RE.fullmatch(text)
    if match is None:
        raise ZenodoEvidenceAcquisitionError(
            f"{field} must have '<algorithm>:<hex-digest>' form"
        )
    algorithm = match.group("algorithm").lower()
    digest = match.group("digest").lower()
    if algorithm == "md5" and len(digest) != 32:
        raise ZenodoEvidenceAcquisitionError(f"{field} MD5 digest length is invalid")
    if algorithm == "sha256" and len(digest) != 64:
        raise ZenodoEvidenceAcquisitionError(f"{field} SHA-256 digest length is invalid")
    return algorithm, digest


def _safe_artifact_name(value: object) -> str:
    text = _text(value, "file key")
    assert text is not None
    if "\\" in text:
        raise ZenodoEvidenceAcquisitionError("file key may not contain backslashes")
    path = PurePosixPath(text)
    if path.is_absolute() or "." in path.parts or ".." in path.parts or len(path.parts) != 1:
        raise ZenodoEvidenceAcquisitionError("file key must be one flat file name")
    if not path.name:
        raise ZenodoEvidenceAcquisitionError("file key must name a file")
    return path.name


def _modern_files(record: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    files = record.get("files")
    if not isinstance(files, Mapping):
        return None
    entries = files.get("entries")
    if not isinstance(entries, Mapping):
        return None
    result: list[Mapping[str, Any]] = []
    for key, value in entries.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            raise ZenodoEvidenceAcquisitionError("Zenodo files.entries is invalid")
        merged = dict(value)
        merged.setdefault("key", key)
        result.append(merged)
    return result


def _legacy_files(record: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    files = record.get("files")
    if not isinstance(files, list):
        return None
    if not all(isinstance(item, Mapping) for item in files):
        raise ZenodoEvidenceAcquisitionError("Zenodo legacy files list is invalid")
    return list(files)


def _download_url(file_record: Mapping[str, Any]) -> str:
    links = file_record.get("links")
    candidates: list[object] = []
    if isinstance(links, Mapping):
        candidates.extend(links.get(key) for key in ("content", "download", "self"))
    candidates.extend(file_record.get(key) for key in ("download", "url"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return _exact_zenodo_url(candidate.strip(), "file download URL")
    raise ZenodoEvidenceAcquisitionError("Zenodo file does not expose exact download URL")


def _normalize_file(file_record: Mapping[str, Any]) -> dict[str, Any]:
    key = _safe_artifact_name(file_record.get("key") or file_record.get("filename"))
    size = _positive_int(file_record.get("size"), f"file {key} size")
    algorithm, digest = _checksum(file_record.get("checksum"), f"file {key} checksum")
    return {
        "key": key,
        "size_bytes": size,
        "source_checksum_algorithm": algorithm,
        "source_checksum_digest": digest,
        "source_checksum_supported": algorithm in _SUPPORTED_SOURCE_CHECKSUMS,
        "download_url": _download_url(file_record),
    }


def normalize_zenodo_record_metadata(
    *,
    metadata_bytes: bytes,
    request_url: str,
    expected_record_id: str | int | None = None,
    expected_doi: str | None = None,
) -> dict[str, Any]:
    if not isinstance(metadata_bytes, bytes):
        raise ZenodoEvidenceAcquisitionError("metadata_bytes must be exact bytes")
    request = _exact_zenodo_url(request_url, "record metadata URL")
    record = _json_object(metadata_bytes)
    record_id = _record_id(record.get("id"))
    if expected_record_id is not None and record_id != _record_id(expected_record_id):
        raise ZenodoEvidenceAcquisitionError("Zenodo record id does not match expectation")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ZenodoEvidenceAcquisitionError("Zenodo record metadata field must be object")
    doi = _doi(record.get("doi") or metadata.get("doi"), "record DOI", optional=True)
    pids = record.get("pids")
    if doi is None and isinstance(pids, Mapping):
        doi_obj = pids.get("doi")
        if isinstance(doi_obj, Mapping):
            doi = _doi(doi_obj.get("identifier"), "record DOI", optional=True)
    if expected_doi is not None and doi != _doi(expected_doi, "expected DOI"):
        raise ZenodoEvidenceAcquisitionError("Zenodo DOI does not match expectation")
    concept_doi = _doi(
        record.get("conceptdoi") or metadata.get("conceptdoi"),
        "concept DOI",
        optional=True,
    )
    title = _text(metadata.get("title") or record.get("title"), "record title")
    assert title is not None
    source_license_ids = _license_ids(metadata)
    license_ids = _canonical_license_ids(source_license_ids)
    access_decision, access_reasons = _access_status(record, metadata)
    license_decision, license_reasons = _license_decision(license_ids)
    if BLOCKED in {access_decision, license_decision}:
        record_decision = BLOCKED
    elif REVIEW_REQUIRED in {access_decision, license_decision}:
        record_decision = REVIEW_REQUIRED
    else:
        record_decision = AUTO
    files = _modern_files(record)
    if files is None:
        files = _legacy_files(record)
    if files is None:
        raise ZenodoEvidenceAcquisitionError("Zenodo record does not contain file metadata")
    normalized_files = [_normalize_file(item) for item in files]
    keys = [item["key"] for item in normalized_files]
    if len(keys) != len(set(keys)):
        raise ZenodoEvidenceAcquisitionError("Zenodo record contains duplicate file keys")
    normalized_files.sort(key=lambda item: item["key"])
    return {
        "schema_version": ZENODO_ACQUISITION_SCHEMA_VERSION,
        "policy_version": ZENODO_ACQUISITION_POLICY_VERSION,
        "source_system": "zenodo",
        "record_id": record_id,
        "doi": doi,
        "concept_doi": concept_doi,
        "title": title,
        "record_metadata_url": request,
        "record_metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "source_license_ids": source_license_ids,
        "license_ids": license_ids,
        "record_decision": record_decision,
        "record_reason_codes": sorted(set(access_reasons + license_reasons)),
        "files": normalized_files,
        "scientific_status_changed": False,
        "requires_scientific_intake": True,
        "download_success_is_scientific_validation": False,
    }


def fetch_zenodo_record_metadata(
    record_id: str | int,
    *,
    fetcher: PublicFetcher = fetch_https_bytes,
    timeout_seconds: float = 60.0,
) -> tuple[bytes, str]:
    url = zenodo_record_url(record_id)
    fetched = fetcher(
        url,
        allowed_hosts=[ZENODO_HOST],
        max_bytes=ZENODO_METADATA_MAX_BYTES,
        timeout_seconds=timeout_seconds,
        headers={"Accept": "application/json"},
    )
    if not isinstance(fetched, FetchResult):
        raise ZenodoEvidenceAcquisitionError("fetcher must return FetchResult")
    if not 200 <= fetched.status_code < 300:
        raise ZenodoEvidenceAcquisitionError(
            f"Zenodo record fetch returned status {fetched.status_code}"
        )
    final_url = _exact_zenodo_url(fetched.final_url, "record final URL")
    return fetched.body, final_url


def plan_zenodo_file_acquisition(
    normalized_record: Mapping[str, Any],
    *,
    selected_files: Sequence[str] | None = None,
    max_file_bytes: int = DEFAULT_ZENODO_FILE_MAX_BYTES,
    max_total_bytes: int = DEFAULT_ZENODO_TOTAL_MAX_BYTES,
) -> dict[str, Any]:
    if normalized_record.get("schema_version") != ZENODO_ACQUISITION_SCHEMA_VERSION:
        raise ZenodoEvidenceAcquisitionError("normalized record schema mismatch")
    if (
        isinstance(max_file_bytes, bool)
        or not isinstance(max_file_bytes, int)
        or max_file_bytes <= 0
        or isinstance(max_total_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or max_total_bytes <= 0
    ):
        raise ZenodoEvidenceAcquisitionError("byte budgets must be positive integers")
    raw_files = normalized_record.get("files")
    if not isinstance(raw_files, list):
        raise ZenodoEvidenceAcquisitionError("normalized record files must be a list")
    by_key = {
        str(item.get("key")): item
        for item in raw_files
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    if len(by_key) != len(raw_files):
        raise ZenodoEvidenceAcquisitionError("normalized record files are invalid")
    requested = sorted(by_key) if selected_files is None else [_safe_artifact_name(v) for v in selected_files]
    if len(requested) != len(set(requested)):
        raise ZenodoEvidenceAcquisitionError("selected_files must not contain duplicates")
    missing = sorted(set(requested) - set(by_key))
    if missing:
        raise ZenodoEvidenceAcquisitionError(f"selected Zenodo files are missing: {missing}")
    record_decision = normalized_record.get("record_decision")
    if record_decision not in {AUTO, REVIEW_REQUIRED, BLOCKED}:
        raise ZenodoEvidenceAcquisitionError("normalized record decision is invalid")
    total_auto = 0
    items: list[dict[str, Any]] = []
    for key in requested:
        file_record = by_key[key]
        size = file_record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ZenodoEvidenceAcquisitionError("normalized file size is invalid")
        reasons = list(normalized_record.get("record_reason_codes") or [])
        decision = str(record_decision)
        if not file_record.get("source_checksum_supported"):
            decision = REVIEW_REQUIRED if decision != BLOCKED else BLOCKED
            reasons.append("source_checksum_algorithm_not_supported")
        if size > max_file_bytes:
            decision = REVIEW_REQUIRED if decision != BLOCKED else BLOCKED
            reasons.append("automatic_file_budget_exceeded")
        if decision == AUTO:
            proposed = total_auto + size
            if proposed > max_total_bytes:
                decision = REVIEW_REQUIRED
                reasons.append("automatic_batch_budget_exceeded")
            else:
                total_auto = proposed
        items.append(
            {
                "key": key,
                "decision": decision,
                "reason_codes": sorted(set(reasons)),
                "size_bytes": size,
                "source_checksum_algorithm": file_record["source_checksum_algorithm"],
                "source_checksum_digest": file_record["source_checksum_digest"],
                "download_url": file_record["download_url"],
            }
        )
    return {
        "schema_version": ZENODO_ACQUISITION_SCHEMA_VERSION,
        "record_id": normalized_record.get("record_id"),
        "doi": normalized_record.get("doi"),
        "auto_bytes": total_auto,
        "max_total_auto_bytes": max_total_bytes,
        "items": items,
        "scientific_status_changed": False,
    }


def _verify_source_checksum(body: bytes, algorithm: str, expected_digest: str) -> None:
    if algorithm == "md5":
        actual = hashlib.md5(body, usedforsecurity=False).hexdigest()
    elif algorithm == "sha256":
        actual = hashlib.sha256(body).hexdigest()
    else:
        raise ZenodoEvidenceAcquisitionError(
            f"unsupported source checksum algorithm: {algorithm}"
        )
    if actual != expected_digest:
        raise ZenodoEvidenceAcquisitionError(
            f"downloaded artifact {algorithm} does not match Zenodo metadata"
        )


def acquire_zenodo_files(
    *,
    metadata_bytes: bytes,
    normalized_record: Mapping[str, Any],
    selected_files: Sequence[str],
    output_dir: str | Path,
    fetcher: PublicFetcher = fetch_https_bytes,
    timeout_seconds: float = 60.0,
    overwrite: bool = False,
    max_file_bytes: int = DEFAULT_ZENODO_FILE_MAX_BYTES,
    max_total_bytes: int = DEFAULT_ZENODO_TOTAL_MAX_BYTES,
) -> dict[str, Any]:
    observed_metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    if observed_metadata_sha != normalized_record.get("record_metadata_sha256"):
        raise ZenodoEvidenceAcquisitionError(
            "metadata bytes do not match normalized record metadata SHA-256"
        )
    plan = plan_zenodo_file_acquisition(
        normalized_record,
        selected_files=selected_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    non_auto = [item for item in plan["items"] if item["decision"] != AUTO]
    if non_auto:
        raise ZenodoEvidenceAcquisitionError(
            f"selected files are not all eligible for automatic acquisition: {non_auto}"
        )
    acquired: list[dict[str, Any]] = []
    bodies: dict[str, bytes] = {}
    for item in plan["items"]:
        fetched = fetcher(
            item["download_url"],
            allowed_hosts=[ZENODO_HOST],
            max_bytes=item["size_bytes"] + 1,
            timeout_seconds=timeout_seconds,
            headers={"Accept": "*/*"},
        )
        if not isinstance(fetched, FetchResult):
            raise ZenodoEvidenceAcquisitionError("fetcher must return FetchResult")
        if not 200 <= fetched.status_code < 300:
            raise ZenodoEvidenceAcquisitionError(
                f"Zenodo file fetch returned status {fetched.status_code}"
            )
        _exact_zenodo_url(fetched.final_url, "file final URL")
        body = fetched.body
        if len(body) != item["size_bytes"]:
            raise ZenodoEvidenceAcquisitionError(
                f"downloaded file size differs from Zenodo metadata: {item['key']}"
            )
        _verify_source_checksum(
            body,
            item["source_checksum_algorithm"],
            item["source_checksum_digest"],
        )
        local_sha = hashlib.sha256(body).hexdigest()
        bodies[item["key"]] = body
        acquired.append(
            {
                "key": item["key"],
                "size_bytes": len(body),
                "source_checksum_algorithm": item["source_checksum_algorithm"],
                "source_checksum_digest": item["source_checksum_digest"],
                "local_sha256": local_sha,
                "download_url": item["download_url"],
                "final_url": fetched.final_url,
            }
        )
    manifest = {
        "schema_version": ZENODO_ACQUISITION_SCHEMA_VERSION,
        "policy_version": ZENODO_ACQUISITION_POLICY_VERSION,
        "source_system": "zenodo",
        "record_id": normalized_record.get("record_id"),
        "doi": normalized_record.get("doi"),
        "concept_doi": normalized_record.get("concept_doi"),
        "record_title": normalized_record.get("title"),
        "record_metadata_url": normalized_record.get("record_metadata_url"),
        "record_metadata_sha256": observed_metadata_sha,
        "source_license_ids": normalized_record.get("source_license_ids"),
        "license_ids": normalized_record.get("license_ids"),
        "files": acquired,
        "source_checksum_preserved_without_algorithm_relabeling": True,
        "local_sha256_computed_for_every_file": True,
        "scientific_status_changed": False,
        "requires_scientific_intake": True,
        "download_success_is_scientific_validation": False,
    }
    manifest_bytes = _canonical_bytes(manifest) + b"\n"
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        recognized_markers=("zenodo_acquisition_manifest.json",),
    ) as staging:
        files_root = staging / "files"
        files_root.mkdir(parents=True, exist_ok=True)
        for key, body in bodies.items():
            (files_root / key).write_bytes(body)
        (staging / "source_metadata.json").write_bytes(metadata_bytes)
        (staging / "zenodo_acquisition_manifest.json").write_bytes(manifest_bytes)
    return {
        **manifest,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "output_dir": str(Path(output_dir)),
    }


__all__ = [
    "AUTO",
    "BLOCKED",
    "DEFAULT_ZENODO_FILE_MAX_BYTES",
    "DEFAULT_ZENODO_TOTAL_MAX_BYTES",
    "REVIEW_REQUIRED",
    "ZENODO_ACQUISITION_POLICY_VERSION",
    "ZENODO_ACQUISITION_SCHEMA_VERSION",
    "ZENODO_HOST",
    "ZenodoEvidenceAcquisitionError",
    "acquire_zenodo_files",
    "fetch_zenodo_record_metadata",
    "normalize_zenodo_record_metadata",
    "plan_zenodo_file_acquisition",
    "zenodo_record_url",
]
