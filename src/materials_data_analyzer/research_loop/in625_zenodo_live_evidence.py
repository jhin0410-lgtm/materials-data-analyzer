"""Fail-closed live-evidence binding for the verified IN625 Zenodo source.

This module deliberately separates source-byte provenance from scientific authority.
A successful download proves only that the configured publication supplement and its
bytes were observed as declared.  It never establishes direct NIST comparability,
hypothesis truth, or positive scientific closeout.
"""
from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .kernel import ResearchLoopError
from .zenodo_evidence_acquisition import normalize_zenodo_record_metadata, zenodo_record_url

IN625_ZENODO_LIVE_EVIDENCE_SCHEMA_VERSION = "1.0"
IN625_ZENODO_LIVE_EVIDENCE_POLICY_VERSION = "1.0"


class In625ZenodoLiveEvidenceError(ResearchLoopError):
    """Raised when the configured source cannot be verified exactly."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise In625ZenodoLiveEvidenceError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _json_object(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625ZenodoLiveEvidenceError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise In625ZenodoLiveEvidenceError(f"{field} root must be an object")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625ZenodoLiveEvidenceError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise In625ZenodoLiveEvidenceError(f"{field} must be non-empty trimmed text")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise In625ZenodoLiveEvidenceError(f"{field} must be a positive integer")
    return value


def _hex(value: object, length: int, field: str) -> str:
    text = _text(value, field).lower()
    if len(text) != length or any(ch not in "0123456789abcdef" for ch in text):
        raise In625ZenodoLiveEvidenceError(f"{field} must be {length}-character lowercase hex")
    return text


def _canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise In625ZenodoLiveEvidenceError("manifest must be canonical-JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest()


def _scientific_boundary() -> dict[str, bool | str]:
    return {
        "authority_class": "source_artifact_only",
        "source_provenance_established": True,
        "artifact_bytes_verified": True,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_established": False,
        "automatic_scientific_promotion": False,
    }


def _zenodo_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    if str(config.get("schema_version")) != "1.1":
        raise In625ZenodoLiveEvidenceError("IN625 Zenodo source config schema must be 1.1")
    zenodo = _mapping(config.get("zenodo"), "config.zenodo")
    boundaries = _mapping(config.get("scientific_boundaries"), "config.scientific_boundaries")
    for key in (
        "source_acquisition_establishes_direct_nist_comparability",
        "source_acquisition_establishes_hypothesis_truth",
        "source_acquisition_establishes_positive_scientific_closeout",
    ):
        if boundaries.get(key) is not False:
            raise In625ZenodoLiveEvidenceError(f"scientific boundary {key} must remain false")
    return zenodo


def _expected_files(zenodo: Mapping[str, Any]) -> Mapping[str, Any]:
    files = _mapping(zenodo.get("files"), "config.zenodo.files")
    selected = zenodo.get("selected_files")
    if not isinstance(selected, list) or not selected or any(not isinstance(x, str) or not x for x in selected):
        raise In625ZenodoLiveEvidenceError("config.zenodo.selected_files must be non-empty text list")
    if set(selected) != set(files):
        raise In625ZenodoLiveEvidenceError("selected_files and configured file identities must match exactly")
    return files


def _related_identifier_verified(metadata: Mapping[str, Any], doi: str, relation: str) -> bool:
    raw = metadata.get("related_identifiers")
    if not isinstance(raw, list):
        return False
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        identifier = item.get("identifier")
        observed_relation = item.get("relation")
        if isinstance(identifier, str) and identifier.lower() == doi.lower() and observed_relation == relation:
            return True
    return False


def _reject_html(body: bytes, field: str) -> None:
    prefix = body.lstrip()[:512].lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html") or b"<html" in prefix:
        raise In625ZenodoLiveEvidenceError(f"{field} looks like HTML rather than source evidence")


def build_verified_in625_zenodo_readme_manifest(
    *,
    config: Mapping[str, Any],
    metadata_bytes: bytes,
    readme_bytes: bytes,
) -> dict[str, Any]:
    """Verify exact current source identity and README bytes against repository policy."""
    if not isinstance(metadata_bytes, bytes) or not isinstance(readme_bytes, bytes):
        raise In625ZenodoLiveEvidenceError("metadata_bytes and readme_bytes must be exact bytes")
    zenodo = _zenodo_config(config)
    record_id = _positive_int(zenodo.get("record_id"), "config.zenodo.record_id")
    version_doi = _text(zenodo.get("version_doi"), "config.zenodo.version_doi")
    normalized = normalize_zenodo_record_metadata(
        metadata_bytes=metadata_bytes,
        request_url=zenodo_record_url(record_id),
        expected_record_id=record_id,
        expected_doi=version_doi,
    )
    if normalized.get("record_decision") != "AUTO":
        raise In625ZenodoLiveEvidenceError("exact Zenodo record is not automatically reusable under policy")
    raw_record = _json_object(metadata_bytes, "Zenodo metadata bytes")
    metadata = _mapping(raw_record.get("metadata"), "Zenodo metadata.metadata")
    expected_title = _text(zenodo.get("expected_title"), "config.zenodo.expected_title")
    if normalized.get("title") != expected_title:
        raise In625ZenodoLiveEvidenceError("Zenodo title drifted from the pinned source identity")
    expected_date = _text(zenodo.get("publication_date"), "config.zenodo.publication_date")
    if metadata.get("publication_date") != expected_date:
        raise In625ZenodoLiveEvidenceError("Zenodo publication date drifted from expectation")
    expected_license = _text(zenodo.get("license_id"), "config.zenodo.license_id").lower()
    source_licenses = normalized.get("source_license_ids")
    if source_licenses != [expected_license]:
        raise In625ZenodoLiveEvidenceError("Zenodo license identity drifted from expectation")
    related_doi = _text(zenodo.get("related_article_doi"), "config.zenodo.related_article_doi")
    related_relation = _text(
        zenodo.get("related_article_relation"), "config.zenodo.related_article_relation"
    )
    if not _related_identifier_verified(metadata, related_doi, related_relation):
        raise In625ZenodoLiveEvidenceError("publication DOI/relation is not verified by the exact Zenodo record")

    expected_files = _expected_files(zenodo)
    observed_files = {
        item["key"]: item
        for item in normalized.get("files", [])
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    if set(observed_files) != set(expected_files):
        raise In625ZenodoLiveEvidenceError("Zenodo file set drifted from the pinned source identity")
    file_bindings: dict[str, Any] = {}
    for key, expected_raw in expected_files.items():
        expected = _mapping(expected_raw, f"config.zenodo.files[{key!r}]")
        observed = observed_files[key]
        size = _positive_int(expected.get("size_bytes"), f"expected {key} size")
        algorithm = _text(
            expected.get("provider_checksum_algorithm"), f"expected {key} checksum algorithm"
        ).lower()
        digest_length = 32 if algorithm == "md5" else 64 if algorithm == "sha256" else 0
        if digest_length == 0:
            raise In625ZenodoLiveEvidenceError("only provider MD5/SHA-256 checksums are supported")
        digest = _hex(
            expected.get("provider_checksum_digest"), digest_length, f"expected {key} checksum"
        )
        if observed.get("size_bytes") != size:
            raise In625ZenodoLiveEvidenceError(f"Zenodo file size drifted: {key}")
        if observed.get("source_checksum_algorithm") != algorithm:
            raise In625ZenodoLiveEvidenceError(f"Zenodo checksum algorithm drifted: {key}")
        if observed.get("source_checksum_digest") != digest:
            raise In625ZenodoLiveEvidenceError(f"Zenodo provider checksum drifted: {key}")
        file_bindings[key] = {
            "size_bytes": size,
            "provider_checksum_algorithm": algorithm,
            "provider_checksum_digest": digest,
            "download_url": observed.get("download_url"),
        }

    readme_name = _text(zenodo.get("readme_file"), "config.zenodo.readme_file")
    expected_readme = _mapping(expected_files.get(readme_name), "configured README identity")
    _reject_html(readme_bytes, "README")
    if len(readme_bytes) != _positive_int(expected_readme.get("size_bytes"), "README size"):
        raise In625ZenodoLiveEvidenceError("README byte size does not match pinned source identity")
    expected_md5 = _hex(expected_readme.get("provider_checksum_digest"), 32, "README provider MD5")
    actual_md5 = hashlib.md5(readme_bytes, usedforsecurity=False).hexdigest()
    if actual_md5 != expected_md5:
        raise In625ZenodoLiveEvidenceError("README MD5 does not match Zenodo provider metadata")
    expected_sha256 = _hex(expected_readme.get("verified_sha256"), 64, "README verified SHA-256")
    actual_sha256 = hashlib.sha256(readme_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        raise In625ZenodoLiveEvidenceError("README SHA-256 does not match repository-verified bytes")

    manifest: dict[str, Any] = {
        "schema_version": IN625_ZENODO_LIVE_EVIDENCE_SCHEMA_VERSION,
        "policy_version": IN625_ZENODO_LIVE_EVIDENCE_POLICY_VERSION,
        "evidence_stage": "verified_publication_readme",
        "record_id": str(record_id),
        "record_doi": version_doi.lower(),
        "record_title": expected_title,
        "publication_date": expected_date,
        "license_id": expected_license,
        "related_article_doi": related_doi.lower(),
        "related_article_relation": related_relation,
        "record_metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "file_bindings": file_bindings,
        "readme": {
            "file_name": readme_name,
            "size_bytes": len(readme_bytes),
            "provider_md5": actual_md5,
            "sha256": actual_sha256,
        },
        "scientific_boundary": _scientific_boundary(),
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def _hash_file(path: Path) -> tuple[int, str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return size, md5.hexdigest(), sha256.hexdigest()


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise In625ZenodoLiveEvidenceError("ZIP member name is empty or contains backslashes")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise In625ZenodoLiveEvidenceError(f"unsafe ZIP member path: {name}")
    return path


def inspect_verified_in625_dataset_archive(
    *,
    config: Mapping[str, Any],
    archive_path: str | Path,
    selected_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the exact archive and safely inventory/extract bounded CSV/TXT evidence."""
    zenodo = _zenodo_config(config)
    expected_files = _expected_files(zenodo)
    archive_name = _text(zenodo.get("archive_file"), "config.zenodo.archive_file")
    expected = _mapping(expected_files.get(archive_name), "configured archive identity")
    path = Path(archive_path)
    if not path.is_file():
        raise In625ZenodoLiveEvidenceError("configured IN625 archive path is not a file")
    size, md5, sha256 = _hash_file(path)
    if size != _positive_int(expected.get("size_bytes"), "archive expected size"):
        raise In625ZenodoLiveEvidenceError("archive byte size does not match Zenodo metadata")
    expected_md5 = _hex(expected.get("provider_checksum_digest"), 32, "archive provider MD5")
    if md5 != expected_md5:
        raise In625ZenodoLiveEvidenceError("archive MD5 does not match Zenodo provider metadata")
    pinned_sha = expected.get("verified_sha256")
    if pinned_sha is not None and sha256 != _hex(pinned_sha, 64, "archive verified SHA-256"):
        raise In625ZenodoLiveEvidenceError("archive SHA-256 does not match repository-verified bytes")

    policy = _mapping(zenodo.get("archive_policy"), "config.zenodo.archive_policy")
    max_members = _positive_int(policy.get("max_members"), "archive max_members")
    max_total = _positive_int(
        policy.get("max_total_uncompressed_bytes"), "archive max_total_uncompressed_bytes"
    )
    max_member = _positive_int(
        policy.get("max_member_uncompressed_bytes"), "archive max_member_uncompressed_bytes"
    )
    max_selected = _positive_int(
        policy.get("max_selected_tabular_bytes"), "archive max_selected_tabular_bytes"
    )
    extensions = policy.get("selected_extensions")
    if not isinstance(extensions, list) or not extensions or any(
        not isinstance(ext, str) or not ext.startswith(".") for ext in extensions
    ):
        raise In625ZenodoLiveEvidenceError("archive selected_extensions must be non-empty extensions")
    extension_set = {ext.lower() for ext in extensions}

    inventory: list[dict[str, Any]] = []
    selected_infos: list[zipfile.ZipInfo] = []
    total_uncompressed = 0
    selected_uncompressed = 0
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > max_members:
            raise In625ZenodoLiveEvidenceError("archive member-count budget exceeded")
        for info in infos:
            member_path = _safe_member_name(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode):
                raise In625ZenodoLiveEvidenceError(f"ZIP symlink is not allowed: {info.filename}")
            if info.flag_bits & 0x1:
                raise In625ZenodoLiveEvidenceError(f"encrypted ZIP member is not allowed: {info.filename}")
            if info.file_size > max_member:
                raise In625ZenodoLiveEvidenceError(f"ZIP member size budget exceeded: {info.filename}")
            total_uncompressed += info.file_size
            if total_uncompressed > max_total:
                raise In625ZenodoLiveEvidenceError("archive total uncompressed-byte budget exceeded")
            suffix = member_path.suffix.lower()
            selected = not info.is_dir() and suffix in extension_set
            if selected:
                selected_uncompressed += info.file_size
                if selected_uncompressed > max_selected:
                    raise In625ZenodoLiveEvidenceError("selected tabular-byte budget exceeded")
                selected_infos.append(info)
            inventory.append(
                {
                    "path": info.filename,
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": info.file_size,
                    "crc32": f"{info.CRC:08x}",
                    "selected_tabular": selected,
                }
            )

        selected_records: list[dict[str, Any]] = []
        output_root = Path(selected_output_dir) if selected_output_dir is not None else None
        if output_root is not None:
            output_root.mkdir(parents=True, exist_ok=True)
        for info in selected_infos:
            member_path = _safe_member_name(info.filename)
            digest = hashlib.sha256()
            actual_size = 0
            target = output_root.joinpath(*member_path.parts) if output_root is not None else None
            if target is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source:
                if target is None:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        actual_size += len(chunk)
                        digest.update(chunk)
                else:
                    with target.open("wb") as sink:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            actual_size += len(chunk)
                            if actual_size > info.file_size:
                                raise In625ZenodoLiveEvidenceError("ZIP member expanded beyond declared size")
                            digest.update(chunk)
                            sink.write(chunk)
            if actual_size != info.file_size:
                raise In625ZenodoLiveEvidenceError("ZIP member bytes differ from declared member size")
            selected_records.append(
                {
                    "path": info.filename,
                    "size_bytes": actual_size,
                    "sha256": digest.hexdigest(),
                }
            )

    manifest: dict[str, Any] = {
        "schema_version": IN625_ZENODO_LIVE_EVIDENCE_SCHEMA_VERSION,
        "policy_version": IN625_ZENODO_LIVE_EVIDENCE_POLICY_VERSION,
        "evidence_stage": "verified_publication_archive_inventory",
        "archive": {
            "file_name": archive_name,
            "size_bytes": size,
            "provider_md5": md5,
            "sha256": sha256,
            "sha256_previously_pinned": pinned_sha is not None,
        },
        "inventory_summary": {
            "member_count": len(inventory),
            "total_uncompressed_bytes": total_uncompressed,
            "selected_tabular_count": len(selected_records),
            "selected_tabular_bytes": selected_uncompressed,
        },
        "inventory": inventory,
        "selected_tabular_files": selected_records,
        "scientific_boundary": _scientific_boundary(),
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest
