"""Discover calibration-record candidates from the mission-pinned NIST AMMT publication index.

Discovery is intentionally weaker than acquisition authority. The capability performs one exact
GET to the official curated NIST index, extracts and ranks candidate publication links, and never
follows those links or converts them into execution/scientific authority.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse

from .in625_geometry_condition_source_acquisition import FetchResult, fetch_exact_source
from .nist_ammt_source_discovery_policy import (
    ACTION_CLASS,
    ALLOWED_HOSTS,
    CANDIDATE_LINK_HOSTS,
    MAX_CANDIDATES,
    MAX_REQUESTS,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_BYTES,
    POLICY_ID,
    QUERY_TERMS,
    SOURCE_ID,
    SOURCE_URL,
    TIMEOUT_SECONDS,
)

NEXT_ACTION_CLASS = "experiment_specific_calibration_record_candidate_acquisition"
IMPLEMENTATION_ID = "nist-ammt-curated-publication-index-discovery-v1"
FACTORY_ID = "mission-pinned-official-index-discovery-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "mission_pinned_source_index_authentication",
    "bounded_official_index_retrieval",
    "provenance_bound_candidate_ranking",
)
_TERM_WEIGHTS = {
    "ammt": 4,
    "calibration": 6,
    "laser": 5,
    "power": 5,
    "spot": 4,
    "metrology": 4,
    "machine-setting": 6,
}


class NistAmmtCalibrationSourceDiscoveryError(ValueError):
    """Raised when bounded source discovery leaves its authenticated authority."""


Fetcher = Callable[..., FetchResult]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistAmmtCalibrationSourceDiscoveryError(message)


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


def _validate_candidate_url(url: str) -> str | None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in CANDIDATE_LINK_HOSTS
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return host


class _PublicationIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._li_stack: list[dict[str, Any]] = []
        self._anchor_stack: list[dict[str, Any]] = []
        self.entries: list[dict[str, Any]] = []
        self.page_text_parts: list[str] = []
        self._suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self._suppressed_depth += 1
            return
        if self._suppressed_depth:
            return
        if tag == "li":
            self._li_stack.append({"text": [], "links": [], "order": len(self.entries)})
        if tag == "a":
            href = next((value for key, value in attrs if key.lower() == "href"), None)
            anchor = {"href": href, "text": []}
            self._anchor_stack.append(anchor)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg"}:
            if self._suppressed_depth:
                self._suppressed_depth -= 1
            return
        if self._suppressed_depth:
            return
        if tag == "a" and self._anchor_stack:
            anchor = self._anchor_stack.pop()
            if self._li_stack:
                self._li_stack[-1]["links"].append(anchor)
        if tag == "li" and self._li_stack:
            entry = self._li_stack.pop()
            if entry["links"]:
                self.entries.append(entry)

    def handle_data(self, data: str) -> None:
        if self._suppressed_depth or not data.strip():
            return
        self.page_text_parts.append(data)
        if self._li_stack:
            self._li_stack[-1]["text"].append(data)
        if self._anchor_stack:
            self._anchor_stack[-1]["text"].append(data)


def _candidate_records(body: bytes) -> tuple[list[dict[str, Any]], str]:
    decoded = body.decode("utf-8", errors="replace")
    parser = _PublicationIndexParser()
    parser.feed(decoded)
    page_text = _normalize_text(" ".join(parser.page_text_parts))
    _require(bool(page_text), "NIST AMMT publication index produced no visible text")
    _require(
        "AMMT" in page_text or "Additive Manufacturing Metrology Testbed" in page_text,
        "NIST AMMT publication index identity text was not found",
    )

    by_url: dict[str, dict[str, Any]] = {}
    discovery_order = 0
    for entry in parser.entries:
        context = _normalize_text(" ".join(entry["text"]))
        for raw_link in entry["links"]:
            href = raw_link.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            url = urljoin(SOURCE_URL, html.unescape(href.strip()))
            host = _validate_candidate_url(url)
            if host is None or url == SOURCE_URL:
                continue
            label = _normalize_text(" ".join(raw_link.get("text", [])))
            searchable = f"{context} {label} {url}".lower()
            matched_terms = [term for term in QUERY_TERMS if term.lower() in searchable]
            if not matched_terms:
                continue
            score = sum(_TERM_WEIGHTS[term.lower()] for term in matched_terms)
            record = {
                "candidate_id": "nist-ammt-index-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
                "discovery_order": discovery_order,
                "url": url,
                "link_host": host,
                "link_label": label[:240],
                "citation_context_sha256": _sha256(context.encode("utf-8")),
                "citation_context_utf8_bytes": len(context.encode("utf-8")),
                "matched_query_terms": matched_terms,
                "relevance_score": score,
                "discovered_from_source_id": SOURCE_ID,
                "candidate_url_followed": False,
                "acquisition_authorized": False,
                "row_level_measurement_authority": False,
                "scientific_status_changed": False,
            }
            discovery_order += 1
            prior = by_url.get(url)
            if prior is None or (score, -record["discovery_order"]) > (
                prior["relevance_score"],
                -prior["discovery_order"],
            ):
                by_url[url] = record

    ranked = sorted(
        by_url.values(),
        key=lambda item: (-item["relevance_score"], item["discovery_order"], item["url"]),
    )[:MAX_CANDIDATES]
    for rank, record in enumerate(ranked, start=1):
        record["rank"] = rank
    return ranked, page_text


def discover_nist_ammt_calibration_sources(
    *,
    qualification: Mapping[str, Any],
    fetcher: Fetcher = fetch_exact_source,
) -> dict[str, Any]:
    """Fetch one exact NIST index and rank discovery-only calibration candidates."""
    _require(
        qualification.get("qualification_status")
        == "exact_nist_ammt_source_discovery_policy_authenticated",
        "NIST AMMT discovery policy is not authenticated",
    )
    _require(qualification.get("policy_id") == POLICY_ID, "discovery policy identity drifted")
    _require(qualification.get("action_class") == ACTION_CLASS, "discovery action class drifted")
    _require(qualification.get("source_id") == SOURCE_ID, "source index identity drifted")
    _require(qualification.get("source_url") == SOURCE_URL, "source index URL drifted")
    _require(qualification.get("allowed_hosts") == list(ALLOWED_HOSTS), "source host authority drifted")
    _require(
        qualification.get("max_requests") == MAX_REQUESTS == 1
        and qualification.get("max_source_bytes") == MAX_SOURCE_BYTES
        and qualification.get("max_total_bytes") == MAX_TOTAL_BYTES,
        "discovery network budget drifted",
    )
    _require(
        qualification.get("network_access_performed") is False
        and qualification.get("unrestricted_search_performed") is False
        and qualification.get("caller_authored_url_used") is False
        and qualification.get("candidate_urls_gain_acquisition_authority") is False,
        "discovery qualification pre-authorized forbidden behavior",
    )

    fetched = fetcher(
        SOURCE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        max_bytes=min(MAX_SOURCE_BYTES, MAX_TOTAL_BYTES),
        timeout_seconds=TIMEOUT_SECONDS,
    )
    _require(isinstance(fetched, FetchResult), "discovery fetcher must return FetchResult")
    parsed_final = urlparse(fetched.final_url)
    _require(
        parsed_final.scheme.lower() == "https"
        and (parsed_final.hostname or "").lower() in ALLOWED_HOSTS,
        "discovery final URL left exact NIST host authority",
    )
    _require(200 <= fetched.status_code < 300, "discovery fetch returned non-success status")
    _require(0 < len(fetched.body) <= MAX_TOTAL_BYTES, "discovery source bytes exceeded total budget")

    candidates, page_text = _candidate_records(fetched.body)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": ACTION_CLASS,
        "discovery_status": "official_nist_ammt_publication_index_reviewed",
        "policy_id": POLICY_ID,
        "policy_sha256": qualification.get("policy_sha256"),
        "source_index": {
            "source_id": SOURCE_ID,
            "requested_url": SOURCE_URL,
            "final_url": fetched.final_url,
            "source_sha256": _sha256(fetched.body),
            "source_size_bytes": len(fetched.body),
            "http_content_type": fetched.content_type,
            "visible_text_sha256": _sha256(page_text.encode("utf-8")),
            "visible_text_utf8_bytes": len(page_text.encode("utf-8")),
            "source_text_persisted": False,
        },
        "network_requests_performed": 1,
        "network_request_budget": 1,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "candidate_links_followed": 0,
        "unrestricted_search_performed": False,
        "caller_authored_url_used": False,
        "arbitrary_url_fetch_performed": False,
        "candidate_urls_gain_acquisition_authority": False,
        "discovered_candidates_are_scientific_evidence": False,
        "source_index_text_is_row_level_measurement_authority": False,
        "global_evidence_unavailability_claimed": False,
        "scientific_status_changed": False,
        "next_action": {
            "action_class": NEXT_ACTION_CLASS,
            "objective": (
                "Acquire and review the highest-ranked experiment-relevant calibration/metrology "
                "candidate only under separately authenticated acquisition authority, then test "
                "whether it establishes the exact mds2-2923 AMMT machine-setting/calibrated-power "
                "and protocol bridge."
            ),
            "candidate_ids": [item["candidate_id"] for item in candidates],
            "automatic_acquisition_authorized": False,
            "caller_authored_arbitrary_urls_authorized": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "NEXT_ACTION_CLASS",
    "NistAmmtCalibrationSourceDiscoveryError",
    "REQUIRED_VERIFIED_PRIMITIVES",
    "discover_nist_ammt_calibration_sources",
]
