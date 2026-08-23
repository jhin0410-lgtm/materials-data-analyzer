"""Acquire exact paper/official bytes for IN625 geometry-condition mapping."""
from __future__ import annotations

import hashlib
import html
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pypdf import PdfReader

from .in625_geometry_condition_multisource_policy import (
    ACTION_CLASS,
    ALLOWED_HOSTS,
    MAX_REQUESTS,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_BYTES,
    POLICY_ID,
    TIMEOUT_SECONDS,
)


class GeometryConditionSourceAcquisitionError(ValueError):
    """Raised when source acquisition cannot preserve finite authority."""


@dataclass(frozen=True)
class FetchResult:
    body: bytes
    final_url: str
    status_code: int
    content_type: str | None


Fetcher = Callable[..., FetchResult]


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


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
        _validate_https_url(newurl, self._allowed_hosts, "redirect URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometryConditionSourceAcquisitionError(message)


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256(raw)


def _validate_https_url(url: str, allowed_hosts: Sequence[str], field: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise GeometryConditionSourceAcquisitionError(f"{field} has invalid port") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in set(allowed_hosts)
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise GeometryConditionSourceAcquisitionError(
            f"{field} left exact HTTPS source authority: {url}"
        )


def fetch_exact_source(
    url: str,
    *,
    allowed_hosts: Sequence[str],
    max_bytes: int,
    timeout_seconds: float,
) -> FetchResult:
    """Fetch one exact source under host and byte restrictions."""
    _validate_https_url(url, allowed_hosts, "source URL")
    _require(
        isinstance(max_bytes, int) and not isinstance(max_bytes, bool) and max_bytes > 0,
        "max_bytes must be positive",
    )
    _require(timeout_seconds > 0, "timeout_seconds must be positive")
    opener = build_opener(_RestrictedRedirectHandler(allowed_hosts))
    request = Request(
        url,
        headers={
            "User-Agent": "materials-data-analyzer/geometry-condition-evidence/1.1",
            "Accept": "text/html,application/pdf,*/*;q=0.1",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=float(timeout_seconds)) as response:
            final_url = response.geturl()
            _validate_https_url(final_url, allowed_hosts, "final URL")
            status = int(getattr(response, "status", response.getcode()))
            _require(200 <= status < 300, f"source HTTP status was {status}")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared = int(content_length)
                except ValueError as exc:
                    raise GeometryConditionSourceAcquisitionError(
                        "source Content-Length is invalid"
                    ) from exc
                _require(0 <= declared <= max_bytes, "source Content-Length exceeds budget")
            body = response.read(max_bytes + 1)
            _require(len(body) <= max_bytes, "source bytes exceeded per-source budget")
            _require(bool(body), "source returned empty bytes")
            return FetchResult(
                body=body,
                final_url=final_url,
                status_code=status,
                content_type=response.headers.get("Content-Type"),
            )
    except GeometryConditionSourceAcquisitionError:
        raise
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise GeometryConditionSourceAcquisitionError(
            f"source fetch failed operationally: {exc}"
        ) from exc


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _html_pages(body: bytes) -> list[str]:
    decoded = body.decode("utf-8", errors="replace")
    parser = _TextCollector()
    parser.feed(decoded)
    text = _normalize_text(" ".join(parser.parts))
    _require(bool(text), "HTML source produced no extractable text")
    return [text]


def _pdf_pages(
    body: bytes,
    *,
    source_id: str,
    content_type: str | None,
) -> list[str]:
    if not body.startswith(b"%PDF-"):
        raise GeometryConditionSourceAcquisitionError(
            f"{source_id} expected PDF bytes but transport returned non-PDF body "
            f"(content_type={content_type!r}, size={len(body)}, sha256={_sha256(body)})"
        )
    try:
        reader = PdfReader(BytesIO(body), strict=False)
        pages = [_normalize_text(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise GeometryConditionSourceAcquisitionError(
            f"{source_id} PDF could not be parsed "
            f"(size={len(body)}, sha256={_sha256(body)}): {exc}"
        ) from exc
    _require(any(pages), f"{source_id} PDF produced no extractable text")
    return pages


def _claim_receipt(
    claim: Mapping[str, Any],
    pages: Sequence[str],
    *,
    is_pdf: bool,
) -> dict[str, Any]:
    claim_id = claim.get("claim_id")
    anchor = claim.get("anchor_regex")
    scope = claim.get("scope")
    _require(isinstance(claim_id, str) and claim_id, "claim_id is missing")
    _require(isinstance(anchor, str) and anchor, f"{claim_id} anchor is missing")
    _require(isinstance(scope, str) and scope, f"{claim_id} scope is missing")
    try:
        pattern = re.compile(anchor, flags=re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        raise GeometryConditionSourceAcquisitionError(
            f"invalid claim anchor for {claim_id}: {exc}"
        ) from exc
    matches: list[dict[str, Any]] = []
    for page_index, text in enumerate(pages):
        match = pattern.search(text)
        if match is None:
            continue
        encoded = match.group(0).encode("utf-8")
        matches.append(
            {
                "page_index_zero_based": page_index if is_pdf else None,
                "matched_text_sha256": _sha256(encoded),
                "matched_text_utf8_bytes": len(encoded),
            }
        )
    return {
        "claim_id": claim_id,
        "scope": scope,
        "anchor_regex_sha256": _sha256(anchor.encode("utf-8")),
        "matched": bool(matches),
        "match_count": len(matches),
        "matches": matches,
        "source_text_persisted": False,
    }


def acquire_geometry_condition_sources(
    *,
    qualification: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    fetcher: Fetcher = fetch_exact_source,
) -> dict[str, Any]:
    """Acquire all exact configured sources and bind claim anchors to source bytes."""
    _require(
        qualification.get("qualification_status")
        == "exact_multisource_condition_evidence_policy_authenticated",
        "multi-source policy qualification is not authenticated",
    )
    _require(qualification.get("policy_id") == POLICY_ID, "policy identity drifted")
    _require(qualification.get("action_class") == ACTION_CLASS, "action class drifted")
    _require(qualification.get("source_count") == MAX_REQUESTS, "source count drifted")
    _require(
        qualification.get("allowed_hosts") == list(ALLOWED_HOSTS),
        "allowed hosts drifted",
    )
    _require(qualification.get("max_requests") == MAX_REQUESTS, "request budget drifted")
    _require(
        qualification.get("max_source_bytes") == MAX_SOURCE_BYTES
        and qualification.get("max_total_bytes") == MAX_TOTAL_BYTES,
        "byte budgets drifted",
    )
    _require(
        qualification.get("network_access_performed") is False,
        "qualification claimed network access",
    )

    sources = source_registry.get("sources")
    _require(
        isinstance(sources, list) and len(sources) == MAX_REQUESTS,
        "source registry count drifted",
    )
    results: list[dict[str, Any]] = []
    total_bytes = 0
    for request_index, raw_source in enumerate(sources, start=1):
        _require(isinstance(raw_source, Mapping), "source entry must be an object")
        source_id = raw_source.get("source_id")
        url = raw_source.get("url")
        media_type = raw_source.get("media_type")
        _require(isinstance(source_id, str) and source_id, "source_id missing")
        _require(isinstance(url, str) and url, f"{source_id} URL missing")
        _require(media_type in {"html", "pdf"}, f"{source_id} media type unsupported")
        fetched = fetcher(
            url,
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_SOURCE_BYTES,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        _require(isinstance(fetched, FetchResult), "fetcher must return FetchResult")
        _validate_https_url(fetched.final_url, ALLOWED_HOSTS, "fetched final URL")
        _require(200 <= fetched.status_code < 300, "fetcher returned non-success status")
        total_bytes += len(fetched.body)
        _require(
            total_bytes <= MAX_TOTAL_BYTES,
            "multi-source total byte budget exceeded",
        )
        pages = (
            _pdf_pages(
                fetched.body,
                source_id=source_id,
                content_type=fetched.content_type,
            )
            if media_type == "pdf"
            else _html_pages(fetched.body)
        )
        claims_raw = raw_source.get("claims_under_review")
        _require(
            isinstance(claims_raw, list) and claims_raw,
            f"{source_id} claims missing",
        )
        claim_receipts = [
            _claim_receipt(claim, pages, is_pdf=media_type == "pdf")
            for claim in claims_raw
            if isinstance(claim, Mapping)
        ]
        _require(
            len(claim_receipts) == len(claims_raw),
            f"{source_id} claim entry malformed",
        )
        all_matched = all(item["matched"] for item in claim_receipts)
        if not all_matched:
            missing = [
                item["claim_id"] for item in claim_receipts if not item["matched"]
            ]
            raise GeometryConditionSourceAcquisitionError(
                f"{source_id} required claim anchors did not match exact source bytes: "
                + ", ".join(missing)
            )
        results.append(
            {
                "request_index": request_index,
                "source_id": source_id,
                "source_class": raw_source.get("source_class"),
                "authority": raw_source.get("authority"),
                "title": raw_source.get("title"),
                "authors": raw_source.get("authors"),
                "publication_date": raw_source.get("publication_date"),
                "document_date_status": raw_source.get("document_date_status"),
                "doi": raw_source.get("doi"),
                "requested_url": url,
                "final_url": fetched.final_url,
                "media_type": media_type,
                "http_content_type": fetched.content_type,
                "source_sha256": _sha256(fetched.body),
                "source_size_bytes": len(fetched.body),
                "pdf_page_count": len(pages) if media_type == "pdf" else None,
                "claims": claim_receipts,
                "all_claim_anchors_matched": True,
                "row_level_measurement_authority": False,
                "source_bytes_persisted": False,
                "scientific_status_changed": False,
            }
        )

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "acquisition_status": "exact_multisource_condition_evidence_acquired",
        "policy_id": POLICY_ID,
        "policy_sha256": qualification.get("policy_sha256"),
        "registry_git_blob_sha1": qualification.get("registry_git_blob_sha1"),
        "source_count": len(results),
        "network_requests_performed": len(results),
        "network_request_budget": MAX_REQUESTS,
        "total_source_bytes_observed": total_bytes,
        "sources": results,
        "all_sources_fetched": len(results) == MAX_REQUESTS,
        "all_claim_anchors_matched": all(
            item["all_claim_anchors_matched"] for item in results
        ),
        "unrestricted_network_search_performed": False,
        "caller_authored_url_used": False,
        "arbitrary_url_fetch_performed": False,
        "source_bytes_persisted": False,
        "paper_claims_promoted_to_row_level_authority": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "scientific_status_changed": False,
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


__all__ = [
    "FetchResult",
    "GeometryConditionSourceAcquisitionError",
    "acquire_geometry_condition_sources",
    "fetch_exact_source",
]
