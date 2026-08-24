"""Policy-bounded automatic acquisition of public research artifacts.

The acquisition layer separates three concerns:

1. source adapters discover exact downloadable artifacts and normalize their metadata;
2. this module decides whether an artifact is safe to acquire automatically;
3. acquired bytes are checksum/size verified and bound into the existing acquisition-record
   provenance contract before they are allowed to move further into scientific intake.

Public, direct, checksum-bound artifacts can therefore run without per-file human approval.
Authentication, click-through terms, uncertain rights, or explicit automation prohibitions are
fail-closed into a review/block queue instead of being bypassed.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPException, InvalidURL
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from platform_core.output_safety import transactional_output_directory

from .acquisition_record_binding import (
    AcquisitionRecordBindingError,
    authenticate_acquisition_record_binding,
)
from .kernel import ResearchLoopError

PUBLIC_ACQUISITION_CANDIDATE_SCHEMA_VERSION = "1.0"
PUBLIC_ACQUISITION_RECEIPT_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_AUTO_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_AUTO_BATCH_BYTES = 4 * 1024 * 1024 * 1024

AUTO = "AUTO"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
BLOCKED = "BLOCKED"

_ALLOWED_RIGHTS_STATUS = {
    "public_repository",
    "explicit_open_license",
    "review_required",
    "restricted",
    "unknown",
}
_CANDIDATE_KEYS = {
    "schema_version",
    "candidate_id",
    "evidence_role",
    "source_system",
    "source_version",
    "metadata_endpoint",
    "metadata_sha256",
    "artifact_path",
    "retrieval_endpoint",
    "expected_sha256",
    "expected_size_bytes",
    "allowed_hosts",
    "access",
    "limitations",
}
_ACCESS_KEYS = {
    "publicly_accessible",
    "authentication_required",
    "interactive_acceptance_required",
    "known_automation_prohibited",
    "rights_status",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROXY_TUNNEL_STATUS_RE = re.compile(r"Tunnel connection failed:\s*(\d{3})\b")
_TRANSIENT_HTTP_STATUS_CODES = frozenset(
    {
        408,
        425,
        429,
        500,
        502,
        503,
        504,
        520,
        521,
        522,
        523,
        524,
    }
)


class PublicAcquisitionError(ResearchLoopError):
    """Raised when automatic public-data acquisition violates its trust boundary."""


class PublicAcquisitionTransportError(PublicAcquisitionError):
    """Raised when a bounded network acquisition cannot complete at transport time.

    This subtype is intentionally reserved for transient network/HTTP delivery failures.
    Content, checksum, size, redirect-host, provenance, policy, and permanent HTTP failures
    remain the parent ``PublicAcquisitionError`` so callers may recover from transient
    delivery failures without swallowing integrity or access-policy failures.
    """


@dataclass(frozen=True)
class FetchResult:
    """Exact bytes returned by a bounded HTTP fetch."""

    body: bytes
    status_code: int
    final_url: str
    content_type: str | None = None


PublicFetcher = Callable[..., FetchResult]


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublicAcquisitionError(f"{field} must be non-empty text")
    if value != value.strip():
        raise PublicAcquisitionError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if not _SHA256_RE.fullmatch(text):
        raise PublicAcquisitionError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PublicAcquisitionError(f"{field} must be a positive integer")
    return value


def _strict_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise PublicAcquisitionError(f"{field} must be boolean")
    return value


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise PublicAcquisitionError(f"{field} must be {qualifier}")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _strict_text(item, f"{field}[{index}]")
        if text in result:
            raise PublicAcquisitionError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], *, field: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        raise PublicAcquisitionError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _relative_artifact_path(value: object) -> PurePosixPath:
    text = _strict_text(value, "artifact_path")
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        raise PublicAcquisitionError("artifact_path must be relative POSIX")
    path = PurePosixPath(text)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise PublicAcquisitionError("artifact_path may not escape the acquisition root")
    if not path.name:
        raise PublicAcquisitionError("artifact_path must name a file")
    return path


def _normalize_hosts(value: object) -> list[str]:
    hosts = _string_list(value, "allowed_hosts")
    normalized: list[str] = []
    for index, host in enumerate(hosts):
        lowered = host.lower()
        if host != lowered or "/" in host or ":" in host or not lowered.strip("."):
            raise PublicAcquisitionError(
                f"allowed_hosts[{index}] must be a lowercase hostname without port/path"
            )
        if lowered in normalized:
            raise PublicAcquisitionError("allowed_hosts must not contain duplicates")
        normalized.append(lowered)
    return normalized


def _validate_https_endpoint(
    value: object, *, field: str, allowed_hosts: Sequence[str]
) -> str:
    text = _strict_text(value, field)
    parsed = urlparse(text)
    if parsed.scheme.lower() != "https":
        raise PublicAcquisitionError(f"{field} must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise PublicAcquisitionError(f"{field} may not embed credentials")
    if parsed.port not in (None, 443):
        raise PublicAcquisitionError(f"{field} may not use a non-HTTPS port")
    host = (parsed.hostname or "").lower()
    if not host or host not in allowed_hosts:
        raise PublicAcquisitionError(
            f"{field} host {host!r} is outside the exact allowed_hosts set"
        )
    if parsed.fragment:
        raise PublicAcquisitionError(f"{field} may not contain a URL fragment")
    return text


def normalize_public_acquisition_candidate(candidate: object) -> dict[str, Any]:
    """Validate and normalize an adapter-produced acquisition candidate."""

    if not isinstance(candidate, Mapping):
        raise PublicAcquisitionError("public acquisition candidate must be an object")
    _exact_keys(candidate, _CANDIDATE_KEYS, field="public acquisition candidate")
    if candidate["schema_version"] != PUBLIC_ACQUISITION_CANDIDATE_SCHEMA_VERSION:
        raise PublicAcquisitionError("unsupported public acquisition candidate schema_version")

    access = candidate["access"]
    if not isinstance(access, Mapping):
        raise PublicAcquisitionError("candidate access must be an object")
    _exact_keys(access, _ACCESS_KEYS, field="candidate access")

    rights_status = _strict_text(access["rights_status"], "access.rights_status")
    if rights_status not in _ALLOWED_RIGHTS_STATUS:
        raise PublicAcquisitionError(
            f"unsupported access.rights_status: {rights_status!r}"
        )
    normalized_access = {
        "publicly_accessible": _strict_bool(
            access["publicly_accessible"], "access.publicly_accessible"
        ),
        "authentication_required": _strict_bool(
            access["authentication_required"], "access.authentication_required"
        ),
        "interactive_acceptance_required": _strict_bool(
            access["interactive_acceptance_required"],
            "access.interactive_acceptance_required",
        ),
        "known_automation_prohibited": _strict_bool(
            access["known_automation_prohibited"],
            "access.known_automation_prohibited",
        ),
        "rights_status": rights_status,
    }

    allowed_hosts = _normalize_hosts(candidate["allowed_hosts"])
    metadata_endpoint = _validate_https_endpoint(
        candidate["metadata_endpoint"],
        field="metadata_endpoint",
        allowed_hosts=allowed_hosts,
    )
    retrieval_endpoint = _validate_https_endpoint(
        candidate["retrieval_endpoint"],
        field="retrieval_endpoint",
        allowed_hosts=allowed_hosts,
    )
    artifact_path = _relative_artifact_path(candidate["artifact_path"]).as_posix()

    return {
        "schema_version": PUBLIC_ACQUISITION_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": _strict_text(candidate["candidate_id"], "candidate_id"),
        "evidence_role": _strict_text(candidate["evidence_role"], "evidence_role"),
        "source_system": _strict_text(candidate["source_system"], "source_system"),
        "source_version": _strict_text(candidate["source_version"], "source_version"),
        "metadata_endpoint": metadata_endpoint,
        "metadata_sha256": _sha256_text(
            candidate["metadata_sha256"], "metadata_sha256"
        ),
        "artifact_path": artifact_path,
        "retrieval_endpoint": retrieval_endpoint,
        "expected_sha256": _sha256_text(
            candidate["expected_sha256"], "expected_sha256"
        ),
        "expected_size_bytes": _positive_int(
            candidate["expected_size_bytes"], "expected_size_bytes"
        ),
        "allowed_hosts": allowed_hosts,
        "access": normalized_access,
        "limitations": _string_list(
            candidate["limitations"], "limitations", allow_empty=False
        ),
    }


def assess_public_acquisition_candidate(
    candidate: object,
    *,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Classify a candidate into AUTO, REVIEW_REQUIRED, or BLOCKED."""

    if isinstance(max_auto_bytes, bool) or not isinstance(max_auto_bytes, int) or max_auto_bytes <= 0:
        raise PublicAcquisitionError("max_auto_bytes must be a positive integer")
    normalized = normalize_public_acquisition_candidate(candidate)
    access = normalized["access"]
    reasons: list[str] = []

    if access["known_automation_prohibited"]:
        return {
            "candidate_id": normalized["candidate_id"],
            "decision": BLOCKED,
            "reason_codes": ["automation_explicitly_prohibited"],
        }
    if access["rights_status"] == "restricted":
        return {
            "candidate_id": normalized["candidate_id"],
            "decision": BLOCKED,
            "reason_codes": ["rights_restricted"],
        }

    if not access["publicly_accessible"]:
        reasons.append("not_publicly_accessible")
    if access["authentication_required"]:
        reasons.append("authentication_required")
    if access["interactive_acceptance_required"]:
        reasons.append("interactive_acceptance_required")
    if access["rights_status"] in {"review_required", "unknown"}:
        reasons.append(f"rights_{access['rights_status']}")
    if normalized["expected_size_bytes"] > max_auto_bytes:
        reasons.append("automatic_size_budget_exceeded")

    if reasons:
        return {
            "candidate_id": normalized["candidate_id"],
            "decision": REVIEW_REQUIRED,
            "reason_codes": reasons,
        }
    return {
        "candidate_id": normalized["candidate_id"],
        "decision": AUTO,
        "reason_codes": [],
    }


def plan_public_acquisition_queue(
    candidates: Sequence[object],
    *,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    max_total_auto_bytes: int = DEFAULT_MAX_AUTO_BATCH_BYTES,
) -> dict[str, Any]:
    """Partition candidates so humans see only exceptional acquisitions.

    Per-artifact and total automatic byte budgets are enforced before execution. Once the
    total budget is exhausted, otherwise-safe candidates are routed to REVIEW_REQUIRED
    rather than silently downloading an unbounded product.
    """

    if (
        isinstance(max_total_auto_bytes, bool)
        or not isinstance(max_total_auto_bytes, int)
        or max_total_auto_bytes <= 0
    ):
        raise PublicAcquisitionError("max_total_auto_bytes must be a positive integer")
    normalized = [
        normalize_public_acquisition_candidate(candidate) for candidate in candidates
    ]
    planned = [
        assess_public_acquisition_candidate(candidate, max_auto_bytes=max_auto_bytes)
        for candidate in normalized
    ]
    ids = [item["candidate_id"] for item in planned]
    if len(ids) != len(set(ids)):
        raise PublicAcquisitionError(
            "candidate_id values must be unique in an acquisition queue"
        )

    automatic_bytes = 0
    budgeted: list[dict[str, Any]] = []
    for item, candidate in zip(planned, normalized, strict=True):
        if item["decision"] != AUTO:
            budgeted.append(item)
            continue
        proposed = automatic_bytes + candidate["expected_size_bytes"]
        if proposed > max_total_auto_bytes:
            budgeted.append(
                {
                    "candidate_id": item["candidate_id"],
                    "decision": REVIEW_REQUIRED,
                    "reason_codes": ["automatic_batch_budget_exceeded"],
                }
            )
            continue
        automatic_bytes = proposed
        budgeted.append(item)

    by_decision = {
        decision: [item for item in budgeted if item["decision"] == decision]
        for decision in (AUTO, REVIEW_REQUIRED, BLOCKED)
    }
    return {
        "schema_version": "1.0",
        "candidate_count": len(budgeted),
        "auto_count": len(by_decision[AUTO]),
        "review_required_count": len(by_decision[REVIEW_REQUIRED]),
        "blocked_count": len(by_decision[BLOCKED]),
        "auto_bytes": automatic_bytes,
        "max_total_auto_bytes": max_total_auto_bytes,
        "auto": by_decision[AUTO],
        "review_required": by_decision[REVIEW_REQUIRED],
        "blocked": by_decision[BLOCKED],
    }


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: Sequence[str]) -> None:
        super().__init__()
        self._allowed_hosts = tuple(allowed_hosts)

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _validate_https_endpoint(
            newurl, field="redirect endpoint", allowed_hosts=self._allowed_hosts
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_https_bytes(
    url: str,
    *,
    allowed_hosts: Sequence[str],
    max_bytes: int,
    timeout_seconds: float = 60.0,
    headers: Mapping[str, str] | None = None,
) -> FetchResult:
    """Fetch HTTPS bytes with exact-host redirect restrictions and a byte ceiling."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise PublicAcquisitionError("max_bytes must be a positive integer")
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise PublicAcquisitionError("timeout_seconds must be positive")
    normalized_hosts = _normalize_hosts(list(allowed_hosts))
    endpoint = _validate_https_endpoint(
        url, field="fetch endpoint", allowed_hosts=normalized_hosts
    )

    request_headers = {
        "User-Agent": "materials-data-analyzer/automatic-public-acquisition",
        "Accept": "*/*",
    }
    if headers:
        for key, value in headers.items():
            request_headers[_strict_text(key, "header name")] = _strict_text(
                value, f"header {key!r}"
            )

    opener = build_opener(_RestrictedRedirectHandler(normalized_hosts))
    request = Request(endpoint, headers=request_headers, method="GET")
    try:
        with opener.open(request, timeout=float(timeout_seconds)) as response:
            final_url = response.geturl()
            _validate_https_endpoint(
                final_url,
                field="final response endpoint",
                allowed_hosts=normalized_hosts,
            )
            status = int(getattr(response, "status", response.getcode()))
            if status < 200 or status >= 300:
                if status in _TRANSIENT_HTTP_STATUS_CODES:
                    raise PublicAcquisitionTransportError(
                        f"HTTP acquisition returned non-success status {status}"
                    )
                raise PublicAcquisitionError(
                    f"HTTP acquisition returned non-success status {status}"
                )
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise PublicAcquisitionError(
                        "HTTP Content-Length is not an integer"
                    ) from exc
                if declared_length < 0 or declared_length > max_bytes:
                    raise PublicAcquisitionError(
                        "HTTP Content-Length exceeds the configured byte ceiling"
                    )
            chunks: list[bytes] = []
            observed = 0
            while True:
                chunk = response.read(min(1024 * 1024, max_bytes - observed + 1))
                if not chunk:
                    break
                observed += len(chunk)
                if observed > max_bytes:
                    raise PublicAcquisitionError(
                        "HTTP response exceeded the configured byte ceiling"
                    )
                chunks.append(chunk)
            body = b"".join(chunks)
            content_type = response.headers.get("Content-Type")
            return FetchResult(
                body=body,
                status_code=status,
                final_url=final_url,
                content_type=content_type,
            )
    except PublicAcquisitionError:
        raise
    except HTTPError as exc:
        status = int(exc.code)
        error_type = (
            PublicAcquisitionTransportError
            if status in _TRANSIENT_HTTP_STATUS_CODES
            else PublicAcquisitionError
        )
        raise error_type(f"HTTP acquisition failed: {status} {exc.reason}") from exc
    except InvalidURL as exc:
        raise PublicAcquisitionError(f"HTTP acquisition invalid URL: {exc}") from exc
    except HTTPException as exc:
        raise PublicAcquisitionTransportError(
            f"HTTP acquisition failed: {exc}"
        ) from exc
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise PublicAcquisitionError(
                f"HTTP acquisition certificate verification failed: {reason}"
            ) from exc
        tunnel_match = _PROXY_TUNNEL_STATUS_RE.search(str(reason))
        if tunnel_match is not None:
            status = int(tunnel_match.group(1))
            error_type = (
                PublicAcquisitionTransportError
                if status in _TRANSIENT_HTTP_STATUS_CODES
                else PublicAcquisitionError
            )
            raise error_type(
                f"HTTP acquisition failed: proxy tunnel status {status}"
            ) from exc
        raise PublicAcquisitionTransportError(
            f"HTTP acquisition failed: {exc}"
        ) from exc
    except (TimeoutError, socket.timeout, OSError) as exc:
        raise PublicAcquisitionTransportError(
            f"HTTP acquisition failed: {exc}"
        ) from exc


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _build_binding_documents(
    *,
    candidate: Mapping[str, Any],
    artifact_sha256: str,
    artifact_size_bytes: int,
    final_url: str,
) -> tuple[bytes, bytes]:
    acquisition_id = f"{candidate['candidate_id']}:{artifact_sha256[:16]}"
    manifest = {
        "schema_version": "1.0",
        "acquisition_id": acquisition_id,
        "source": {
            "source_system": candidate["source_system"],
            "source_version": candidate["source_version"],
            "metadata_endpoint": candidate["metadata_endpoint"],
            "metadata_sha256": candidate["metadata_sha256"],
        },
        "retrieval": {
            "retrieval_endpoint": candidate["retrieval_endpoint"],
            "final_endpoint": final_url,
            "retrieval_status": "downloaded_checksum_verified",
            "network_performed": True,
        },
        "artifact": {
            "path": candidate["artifact_path"],
            "sha256": artifact_sha256,
            "size_bytes": artifact_size_bytes,
        },
    }
    manifest_bytes = _canonical_json_bytes(manifest)
    declaration = {
        "schema_version": "1.0",
        "acquisition_id": acquisition_id,
        "evidence_artifact_sha256": artifact_sha256,
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evidence_role": candidate["evidence_role"],
        "manifest_evidence_sha256_pointer": "/artifact/sha256",
        "manifest_claim_bindings": [
            {
                "claim": "source_system",
                "json_pointer": "/source/source_system",
                "expected_value": candidate["source_system"],
            },
            {
                "claim": "source_version",
                "json_pointer": "/source/source_version",
                "expected_value": candidate["source_version"],
            },
            {
                "claim": "retrieval_endpoint",
                "json_pointer": "/retrieval/retrieval_endpoint",
                "expected_value": candidate["retrieval_endpoint"],
            },
            {
                "claim": "retrieval_status",
                "json_pointer": "/retrieval/retrieval_status",
                "expected_value": "downloaded_checksum_verified",
            },
            {
                "claim": "network_performed",
                "json_pointer": "/retrieval/network_performed",
                "expected_value": True,
            },
        ],
        "limitations": [
            "Recorded acquisition provenance does not by itself authenticate physical origin or scientific validity.",
            "Transport and public-repository metadata do not establish support independence or cross-source comparability.",
            *candidate["limitations"],
        ],
    }
    return manifest_bytes, _canonical_json_bytes(declaration)


def acquire_public_artifact(
    *,
    candidate: object,
    metadata_bytes: bytes,
    output_dir: str | Path,
    fetcher: PublicFetcher = fetch_https_bytes,
    overwrite: bool = False,
    timeout_seconds: float = 60.0,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Automatically acquire one AUTO candidate and emit provenance-bound exact bytes."""

    normalized = normalize_public_acquisition_candidate(candidate)
    assessment = assess_public_acquisition_candidate(
        normalized, max_auto_bytes=max_auto_bytes
    )
    if assessment["decision"] != AUTO:
        raise PublicAcquisitionError(
            f"candidate is not eligible for automatic acquisition: {assessment}"
        )
    if not isinstance(metadata_bytes, bytes):
        raise PublicAcquisitionError("metadata_bytes must be exact bytes")
    observed_metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    if observed_metadata_sha != normalized["metadata_sha256"]:
        raise PublicAcquisitionError(
            "metadata bytes do not match the adapter-declared metadata SHA-256"
        )

    fetch_limit = normalized["expected_size_bytes"] + 1
    fetched = fetcher(
        normalized["retrieval_endpoint"],
        allowed_hosts=normalized["allowed_hosts"],
        max_bytes=fetch_limit,
        timeout_seconds=timeout_seconds,
        headers={"Accept": "*/*"},
    )
    if not isinstance(fetched, FetchResult):
        raise PublicAcquisitionError("fetcher must return FetchResult")
    _validate_https_endpoint(
        fetched.final_url,
        field="fetched final_url",
        allowed_hosts=normalized["allowed_hosts"],
    )
    if fetched.status_code < 200 or fetched.status_code >= 300:
        raise PublicAcquisitionError(
            f"artifact fetch returned non-success status {fetched.status_code}"
        )

    artifact = fetched.body
    actual_size = len(artifact)
    actual_sha = hashlib.sha256(artifact).hexdigest()
    if actual_size != normalized["expected_size_bytes"]:
        raise PublicAcquisitionError(
            "downloaded artifact size does not match authoritative metadata"
        )
    if actual_sha != normalized["expected_sha256"]:
        raise PublicAcquisitionError(
            "downloaded artifact SHA-256 does not match authoritative metadata"
        )

    manifest_bytes, declaration_bytes = _build_binding_documents(
        candidate=normalized,
        artifact_sha256=actual_sha,
        artifact_size_bytes=actual_size,
        final_url=fetched.final_url,
    )
    try:
        authenticated = authenticate_acquisition_record_binding(
            evidence_bytes=artifact,
            acquisition_manifest_bytes=manifest_bytes,
            acquisition_declaration_bytes=declaration_bytes,
        )
    except AcquisitionRecordBindingError as exc:
        raise PublicAcquisitionError(
            "generated acquisition record failed exact-byte self-authentication"
        ) from exc

    receipt = {
        "schema_version": PUBLIC_ACQUISITION_RECEIPT_SCHEMA_VERSION,
        "candidate_id": normalized["candidate_id"],
        "decision": AUTO,
        "executed": True,
        "artifact_path": normalized["artifact_path"],
        "artifact_sha256": actual_sha,
        "artifact_size_bytes": actual_size,
        "metadata_sha256": observed_metadata_sha,
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "acquisition_declaration_sha256": hashlib.sha256(
            declaration_bytes
        ).hexdigest(),
        "recorded_acquisition_provenance_authenticated": authenticated[
            "recorded_acquisition_provenance_authenticated"
        ],
        "scientific_status_changed": False,
        "requires_scientific_intake": True,
    }
    receipt_bytes = _canonical_json_bytes(receipt)

    artifact_path = _relative_artifact_path(normalized["artifact_path"])
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        recognized_markers=("acquisition_receipt.json",),
    ) as staging:
        target = staging.joinpath(*artifact_path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact)
        (staging / "source_metadata.json").write_bytes(metadata_bytes)
        (staging / "acquisition_manifest.json").write_bytes(manifest_bytes)
        (staging / "acquisition_declaration.json").write_bytes(declaration_bytes)
        (staging / "acquisition_receipt.json").write_bytes(receipt_bytes)

    return receipt


__all__ = [
    "AUTO",
    "BLOCKED",
    "REVIEW_REQUIRED",
    "DEFAULT_MAX_AUTO_ARTIFACT_BYTES",
    "DEFAULT_MAX_AUTO_BATCH_BYTES",
    "FetchResult",
    "PUBLIC_ACQUISITION_CANDIDATE_SCHEMA_VERSION",
    "PUBLIC_ACQUISITION_RECEIPT_SCHEMA_VERSION",
    "PublicAcquisitionError",
    "PublicAcquisitionTransportError",
    "acquire_public_artifact",
    "assess_public_acquisition_candidate",
    "fetch_https_bytes",
    "normalize_public_acquisition_candidate",
    "plan_public_acquisition_queue",
]
