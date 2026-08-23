"""Acquire exact Naderi bytes and bind the finite mds2-2923 reference-chain claims."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import unicodedata
from io import BytesIO
from typing import Any, Callable, Mapping, Sequence

from pypdf import PdfReader

from .in625_geometry_condition_source_acquisition import FetchResult, fetch_exact_source
from .nist_mds2_2923_reference_chain_policy import (
    ACTION_CLASS,
    ALLOWED_HOSTS,
    CLAIMS,
    MATCH_MODE,
    MAX_CLAIM_SPAN_UTF8_BYTES,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_BYTES,
    POLICY_ID,
    SOURCE_DOI,
    SOURCE_ID,
    SOURCE_SHA256,
    SOURCE_SIZE_BYTES,
    SOURCE_URL,
    TIMEOUT_SECONDS,
)

IMPLEMENTATION_ID = "mds2-2923-naderi-reference-chain-evidence-v1"
TEXT_NORMALIZATION_ID = "pdf-discretionary-word-break-normalization-v2"
_CONTROL_CLASS = r"\x00-\x08\x0b\x0c\x0e-\x1f\x7f"


class NistMds22923ReferenceChainEvidenceError(ValueError):
    """Raised when reference-chain acquisition leaves exact source authority."""


Fetcher = Callable[..., FetchResult]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistMds22923ReferenceChainEvidenceError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256(raw)


def _normalize_text(value: str) -> str:
    """Normalize only Unicode compatibility and PDF discretionary word breaks."""
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(
        rf"(?<=\w)\s*[{_CONTROL_CLASS}]\s*(?=\w)",
        "",
        value,
    )
    value = re.sub(r"(?<=\w)\s*\u00ad\s*(?=\w)", "", value)
    value = re.sub(rf"[{_CONTROL_CLASS}]", "", value)
    value = value.replace("\u00ad", "")
    return re.sub(r"\s+", " ", value).strip()


def _pdf_pages(body: bytes) -> list[str]:
    _require(body.startswith(b"%PDF-"), "Naderi reference source is not PDF bytes")
    try:
        reader = PdfReader(BytesIO(body), strict=False)
        pages = [_normalize_text(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise NistMds22923ReferenceChainEvidenceError(
            f"Naderi reference PDF could not be parsed: {exc}"
        ) from exc
    _require(any(pages), "Naderi reference PDF produced no extractable text")
    return pages


def _claim_receipt(
    claim_id: str,
    required_fragments: Sequence[str],
    scope: str,
    pages: Sequence[str],
) -> dict[str, Any]:
    _require(bool(required_fragments), f"reference-chain claim {claim_id} has no fragments")
    _require(
        all(isinstance(item, str) and item for item in required_fragments),
        f"reference-chain claim {claim_id} fragments are invalid",
    )
    gap = f".{{0,{MAX_CLAIM_SPAN_UTF8_BYTES}}}?"
    pattern_text = gap.join(re.escape(item) for item in required_fragments)
    pattern = re.compile(pattern_text, flags=re.IGNORECASE | re.DOTALL)
    matches: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        match = pattern.search(page)
        if match is None:
            continue
        raw = match.group(0).encode("utf-8")
        if len(raw) > MAX_CLAIM_SPAN_UTF8_BYTES:
            continue
        matches.append(
            {
                "page_index_zero_based": page_index,
                "matched_span_sha256": _sha256(raw),
                "matched_span_utf8_bytes": len(raw),
            }
        )
    return {
        "claim_id": claim_id,
        "scope": scope,
        "match_mode": MATCH_MODE,
        "max_span_utf8_bytes": MAX_CLAIM_SPAN_UTF8_BYTES,
        "required_fragment_count": len(required_fragments),
        "required_fragments_sha256": _canonical_sha(list(required_fragments)),
        "matched": bool(matches),
        "match_count": len(matches),
        "matches": matches,
        "source_text_persisted": False,
    }


def _claim_diagnostics(
    failed_claims: Sequence[tuple[str, Sequence[str], str]],
    pages: Sequence[str],
) -> str:
    """Return fragment-presence booleans only; never source text."""
    lowered_pages = [page.casefold() for page in pages]
    diagnostics: dict[str, dict[str, bool]] = {}
    for claim_id, fragments, _scope in failed_claims:
        diagnostics[claim_id] = {
            fragment: any(fragment.casefold() in page for page in lowered_pages)
            for fragment in fragments
        }
    return json.dumps(diagnostics, sort_keys=True, separators=(",", ":"))


def acquire_naderi_reference_chain_evidence(
    *,
    qualification: Mapping[str, Any],
    fetcher: Fetcher = fetch_exact_source,
) -> dict[str, Any]:
    """Acquire one exact NIST-hosted paper and emit bounded claim receipts only."""
    _require(
        qualification.get("qualification_status")
        == "exact_nist_mds2_2923_reference_chain_policy_authenticated",
        "reference-chain policy is not authenticated",
    )
    _require(qualification.get("policy_id") == POLICY_ID, "reference policy identity drifted")
    _require(qualification.get("action_class") == ACTION_CLASS, "reference action class drifted")
    _require(qualification.get("source_id") == SOURCE_ID, "reference source identity drifted")
    _require(qualification.get("source_url") == SOURCE_URL, "reference source URL drifted")
    _require(qualification.get("source_sha256") == SOURCE_SHA256, "reference source SHA drifted")
    _require(
        qualification.get("source_size_bytes") == SOURCE_SIZE_BYTES,
        "reference source size drifted",
    )
    _require(
        qualification.get("allowed_hosts") == list(ALLOWED_HOSTS)
        and qualification.get("max_requests") == 1
        and qualification.get("max_source_bytes") == MAX_SOURCE_BYTES
        and qualification.get("max_total_bytes") == MAX_TOTAL_BYTES,
        "reference-chain network authority drifted",
    )
    _require(
        qualification.get("claim_match_mode") == MATCH_MODE
        and qualification.get("max_claim_span_utf8_bytes") == MAX_CLAIM_SPAN_UTF8_BYTES,
        "reference-chain claim matching authority drifted",
    )
    _require(
        qualification.get("network_access_performed") is False
        and qualification.get("caller_authored_url_used") is False
        and qualification.get("scientific_status_changed") is False,
        "reference-chain qualification pre-authorized forbidden behavior",
    )

    fetched = fetcher(
        SOURCE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        max_bytes=min(MAX_SOURCE_BYTES, MAX_TOTAL_BYTES),
        timeout_seconds=TIMEOUT_SECONDS,
    )
    _require(isinstance(fetched, FetchResult), "reference fetcher must return FetchResult")
    _require(fetched.final_url == SOURCE_URL, "reference source final URL drifted")
    _require(200 <= fetched.status_code < 300, "reference source returned non-success status")
    _require(len(fetched.body) == SOURCE_SIZE_BYTES, "reference source exact size changed")
    observed_sha = _sha256(fetched.body)
    _require(observed_sha == SOURCE_SHA256, "reference source exact SHA-256 changed")
    pages = _pdf_pages(fetched.body)
    claims = [
        _claim_receipt(claim_id, fragments, scope, pages)
        for claim_id, fragments, scope in CLAIMS
    ]
    failed_ids = {item["claim_id"] for item in claims if not item["matched"]}
    if failed_ids:
        failed_claims = [item for item in CLAIMS if item[0] in failed_ids]
        diagnostics = _claim_diagnostics(failed_claims, pages)
        raise NistMds22923ReferenceChainEvidenceError(
            "required Naderi reference-chain claim did not match: "
            + ", ".join(sorted(failed_ids))
            + "; bounded_fragment_hits="
            + diagnostics
        )

    report: dict[str, Any] = {
        "schema_version": "1.1",
        "action_class": ACTION_CLASS,
        "acquisition_status": "exact_naderi_reference_chain_evidence_acquired",
        "policy_id": POLICY_ID,
        "policy_sha256": qualification.get("policy_sha256"),
        "mission_sha256": qualification.get("mission_sha256"),
        "source": {
            "source_id": SOURCE_ID,
            "doi": SOURCE_DOI,
            "requested_url": SOURCE_URL,
            "final_url": fetched.final_url,
            "source_sha256": observed_sha,
            "source_size_bytes": len(fetched.body),
            "pdf_page_count": len(pages),
            "http_content_type": fetched.content_type,
            "pypdf_version": importlib.metadata.version("pypdf"),
            "text_normalization_id": TEXT_NORMALIZATION_ID,
            "source_bytes_persisted": False,
            "source_text_persisted": False,
            "row_level_measurement_authority": False,
        },
        "claim_match_mode": MATCH_MODE,
        "max_claim_span_utf8_bytes": MAX_CLAIM_SPAN_UTF8_BYTES,
        "claims": claims,
        "all_claims_matched": True,
        "network_requests_performed": 1,
        "unrestricted_search_performed": False,
        "caller_authored_url_used": False,
        "arbitrary_url_fetch_performed": False,
        "same_platform_promoted_to_experiment_identity": False,
        "reference_chain_promoted_to_power_conversion": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "global_evidence_unavailability_claimed": False,
        "scientific_status_changed": False,
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


__all__ = [
    "IMPLEMENTATION_ID",
    "NistMds22923ReferenceChainEvidenceError",
    "TEXT_NORMALIZATION_ID",
    "acquire_naderi_reference_chain_evidence",
]
