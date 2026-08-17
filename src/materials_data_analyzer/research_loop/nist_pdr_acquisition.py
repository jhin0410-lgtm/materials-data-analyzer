"""NIST Public Data Repository adapter for bounded automatic acquisition.

NERDm metadata is the authority for exact repository file identity. The adapter turns
public NIST DataFile components into the generic acquisition-candidate contract; it does
not infer materials-science comparability from repository metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from .public_data_acquisition import (
    DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    FetchResult,
    PublicAcquisitionError,
    PublicFetcher,
    acquire_public_artifact,
    fetch_https_bytes,
    normalize_public_acquisition_candidate,
    plan_public_acquisition_queue,
)

NIST_PDR_SOURCE_SYSTEM = "NIST Public Data Repository (PDR/NERDm)"
NIST_PDR_HOST = "data.nist.gov"
NIST_PDR_METADATA_MAX_BYTES = 32 * 1024 * 1024
_PRODUCT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NistPdrAcquisitionError(PublicAcquisitionError):
    """Raised when NIST PDR metadata cannot support exact automatic acquisition."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NistPdrAcquisitionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistPdrAcquisitionError("NERDm metadata must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise NistPdrAcquisitionError("NERDm metadata root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NistPdrAcquisitionError(f"{field} must be non-empty text")
    if value != value.strip():
        raise NistPdrAcquisitionError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _product_id(value: object) -> str:
    text = _strict_text(value, "product_id")
    if not _PRODUCT_ID_RE.fullmatch(text):
        raise NistPdrAcquisitionError(
            "product_id contains characters that are not allowed in the PDR metadata path"
        )
    return text


def nist_pdr_metadata_endpoint(product_id: str) -> str:
    """Return the content-negotiated NERDm endpoint for one PDR product."""

    normalized = _product_id(product_id)
    return f"https://{NIST_PDR_HOST}/od/id/{quote(normalized, safe='')}"


def _metadata_identifiers(metadata: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("@id", "doi", "identifier", "ediid"):
        value = metadata.get(field)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, Mapping):
            for nested in ("@id", "value", "identifier"):
                item = value.get(nested)
                if isinstance(item, str):
                    values.append(item)
    return values


def _require_product_identity(metadata: Mapping[str, Any], product_id: str) -> None:
    needle = product_id.lower()
    identifiers = _metadata_identifiers(metadata)
    if not identifiers or not any(needle in item.lower() for item in identifiers):
        raise NistPdrAcquisitionError(
            "NERDm metadata does not bind the requested product_id in its identifiers"
        )


def _require_public_resource(metadata: Mapping[str, Any]) -> None:
    access_level = metadata.get("accessLevel")
    if access_level is not None:
        if access_level != "public":
            raise NistPdrAcquisitionError(
                f"NERDm accessLevel is not public: {access_level!r}"
            )
        return
    types = metadata.get("@type")
    type_values = types if isinstance(types, list) else []
    if "nrdp:PublicDataResource" not in type_values:
        raise NistPdrAcquisitionError(
            "NERDm resource is not explicitly marked as public"
        )


def _source_version(metadata: Mapping[str, Any]) -> str:
    version = metadata.get("version")
    if isinstance(version, str) and version.strip() and version == version.strip():
        return version
    raise NistPdrAcquisitionError(
        "NERDm resource must expose a non-empty exact version before automatic acquisition"
    )


def _datafile_components(metadata: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    components = metadata.get("components")
    if not isinstance(components, list):
        raise NistPdrAcquisitionError("NERDm metadata components must be a list")
    result: list[Mapping[str, Any]] = []
    for component in components:
        if not isinstance(component, Mapping):
            continue
        types = component.get("@type")
        type_values = types if isinstance(types, list) else []
        # DataFile inherits DownloadableFile in NERDm, so the inherited type need not
        # appear separately in @type. Requiring both would reject valid NERDm records.
        if "nrdp:DataFile" in type_values and component.get("downloadURL") is not None:
            result.append(component)
    if not result:
        raise NistPdrAcquisitionError(
            "NERDm metadata contains no downloadable DataFile components"
        )
    return result


def _component_size(component: Mapping[str, Any], *, filepath: str) -> int:
    value = component.get("size")
    if isinstance(value, bool):
        raise NistPdrAcquisitionError(
            f"component {filepath!r} size must be a positive integer"
        )
    if isinstance(value, int):
        size = value
    elif isinstance(value, str) and value.isdigit():
        # Some NIST examples serialize byte counts as decimal strings even though the
        # NERDm reference type is integer. Normalize without accepting units/decimals.
        size = int(value)
    else:
        raise NistPdrAcquisitionError(
            f"component {filepath!r} size must be an integer byte count"
        )
    if size <= 0:
        raise NistPdrAcquisitionError(
            f"component {filepath!r} size must be positive"
        )
    return size


def _component_checksum(component: Mapping[str, Any], *, filepath: str) -> str:
    checksum = component.get("checksum")
    if not isinstance(checksum, Mapping):
        raise NistPdrAcquisitionError(
            f"component {filepath!r} does not expose checksum metadata"
        )
    digest = checksum.get("hash")
    algorithm = checksum.get("algorithm")
    tag: object = None
    if isinstance(algorithm, Mapping):
        tag = algorithm.get("tag")
    elif isinstance(algorithm, str):
        tag = algorithm
    if not isinstance(tag, str) or tag.lower().replace("-", "") != "sha256":
        raise NistPdrAcquisitionError(
            f"component {filepath!r} checksum is not explicitly SHA-256"
        )
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise NistPdrAcquisitionError(
            f"component {filepath!r} SHA-256 hash is missing or invalid"
        )
    return digest


def _validate_nist_url(value: object, *, field: str) -> str:
    text = _strict_text(value, field)
    parsed = urlparse(text)
    try:
        port = parsed.port
    except ValueError as exc:
        raise NistPdrAcquisitionError(f"{field} contains an invalid port") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != NIST_PDR_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise NistPdrAcquisitionError(
            f"{field} is outside exact NIST PDR HTTPS"
        )
    return text


def _component_candidate(
    *,
    metadata: Mapping[str, Any],
    metadata_bytes: bytes,
    product_id: str,
    component: Mapping[str, Any],
    evidence_role: str,
) -> dict[str, Any]:
    filepath = _strict_text(component.get("filepath"), "component.filepath")
    retrieval_endpoint = _validate_nist_url(
        component.get("downloadURL"), field=f"component {filepath!r}.downloadURL"
    )
    candidate = {
        "schema_version": "1.0",
        "candidate_id": f"nist-pdr:{product_id}:{filepath}",
        "evidence_role": evidence_role,
        "source_system": NIST_PDR_SOURCE_SYSTEM,
        "source_version": _source_version(metadata),
        "metadata_endpoint": nist_pdr_metadata_endpoint(product_id),
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "artifact_path": filepath,
        "retrieval_endpoint": retrieval_endpoint,
        "expected_sha256": _component_checksum(component, filepath=filepath),
        "expected_size_bytes": _component_size(component, filepath=filepath),
        "allowed_hosts": [NIST_PDR_HOST],
        "access": {
            "publicly_accessible": True,
            "authentication_required": False,
            "interactive_acceptance_required": False,
            "known_automation_prohibited": False,
            "rights_status": "public_repository",
        },
        "limitations": [
            "NERDm file metadata establishes repository file identity/integrity, not scientific comparability.",
            "Automatic acquisition does not relabel programmed power as calibrated actual power.",
            "Downstream intake must preserve machine, material state, calibration, spot size, and replicate identity.",
        ],
    }
    return normalize_public_acquisition_candidate(candidate)


def discover_nist_pdr_candidates(
    *,
    metadata_bytes: bytes,
    product_id: str,
    filepaths: Sequence[str] | None = None,
    evidence_role: str = "source_artifact",
) -> list[dict[str, Any]]:
    """Discover exact checksum-bound downloadable files from NERDm metadata."""

    if not isinstance(metadata_bytes, bytes):
        raise NistPdrAcquisitionError("metadata_bytes must be exact bytes")
    normalized_product_id = _product_id(product_id)
    metadata = _json_object(metadata_bytes)
    _require_product_identity(metadata, normalized_product_id)
    _require_public_resource(metadata)

    requested: set[str] | None = None
    if filepaths is not None:
        requested = set()
        for index, filepath in enumerate(filepaths):
            text = _strict_text(filepath, f"filepaths[{index}]")
            if text in requested:
                raise NistPdrAcquisitionError("filepaths must not contain duplicates")
            requested.add(text)

    candidates: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for component in _datafile_components(metadata):
        filepath = _strict_text(component.get("filepath"), "component.filepath")
        if filepath in seen_paths:
            raise NistPdrAcquisitionError(
                f"NERDm metadata contains duplicate downloadable filepath {filepath!r}"
            )
        seen_paths.add(filepath)
        if requested is not None and filepath not in requested:
            continue
        candidates.append(
            _component_candidate(
                metadata=metadata,
                metadata_bytes=metadata_bytes,
                product_id=normalized_product_id,
                component=component,
                evidence_role=evidence_role,
            )
        )

    if requested is not None:
        found = {candidate["artifact_path"] for candidate in candidates}
        missing = sorted(requested - found)
        if missing:
            raise NistPdrAcquisitionError(
                f"requested filepaths are not downloadable DataFile components: {missing}"
            )
    if not candidates:
        raise NistPdrAcquisitionError("no requested downloadable files were discovered")
    return candidates


def fetch_nist_pdr_metadata(
    product_id: str,
    *,
    fetcher: PublicFetcher = fetch_https_bytes,
    timeout_seconds: float = 60.0,
) -> FetchResult:
    """Fetch exact NERDm bytes using JSON content negotiation."""

    endpoint = nist_pdr_metadata_endpoint(product_id)
    result = fetcher(
        endpoint,
        allowed_hosts=[NIST_PDR_HOST],
        max_bytes=NIST_PDR_METADATA_MAX_BYTES,
        timeout_seconds=timeout_seconds,
        headers={"Accept": "application/json"},
    )
    if not isinstance(result, FetchResult):
        raise NistPdrAcquisitionError("fetcher must return FetchResult")
    if not 200 <= result.status_code < 300:
        raise NistPdrAcquisitionError(
            f"NERDm metadata fetch returned status {result.status_code}"
        )
    _validate_nist_url(result.final_url, field="NERDm metadata final URL")
    return result


def plan_nist_pdr_product_acquisition(
    *,
    product_id: str,
    metadata_bytes: bytes,
    filepaths: Sequence[str] | None = None,
    evidence_role: str = "source_artifact",
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Build an exception-only acquisition queue for a NIST PDR product."""

    candidates = discover_nist_pdr_candidates(
        metadata_bytes=metadata_bytes,
        product_id=product_id,
        filepaths=filepaths,
        evidence_role=evidence_role,
    )
    return plan_public_acquisition_queue(candidates, max_auto_bytes=max_auto_bytes)


def acquire_nist_pdr_file(
    *,
    product_id: str,
    filepath: str,
    output_dir: str | Path,
    evidence_role: str = "source_artifact",
    fetcher: PublicFetcher = fetch_https_bytes,
    overwrite: bool = False,
    timeout_seconds: float = 60.0,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Fetch metadata, resolve one exact file, acquire it, and bind provenance."""

    metadata_result = fetch_nist_pdr_metadata(
        product_id, fetcher=fetcher, timeout_seconds=timeout_seconds
    )
    candidate = discover_nist_pdr_candidates(
        metadata_bytes=metadata_result.body,
        product_id=product_id,
        filepaths=[filepath],
        evidence_role=evidence_role,
    )[0]
    return acquire_public_artifact(
        candidate=candidate,
        metadata_bytes=metadata_result.body,
        output_dir=output_dir,
        fetcher=fetcher,
        overwrite=overwrite,
        timeout_seconds=timeout_seconds,
        max_auto_bytes=max_auto_bytes,
    )


def acquire_nist_pdr_auto_candidates(
    *,
    product_id: str,
    output_root: str | Path,
    filepaths: Sequence[str] | None = None,
    evidence_role: str = "source_artifact",
    fetcher: PublicFetcher = fetch_https_bytes,
    overwrite: bool = False,
    timeout_seconds: float = 60.0,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Acquire every AUTO file in one plan without per-file human approval."""

    metadata_result = fetch_nist_pdr_metadata(
        product_id, fetcher=fetcher, timeout_seconds=timeout_seconds
    )
    candidates = discover_nist_pdr_candidates(
        metadata_bytes=metadata_result.body,
        product_id=product_id,
        filepaths=filepaths,
        evidence_role=evidence_role,
    )
    queue = plan_public_acquisition_queue(candidates, max_auto_bytes=max_auto_bytes)
    auto_ids = {item["candidate_id"] for item in queue["auto"]}
    root = Path(output_root)
    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for index, candidate in enumerate(candidates):
        if candidate["candidate_id"] not in auto_ids:
            continue
        package_key = hashlib.sha256(
            candidate["candidate_id"].encode("utf-8")
        ).hexdigest()[:16]
        package_dir = root / f"{index:04d}-{package_key}"
        try:
            receipt = acquire_public_artifact(
                candidate=candidate,
                metadata_bytes=metadata_result.body,
                output_dir=package_dir,
                fetcher=fetcher,
                overwrite=overwrite,
                timeout_seconds=timeout_seconds,
                max_auto_bytes=max_auto_bytes,
            )
        except PublicAcquisitionError as exc:
            failures.append(
                {"candidate_id": candidate["candidate_id"], "error": str(exc)}
            )
            continue
        receipts.append({**receipt, "package_directory": package_dir.as_posix()})

    return {
        "schema_version": "1.0",
        "product_id": _product_id(product_id),
        "metadata_sha256": hashlib.sha256(metadata_result.body).hexdigest(),
        "queue": queue,
        "automatic_execution_attempted": len(auto_ids),
        "automatic_execution_succeeded": len(receipts),
        "automatic_execution_failed": len(failures),
        "receipts": receipts,
        "failures": failures,
        "all_auto_succeeded": not failures,
        "human_review_required": queue["review_required"],
        "blocked": queue["blocked"],
    }


__all__ = [
    "NIST_PDR_HOST",
    "NIST_PDR_METADATA_MAX_BYTES",
    "NIST_PDR_SOURCE_SYSTEM",
    "NistPdrAcquisitionError",
    "acquire_nist_pdr_auto_candidates",
    "acquire_nist_pdr_file",
    "discover_nist_pdr_candidates",
    "fetch_nist_pdr_metadata",
    "nist_pdr_metadata_endpoint",
    "plan_nist_pdr_product_acquisition",
]
