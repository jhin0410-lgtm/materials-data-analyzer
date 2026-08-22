"""Fail-closed authorization and execution of the exact IN625 Zenodo archive download.

The module deliberately separates a deterministic pre-download authorization certificate
from the network fetch that consumes it.  Authorization is derived only from the repository-
pinned source policy plus exact live Zenodo metadata/README bytes.  Execution rebuilds the
certificate before performing any network access, restricts redirects to the exact HTTPS
host, enforces the declared byte ceiling, and verifies provider MD5 plus project SHA-256.

Successful acquisition establishes transport/provenance only.  It does not establish sample
identity, measurement semantics, replicate independence, NIST comparability, empirical model
validity, hypothesis truth, or positive scientific closeout.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .in625_zenodo_live_evidence import build_verified_in625_zenodo_readme_manifest
from .kernel import ResearchLoopError

NETWORK_ACQUISITION_AUTHORIZATION_SCHEMA_VERSION = "1.0"
NETWORK_ACQUISITION_AUTHORIZATION_POLICY_VERSION = "1.0"
NETWORK_ACQUISITION_RECEIPT_SCHEMA_VERSION = "1.0"
NETWORK_ACQUISITION_RECEIPT_POLICY_VERSION = "1.0"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_RECORD_ID = 20503603
EXPECTED_HOST = "zenodo.org"
DEFAULT_TIMEOUT_SECONDS = 180.0
_MAX_DOWNLOAD_OVERHEAD_BYTES = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")


class In625ArchiveNetworkAcquisitionError(ResearchLoopError):
    """Raised when pre-download authorization or exact network acquisition drifts."""


@dataclass(frozen=True)
class NetworkFetchResult:
    """Exact downloaded bytes and the final network endpoint observed by the fetcher."""

    body: bytes
    status_code: int
    final_url: str
    content_type: str | None = None


NetworkFetcher = Callable[..., NetworkFetchResult]


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
        raise In625ArchiveNetworkAcquisitionError(
            "network acquisition evidence must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise In625ArchiveNetworkAcquisitionError(f"{field} must be non-empty trimmed text")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625ArchiveNetworkAcquisitionError(f"{field} must be an object")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise In625ArchiveNetworkAcquisitionError(f"{field} must be a positive integer")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256_RE.fullmatch(text) is None:
        raise In625ArchiveNetworkAcquisitionError(f"{field} must be lowercase SHA-256")
    return text


def _md5(value: object, field: str) -> str:
    text = _text(value, field)
    if _MD5_RE.fullmatch(text) is None:
        raise In625ArchiveNetworkAcquisitionError(f"{field} must be lowercase MD5")
    return text


def _source_policy(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("source_id") != EXPECTED_SOURCE_ID:
        raise In625ArchiveNetworkAcquisitionError("IN625 source_id drifted")
    zenodo = _mapping(config.get("zenodo"), "config.zenodo")
    if zenodo.get("record_id") != EXPECTED_RECORD_ID:
        raise In625ArchiveNetworkAcquisitionError("IN625 Zenodo record id drifted")
    archive_name = _text(zenodo.get("archive_file"), "config.zenodo.archive_file")
    files = _mapping(zenodo.get("files"), "config.zenodo.files")
    archive = _mapping(files.get(archive_name), "config archive entry")
    if _text(archive.get("provider_checksum_algorithm"), "archive checksum algorithm") != "md5":
        raise In625ArchiveNetworkAcquisitionError("IN625 archive provider checksum must remain MD5")
    size = _positive_int(archive.get("size_bytes"), "archive size_bytes")
    provider_md5 = _md5(archive.get("provider_checksum_digest"), "archive provider MD5")
    project_sha = _sha(archive.get("verified_sha256"), "archive verified SHA-256")
    boundaries = _mapping(config.get("scientific_boundaries"), "scientific_boundaries")
    for key in (
        "automatic_scientific_promotion",
        "source_acquisition_establishes_direct_nist_comparability",
        "source_acquisition_establishes_hypothesis_truth",
        "source_acquisition_establishes_positive_scientific_closeout",
    ):
        if boundaries.get(key) is not False:
            raise In625ArchiveNetworkAcquisitionError(f"scientific boundary {key} must remain false")
    return {
        "archive_name": archive_name,
        "size_bytes": size,
        "provider_md5": provider_md5,
        "project_sha256": project_sha,
    }


def _validate_endpoint(value: object, *, field: str) -> str:
    text = _text(value, field)
    parsed = urlparse(text)
    if parsed.scheme.lower() != "https":
        raise In625ArchiveNetworkAcquisitionError(f"{field} must use HTTPS")
    if (parsed.hostname or "").lower() != EXPECTED_HOST:
        raise In625ArchiveNetworkAcquisitionError(f"{field} must remain on exact Zenodo host")
    if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
        raise In625ArchiveNetworkAcquisitionError(f"{field} contains unsupported authority data")
    if parsed.fragment:
        raise In625ArchiveNetworkAcquisitionError(f"{field} may not contain a fragment")
    return text


def _scientific_boundary() -> dict[str, bool]:
    return {
        "source_provenance_established_by_successful_download": True,
        "sample_identity_established": False,
        "measurement_semantics_interpreted": False,
        "replicate_independence_established": False,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_established": False,
        "automatic_scientific_promotion": False,
    }


def build_in625_archive_network_authorization(
    *,
    config: Mapping[str, Any],
    config_bytes: bytes,
    metadata_bytes: bytes,
    readme_bytes: bytes,
) -> dict[str, Any]:
    """Authorize only the exact checksum-pinned archive after verified README metadata."""
    if not all(isinstance(item, bytes) for item in (config_bytes, metadata_bytes, readme_bytes)):
        raise In625ArchiveNetworkAcquisitionError(
            "config_bytes, metadata_bytes, and readme_bytes must be exact bytes"
        )
    try:
        parsed_config = json.loads(config_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625ArchiveNetworkAcquisitionError("config_bytes must be valid UTF-8 JSON") from exc
    if not isinstance(parsed_config, dict) or parsed_config != dict(config):
        raise In625ArchiveNetworkAcquisitionError(
            "caller config object differs from exact repository config bytes"
        )
    source = _source_policy(config)
    try:
        readme_manifest = build_verified_in625_zenodo_readme_manifest(
            config=config,
            metadata_bytes=metadata_bytes,
            readme_bytes=readme_bytes,
        )
    except ResearchLoopError as exc:
        raise In625ArchiveNetworkAcquisitionError(
            f"README/source metadata did not pass the exact verified-source boundary or exact Zenodo host restriction: {exc}"
        ) from exc
    file_bindings = _mapping(readme_manifest.get("file_bindings"), "readme_manifest.file_bindings")
    archive_binding = _mapping(
        file_bindings.get(source["archive_name"]),
        "readme_manifest archive binding",
    )
    if archive_binding.get("size_bytes") != source["size_bytes"]:
        raise In625ArchiveNetworkAcquisitionError("live archive size differs from pinned source policy")
    if archive_binding.get("provider_checksum_algorithm") != "md5":
        raise In625ArchiveNetworkAcquisitionError("live archive checksum algorithm drifted")
    if archive_binding.get("provider_checksum_digest") != source["provider_md5"]:
        raise In625ArchiveNetworkAcquisitionError("live archive provider MD5 differs from source policy")
    download_url = _validate_endpoint(
        archive_binding.get("download_url"), field="archive download_url"
    )
    if readme_manifest.get("license_id") != "cc-by-4.0":
        raise In625ArchiveNetworkAcquisitionError("expected open-license identity is not verified")

    certificate: dict[str, Any] = {
        "schema_version": NETWORK_ACQUISITION_AUTHORIZATION_SCHEMA_VERSION,
        "policy_version": NETWORK_ACQUISITION_AUTHORIZATION_POLICY_VERSION,
        "authorization_status": "authorized_exact_archive_download",
        "source_id": EXPECTED_SOURCE_ID,
        "zenodo_record_id": str(EXPECTED_RECORD_ID),
        "source_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "readme_sha256": hashlib.sha256(readme_bytes).hexdigest(),
        "readme_manifest_sha256": _sha(
            readme_manifest.get("manifest_sha256"), "readme manifest SHA-256"
        ),
        "archive": {
            "file_name": source["archive_name"],
            "download_url": download_url,
            "allowed_hosts": [EXPECTED_HOST],
            "expected_size_bytes": source["size_bytes"],
            "provider_checksum_algorithm": "md5",
            "provider_checksum_digest": source["provider_md5"],
            "expected_sha256": source["project_sha256"],
        },
        "preconditions_verified": {
            "exact_repository_source_config": True,
            "exact_live_zenodo_record": True,
            "exact_readme_bytes": True,
            "open_license_identity": True,
            "archive_provider_identity": True,
            "project_archive_sha256_pre_pinned": True,
            "https_exact_host_restriction": True,
        },
        "network_execution_authorized": True,
        "network_access_performed": False,
        "archive_bytes_observed": False,
        "scientific_status_changed": False,
    }
    certificate["authorization_sha256"] = _canonical_sha256(certificate)
    return certificate


def validate_in625_archive_network_authorization(
    authorization: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    config_bytes: bytes,
    metadata_bytes: bytes,
    readme_bytes: bytes,
) -> dict[str, Any]:
    supplied = dict(_mapping(authorization, "authorization"))
    embedded = supplied.pop("authorization_sha256", None)
    if not isinstance(embedded, str) or _SHA256_RE.fullmatch(embedded) is None:
        raise In625ArchiveNetworkAcquisitionError("authorization SHA-256 is malformed")
    if _canonical_sha256(supplied) != embedded:
        raise In625ArchiveNetworkAcquisitionError("authorization canonical SHA-256 does not match")
    rebuilt = build_in625_archive_network_authorization(
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
    )
    if rebuilt != dict(authorization):
        raise In625ArchiveNetworkAcquisitionError(
            "authorization differs from deterministic exact-source reconstruction"
        )
    return rebuilt


class _RestrictedZenodoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _validate_endpoint(newurl, field="redirect endpoint")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_authorized_zenodo_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> NetworkFetchResult:
    """Fetch exact Zenodo HTTPS bytes under an explicit maximum byte ceiling."""
    endpoint = _validate_endpoint(url, field="network acquisition endpoint")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise In625ArchiveNetworkAcquisitionError("max_bytes must be a positive integer")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise In625ArchiveNetworkAcquisitionError("timeout_seconds must be positive")
    opener = build_opener(_RestrictedZenodoRedirectHandler())
    request = Request(
        endpoint,
        headers={"User-Agent": "materials-data-analyzer/in625-authorized-acquisition", "Accept": "*/*"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=float(timeout_seconds)) as response:
            final_url = _validate_endpoint(response.geturl(), field="final response endpoint")
            status = int(getattr(response, "status", response.getcode()))
            if status < 200 or status >= 300:
                raise In625ArchiveNetworkAcquisitionError(
                    f"archive acquisition returned non-success HTTP status {status}"
                )
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    declared_size = int(declared)
                except ValueError as exc:
                    raise In625ArchiveNetworkAcquisitionError(
                        "archive Content-Length is not an integer"
                    ) from exc
                if declared_size < 0 or declared_size > max_bytes:
                    raise In625ArchiveNetworkAcquisitionError(
                        "archive Content-Length exceeds authorization byte ceiling"
                    )
            chunks: list[bytes] = []
            observed = 0
            while True:
                chunk = response.read(min(1024 * 1024, max_bytes - observed + 1))
                if not chunk:
                    break
                observed += len(chunk)
                if observed > max_bytes:
                    raise In625ArchiveNetworkAcquisitionError(
                        "archive response exceeded authorization byte ceiling"
                    )
                chunks.append(chunk)
            return NetworkFetchResult(
                body=b"".join(chunks),
                status_code=status,
                final_url=final_url,
                content_type=response.headers.get("Content-Type"),
            )
    except In625ArchiveNetworkAcquisitionError:
        raise
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise In625ArchiveNetworkAcquisitionError(f"authorized archive acquisition failed: {exc}") from exc


def _reject_html(body: bytes) -> None:
    prefix = body.lstrip()[:512].lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html") or b"<html" in prefix:
        raise In625ArchiveNetworkAcquisitionError("archive response looks like HTML/error payload")


def execute_authorized_in625_archive_download(
    *,
    authorization: Mapping[str, Any],
    config: Mapping[str, Any],
    config_bytes: bytes,
    metadata_bytes: bytes,
    readme_bytes: bytes,
    output_path: str | Path,
    fetcher: NetworkFetcher = fetch_authorized_zenodo_bytes,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute one exact archive network fetch only after deterministic authorization."""
    verified = validate_in625_archive_network_authorization(
        authorization,
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
    )
    archive = _mapping(verified.get("archive"), "authorization.archive")
    expected_size = _positive_int(archive.get("expected_size_bytes"), "expected_size_bytes")
    fetched = fetcher(
        _text(archive.get("download_url"), "archive.download_url"),
        max_bytes=expected_size + _MAX_DOWNLOAD_OVERHEAD_BYTES,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(fetched, NetworkFetchResult):
        raise In625ArchiveNetworkAcquisitionError("network fetcher must return NetworkFetchResult")
    if fetched.status_code < 200 or fetched.status_code >= 300:
        raise In625ArchiveNetworkAcquisitionError("network fetch did not return a success status")
    final_url = _validate_endpoint(fetched.final_url, field="fetched final_url")
    body = fetched.body
    if not isinstance(body, bytes):
        raise In625ArchiveNetworkAcquisitionError("network fetch body must be exact bytes")
    _reject_html(body)
    if len(body) != expected_size:
        raise In625ArchiveNetworkAcquisitionError(
            "downloaded archive byte count differs from authorized source identity"
        )
    provider_md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
    if provider_md5 != _md5(
        archive.get("provider_checksum_digest"), "authorized provider checksum"
    ):
        raise In625ArchiveNetworkAcquisitionError("downloaded archive provider MD5 mismatch")
    sha256 = hashlib.sha256(body).hexdigest()
    if sha256 != _sha(archive.get("expected_sha256"), "authorized archive SHA-256"):
        raise In625ArchiveNetworkAcquisitionError("downloaded archive project SHA-256 mismatch")

    target = Path(output_path).expanduser().resolve(strict=False)
    if target.exists():
        raise In625ArchiveNetworkAcquisitionError("authorized acquisition output already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.authorized-acquisition.tmp")
    if temporary.exists():
        raise In625ArchiveNetworkAcquisitionError("temporary acquisition output already exists")
    try:
        with temporary.open("xb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    receipt: dict[str, Any] = {
        "schema_version": NETWORK_ACQUISITION_RECEIPT_SCHEMA_VERSION,
        "policy_version": NETWORK_ACQUISITION_RECEIPT_POLICY_VERSION,
        "authorization_sha256": verified["authorization_sha256"],
        "source_id": EXPECTED_SOURCE_ID,
        "zenodo_record_id": str(EXPECTED_RECORD_ID),
        "archive": {
            "path": str(target),
            "file_name": archive["file_name"],
            "size_bytes": len(body),
            "provider_md5": provider_md5,
            "sha256": sha256,
            "requested_url": archive["download_url"],
            "final_url": final_url,
            "content_type": fetched.content_type,
        },
        "network_execution_authorized": True,
        "network_access_performed": True,
        "exact_host_restriction_enforced": True,
        "byte_count_verified": True,
        "provider_checksum_verified": True,
        "project_sha256_verified": True,
        "scientific_boundary": _scientific_boundary(),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


__all__ = [
    "In625ArchiveNetworkAcquisitionError",
    "NetworkFetchResult",
    "build_in625_archive_network_authorization",
    "execute_authorized_in625_archive_download",
    "fetch_authorized_zenodo_bytes",
    "validate_in625_archive_network_authorization",
]
