"""Acquire one NIST calibration candidate only from authenticated discovery provenance.

The capability derives the candidate URL from the verified predecessor discovery report, then derives
one full-text URL from the acquired NIST publication page. It accepts no caller-authored URL and
never treats acquisition or parsing success as a calibration bridge or row-level authority.
"""
from __future__ import annotations

import hashlib
import html
import importlib.metadata
import json
import re
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, urljoin, urlparse

from pypdf import PdfReader

from .in625_geometry_condition_source_acquisition import FetchResult, fetch_exact_source
from .nist_ammt_candidate_acquisition_policy import (
    ACTION_CLASS,
    CANDIDATE_PAGE_ALLOWED_HOSTS,
    CANDIDATE_PATH_PREFIX,
    DISCOVERY_POLICY_ID,
    DISCOVERY_SOURCE_ID,
    FULL_TEXT_ALLOWED_HOSTS,
    FULL_TEXT_LINK_LABEL,
    FULL_TEXT_PATH_PREFIX,
    FULL_TEXT_REQUIRED_QUERY_PARAMETER,
    MAX_CANDIDATE_PAGE_BYTES,
    MAX_FULL_TEXT_BYTES,
    MAX_REQUESTS,
    MAX_TOTAL_BYTES,
    POLICY_ID,
    REQUIRED_CANDIDATE_HOST,
    REQUIRED_CANDIDATE_RANK,
    TIMEOUT_SECONDS,
    authenticate_nist_ammt_candidate_acquisition_policy,
)

IMPLEMENTATION_ID = "nist-ammt-derived-calibration-candidate-acquisition-v1"
FACTORY_ID = "provenance-derived-official-candidate-acquisition-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "authenticated_discovery_report_binding",
    "derived_candidate_url_authorization",
    "candidate_page_local_download_derivation",
    "bounded_nist_pdf_acquisition",
    "provenance_bound_calibration_intake",
)


class NistAmmtCalibrationCandidateAcquisitionError(ValueError):
    """Raised when derived candidate acquisition leaves authenticated authority."""


Fetcher = Callable[..., FetchResult]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistAmmtCalibrationCandidateAcquisitionError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _validate_self_hash(
    value: Mapping[str, Any],
    field: str,
) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _validate_manifest(manifest: Mapping[str, Any]) -> str:
    digest = manifest.get("manifest_sha256")
    _require(isinstance(digest, str) and len(digest) == 64, "predecessor manifest SHA is missing")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    _require(_canonical_sha(unsigned) == digest, "predecessor manifest self binding is invalid")
    return digest


def _validate_candidate_url(url: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise NistAmmtCalibrationCandidateAcquisitionError(
            "derived candidate URL has invalid port"
        ) from exc
    _require(
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() == REQUIRED_CANDIDATE_HOST
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and parsed.path.startswith(CANDIDATE_PATH_PREFIX)
        and not parsed.fragment,
        "derived candidate URL left intrinsic NIST publication authority",
    )


def _validate_full_text_url(url: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise NistAmmtCalibrationCandidateAcquisitionError(
            "derived full-text URL has invalid port"
        ) from exc
    query = parse_qs(parsed.query, keep_blank_values=True)
    _require(
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() in set(FULL_TEXT_ALLOWED_HOSTS)
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and parsed.path == FULL_TEXT_PATH_PREFIX
        and not parsed.fragment,
        "derived full-text URL left intrinsic NIST PDF authority",
    )
    values = query.get(FULL_TEXT_REQUIRED_QUERY_PARAMETER)
    _require(
        isinstance(values, list)
        and len(values) == 1
        and values[0].isdigit()
        and set(query) == {FULL_TEXT_REQUIRED_QUERY_PARAMETER},
        "derived full-text URL query contract drifted",
    )


class _PublicationPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.visible_parts: list[str] = []
        self.anchors: list[dict[str, str]] = []
        self._anchor: dict[str, Any] | None = None
        self._suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self._suppressed_depth += 1
            return
        if self._suppressed_depth:
            return
        if tag == "a":
            href = next((value for key, value in attrs if key.lower() == "href"), None)
            self._anchor = {"href": href, "text": []}

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg"}:
            if self._suppressed_depth:
                self._suppressed_depth -= 1
            return
        if self._suppressed_depth:
            return
        if tag == "a" and self._anchor is not None:
            href = self._anchor.get("href")
            if isinstance(href, str):
                self.anchors.append(
                    {
                        "href": href,
                        "label": _normalize_text(" ".join(self._anchor["text"])),
                    }
                )
            self._anchor = None

    def handle_data(self, data: str) -> None:
        if self._suppressed_depth or not data.strip():
            return
        self.visible_parts.append(data)
        if self._anchor is not None:
            self._anchor["text"].append(data)


def _parse_candidate_page(body: bytes, candidate_url: str) -> tuple[str, str]:
    decoded = body.decode("utf-8", errors="replace")
    parser = _PublicationPageParser()
    parser.feed(decoded)
    visible_text = _normalize_text(" ".join(parser.visible_parts))
    _require(bool(visible_text), "candidate page produced no visible text")
    _require(
        "Published" in visible_text
        and "Author(s)" in visible_text
        and "Download Paper" in visible_text,
        "candidate page did not match NIST publication-page semantics",
    )
    links: list[str] = []
    for anchor in parser.anchors:
        if anchor["label"] != FULL_TEXT_LINK_LABEL:
            continue
        url = urljoin(candidate_url, html.unescape(anchor["href"]).strip())
        try:
            _validate_full_text_url(url)
        except NistAmmtCalibrationCandidateAcquisitionError:
            continue
        links.append(url)
    _require(len(set(links)) == 1, "candidate page did not expose exactly one authorized Local Download")
    return visible_text, links[0]


def _pdf_pages(body: bytes, content_type: str | None) -> list[str]:
    _require(body.startswith(b"%PDF-"), f"full text was not PDF bytes (content_type={content_type!r})")
    try:
        reader = PdfReader(BytesIO(body), strict=False)
        pages = [_normalize_text(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise NistAmmtCalibrationCandidateAcquisitionError(
            f"full-text PDF could not be parsed: {exc}"
        ) from exc
    _require(any(pages), "full-text PDF produced no extractable text")
    return pages


def _claim_receipt(
    *,
    claim_id: str,
    pattern: str,
    pages: Sequence[str],
) -> dict[str, Any]:
    compiled = re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    matches: list[dict[str, Any]] = []
    for page_index, text in enumerate(pages):
        match = compiled.search(text)
        if match is None:
            continue
        raw = match.group(0).encode("utf-8")
        matches.append(
            {
                "page_index_zero_based": page_index,
                "matched_text_sha256": _sha256(raw),
                "matched_text_utf8_bytes": len(raw),
            }
        )
    return {
        "claim_id": claim_id,
        "matched": bool(matches),
        "match_count": len(matches),
        "matches": matches,
        "pattern_sha256": _sha256(pattern.encode("utf-8")),
    }


def build_derived_candidate_authorization(
    *,
    qualification: Mapping[str, Any],
    discovery_report: Mapping[str, Any],
    predecessor_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive one rank-1 candidate authorization from authenticated predecessor artifacts."""
    _require(
        qualification.get("qualification_status")
        == "exact_nist_ammt_candidate_acquisition_policy_authenticated",
        "candidate acquisition policy is not authenticated",
    )
    _require(qualification.get("policy_id") == POLICY_ID, "candidate policy identity drifted")
    _require(qualification.get("action_class") == ACTION_CLASS, "candidate action class drifted")
    discovery_sha = _validate_self_hash(discovery_report, "report_sha256_without_self_field")
    manifest_sha = _validate_manifest(predecessor_manifest)
    _require(
        predecessor_manifest.get("nist_ammt_source_discovery_sha256") == discovery_sha,
        "predecessor manifest is not bound to exact discovery report",
    )
    _require(
        predecessor_manifest.get("generated_next_action_class") == ACTION_CLASS
        and predecessor_manifest.get("third_capability_gap_emitted") is True,
        "predecessor manifest did not reach candidate acquisition frontier",
    )
    _require(
        discovery_report.get("policy_id") == DISCOVERY_POLICY_ID,
        "discovery report policy identity drifted",
    )
    source_index = discovery_report.get("source_index")
    _require(isinstance(source_index, Mapping), "discovery source index is missing")
    _require(
        source_index.get("source_id") == DISCOVERY_SOURCE_ID,
        "discovery source index identity drifted",
    )
    source_index_sha = source_index.get("source_sha256")
    _require(
        isinstance(source_index_sha, str) and len(source_index_sha) == 64,
        "discovery source index SHA is missing",
    )
    _require(
        discovery_report.get("candidate_urls_gain_acquisition_authority") is False
        and discovery_report.get("candidate_links_followed") == 0
        and discovery_report.get("caller_authored_url_used") is False,
        "discovery report already widened candidate authority",
    )
    candidates = discovery_report.get("candidates")
    _require(isinstance(candidates, list) and candidates, "discovery candidates are missing")
    selected = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("rank") == REQUIRED_CANDIDATE_RANK
    ]
    _require(len(selected) == 1, "discovery report must contain exactly one rank-1 candidate")
    candidate = selected[0]
    candidate_id = candidate.get("candidate_id")
    candidate_url = candidate.get("url")
    _require(
        isinstance(candidate_id, str) and candidate_id,
        "rank-1 candidate identity is missing",
    )
    _require(isinstance(candidate_url, str), "rank-1 candidate URL is missing")
    _validate_candidate_url(candidate_url)
    _require(
        candidate.get("link_host") == REQUIRED_CANDIDATE_HOST
        and candidate.get("discovered_from_source_id") == DISCOVERY_SOURCE_ID
        and candidate.get("candidate_url_followed") is False
        and candidate.get("acquisition_authorized") is False
        and candidate.get("row_level_measurement_authority") is False,
        "rank-1 candidate provenance/authority drifted",
    )
    next_action = discovery_report.get("next_action")
    _require(isinstance(next_action, Mapping), "discovery next action is missing")
    candidate_ids = next_action.get("candidate_ids")
    _require(
        next_action.get("action_class") == ACTION_CLASS
        and isinstance(candidate_ids, list)
        and candidate_id in candidate_ids
        and next_action.get("automatic_acquisition_authorized") is False
        and next_action.get("caller_authored_arbitrary_urls_authorized") is False,
        "discovery next-action candidate contract drifted",
    )

    authorization: dict[str, Any] = {
        "schema_version": "1.0",
        "authorization_type": "provenance_derived_nist_candidate_acquisition",
        "policy_id": POLICY_ID,
        "policy_sha256": qualification.get("policy_sha256"),
        "mission_sha256": qualification.get("mission_sha256"),
        "action_class": ACTION_CLASS,
        "discovery_report_sha256": discovery_sha,
        "predecessor_manifest_sha256": manifest_sha,
        "source_index_sha256": source_index_sha,
        "candidate_id": candidate_id,
        "candidate_rank": REQUIRED_CANDIDATE_RANK,
        "candidate_url": candidate_url,
        "candidate_page_allowed_hosts": list(CANDIDATE_PAGE_ALLOWED_HOSTS),
        "full_text_allowed_hosts": list(FULL_TEXT_ALLOWED_HOSTS),
        "max_requests": MAX_REQUESTS,
        "max_candidate_page_bytes": MAX_CANDIDATE_PAGE_BYTES,
        "max_full_text_bytes": MAX_FULL_TEXT_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "caller_authored_url_used": False,
        "candidate_url_derived_from_discovery": True,
        "full_text_url_derived_from_candidate_page": False,
        "scientific_status_change_authorized": False,
    }
    authorization["authorization_sha256"] = _canonical_sha(authorization)
    return authorization


def execute_derived_candidate_acquisition(
    *,
    authorization: Mapping[str, Any],
    fetcher: Fetcher = fetch_exact_source,
) -> dict[str, Any]:
    """Acquire the authorized NIST publication page and its page-derived local PDF."""
    auth_sha = _validate_self_hash(authorization, "authorization_sha256")
    _require(authorization.get("policy_id") == POLICY_ID, "authorization policy drifted")
    _require(authorization.get("action_class") == ACTION_CLASS, "authorization action drifted")
    _require(
        authorization.get("candidate_rank") == REQUIRED_CANDIDATE_RANK
        and authorization.get("candidate_page_allowed_hosts") == list(CANDIDATE_PAGE_ALLOWED_HOSTS)
        and authorization.get("full_text_allowed_hosts") == list(FULL_TEXT_ALLOWED_HOSTS)
        and authorization.get("max_requests") == MAX_REQUESTS
        and authorization.get("max_candidate_page_bytes") == MAX_CANDIDATE_PAGE_BYTES
        and authorization.get("max_full_text_bytes") == MAX_FULL_TEXT_BYTES
        and authorization.get("max_total_bytes") == MAX_TOTAL_BYTES
        and authorization.get("timeout_seconds") == TIMEOUT_SECONDS,
        "authorization network authority drifted",
    )
    _require(
        authorization.get("caller_authored_url_used") is False
        and authorization.get("candidate_url_derived_from_discovery") is True
        and authorization.get("full_text_url_derived_from_candidate_page") is False
        and authorization.get("scientific_status_change_authorized") is False,
        "authorization pre-granted forbidden authority",
    )
    candidate_url = authorization.get("candidate_url")
    _require(isinstance(candidate_url, str), "authorized candidate URL is missing")
    _validate_candidate_url(candidate_url)

    page = fetcher(
        candidate_url,
        allowed_hosts=CANDIDATE_PAGE_ALLOWED_HOSTS,
        max_bytes=MAX_CANDIDATE_PAGE_BYTES,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    _require(isinstance(page, FetchResult), "candidate-page fetcher must return FetchResult")
    _validate_candidate_url(page.final_url)
    _require(200 <= page.status_code < 300, "candidate page fetch returned non-success status")
    _require(0 < len(page.body) <= MAX_CANDIDATE_PAGE_BYTES, "candidate page exceeded byte budget")
    page_text, full_text_url = _parse_candidate_page(page.body, candidate_url)
    _validate_full_text_url(full_text_url)

    remaining = MAX_TOTAL_BYTES - len(page.body)
    _require(remaining > 0, "candidate page exhausted total acquisition byte budget")
    pdf = fetcher(
        full_text_url,
        allowed_hosts=FULL_TEXT_ALLOWED_HOSTS,
        max_bytes=min(MAX_FULL_TEXT_BYTES, remaining),
        timeout_seconds=TIMEOUT_SECONDS,
    )
    _require(isinstance(pdf, FetchResult), "full-text fetcher must return FetchResult")
    _validate_full_text_url(pdf.final_url)
    _require(200 <= pdf.status_code < 300, "full-text fetch returned non-success status")
    _require(
        len(page.body) + len(pdf.body) <= MAX_TOTAL_BYTES,
        "candidate acquisition exceeded total byte budget",
    )
    pages = _pdf_pages(pdf.body, pdf.content_type)

    claims = [
        _claim_receipt(
            claim_id="digital_camera_in_situ_calibration_methodology",
            pattern=r"in-situ calibration techniques.{0,1200}digital camera",
            pages=pages,
        ),
        _claim_receipt(
            claim_id="open_platform_testbed_experiment_scope",
            pattern=r"experiments in this study are conducted on a testbed.{0,1000}open platform control framework",
            pages=pages,
        ),
        _claim_receipt(
            claim_id="spot_calibration_200w_pulsed_condition",
            pattern=r"laser power is set at 200 W.{0,1000}pulsed at 5 Hz",
            pages=pages,
        ),
        _claim_receipt(
            claim_id="d4sigma_spot_definition",
            pattern=r"laser spot diameter can be estimated by D4\s*σ",
            pages=pages,
        ),
        _claim_receipt(
            claim_id="explicit_mds2_2923_identity",
            pattern=r"mds2[- ]?2923",
            pages=pages,
        ),
        _claim_receipt(
            claim_id="explicit_machine_setting_actual_power_bridge",
            pattern=(
                r"(?:180(?:\.0)?\s*W.{0,500}137\.9\s*W|137\.9\s*W.{0,500}180(?:\.0)?\s*W|"
                r"195(?:\.0)?\s*W.{0,500}179\.2\s*W|179\.2\s*W.{0,500}195(?:\.0)?\s*W)"
            ),
            pages=pages,
        ),
    ]
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": ACTION_CLASS,
        "acquisition_status": "derived_nist_calibration_candidate_and_full_text_acquired",
        "authorization_sha256": auth_sha,
        "policy_id": POLICY_ID,
        "policy_sha256": authorization.get("policy_sha256"),
        "mission_sha256": authorization.get("mission_sha256"),
        "discovery_report_sha256": authorization.get("discovery_report_sha256"),
        "predecessor_manifest_sha256": authorization.get("predecessor_manifest_sha256"),
        "source_index_sha256": authorization.get("source_index_sha256"),
        "candidate_id": authorization.get("candidate_id"),
        "candidate_rank": authorization.get("candidate_rank"),
        "candidate_page": {
            "requested_url": candidate_url,
            "final_url": page.final_url,
            "source_sha256": _sha256(page.body),
            "source_size_bytes": len(page.body),
            "http_content_type": page.content_type,
            "visible_text_sha256": _sha256(page_text.encode("utf-8")),
            "visible_text_utf8_bytes": len(page_text.encode("utf-8")),
            "raw_bytes_persisted": False,
        },
        "full_text": {
            "url_derived_from_candidate_page": True,
            "requested_url": full_text_url,
            "final_url": pdf.final_url,
            "source_sha256": _sha256(pdf.body),
            "source_size_bytes": len(pdf.body),
            "http_content_type": pdf.content_type,
            "page_count": len(pages),
            "page_text_sha256": [_sha256(text.encode("utf-8")) for text in pages],
            "extractor": "pypdf",
            "extractor_version": importlib.metadata.version("pypdf"),
            "extractor_strict_mode": False,
            "raw_bytes_persisted": False,
            "full_text_persisted": False,
        },
        "claim_receipts": claims,
        "network_requests_performed": 2,
        "candidate_url_derived_from_discovery": True,
        "full_text_url_derived_from_candidate_page": True,
        "caller_authored_url_used": False,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "acquisition_success_establishes_calibration_bridge": False,
        "global_evidence_unavailability_claimed": False,
        "scientific_status_changed": False,
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def smoke_derived_candidate_acquisition(
    *,
    repository_root: str,
    mission_path: str,
    expected_mission_sha256: str,
    discovery_report: Mapping[str, Any],
    predecessor_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Run a real derived acquisition smoke under the exact predecessor discovery artifacts."""
    qualification = authenticate_nist_ammt_candidate_acquisition_policy(
        repository_root=repository_root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
    )
    authorization = build_derived_candidate_authorization(
        qualification=qualification,
        discovery_report=discovery_report,
        predecessor_manifest=predecessor_manifest,
    )
    return execute_derived_candidate_acquisition(authorization=authorization)


__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "NistAmmtCalibrationCandidateAcquisitionError",
    "REQUIRED_VERIFIED_PRIMITIVES",
    "build_derived_candidate_authorization",
    "execute_derived_candidate_acquisition",
    "smoke_derived_candidate_acquisition",
]
