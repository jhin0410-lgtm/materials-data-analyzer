"""Acquire exact Naderi bytes and bind the finite mds2-2923 reference-chain claims."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from io import BytesIO
from typing import Any, Callable, Mapping, Sequence

from pypdf import PdfReader

from .in625_geometry_condition_source_acquisition import FetchResult, fetch_exact_source
from .nist_mds2_2923_reference_chain_policy import (
    ACTION_CLASS,
    ALLOWED_HOSTS,
    CLAIMS,
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
MAX_CLAIM_MATCH_UTF8_BYTES = 4096
TEXT_NORMALIZATION_ID = "pdf-discretionary-break-normalization-v1"

_DIAGNOSTIC_PROBES: dict[str, tuple[str, ...]] = {
    "naderi-ammt-in625-weaver-detail-reference": (
        "AMMT",
        "195 W",
        "800 mm/s",
        "spot diameters ranging from 50",
        "256",
        "More details are provided",
        "Weaver",
    ),
    "naderi-reference-7-weaver-spot-size-paper": (
        "7. Weaver",
        "Weaver JS",
        "Heigel JC",
        "Lane BM",
        "Laser spot size",
        "scaling laws",
        "laser beam additive manufacturing",
    ),
    "naderi-reference-31-ammt-design": (
        "31. Lane",
        "Lane B",
        "Mekhontsev S",
        "Grantham S",
        "Design, developments, and results",
        "NIST additive manufacturing metrology testbed",
    ),
    "naderi-reference-32-lane-in625-protocol": (
        "32. Lane",
        "Heigel J",
        "Ricker R",
        "Measurements of melt pool geometry",
        "individual laser traces",
        "IN625 bare plates",
    ),
}


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
    # Springer/NIST PDF text extraction can insert non-printing discretionary
    # break controls inside words (for example ``manu\x02facturing``) and soft
    # hyphens. These are layout artifacts, not source semantics. Remove only
    # those non-whitespace controls and soft hyphens before collapsing
    # whitespace so exact source-byte and policy/anchor bindings remain intact.
    value = value.replace("\u00ad", "")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
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
    anchor_regex: str,
    scope: str,
    pages: Sequence[str],
) -> dict[str, Any]:
    bounded = anchor_regex.replace(".*", f".{{0,{MAX_CLAIM_MATCH_UTF8_BYTES}}}?")
    try:
        pattern = re.compile(bounded, flags=re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        raise NistMds22923ReferenceChainEvidenceError(
            f"invalid reference-chain claim anchor {claim_id}: {exc}"
        ) from exc
    matches: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        match = pattern.search(page)
        if match is None:
            continue
        raw = match.group(0).encode("utf-8")
        if len(raw) > MAX_CLAIM_MATCH_UTF8_BYTES:
            continue
        matches.append(
            {
                "page_index_zero_based": page_index,
                "matched_text_sha256": _sha256(raw),
                "matched_text_utf8_bytes": len(raw),
            }
        )
    return {
        "claim_id": claim_id,
        "scope": scope,
        "anchor_regex_sha256": _sha256(anchor_regex.encode("utf-8")),
        "matched": bool(matches),
        "match_count": len(matches),
        "matches": matches,
        "source_text_persisted": False,
    }


def _claim_diagnostics(claim_ids: Sequence[str], pages: Sequence[str]) -> str:
    """Return boolean probe hits only; never return or persist source text."""
    lowered_pages = [page.casefold() for page in pages]
    diagnostics: dict[str, dict[str, bool]] = {}
    for claim_id in claim_ids:
        probes = _DIAGNOSTIC_PROBES.get(claim_id, ())
        diagnostics[claim_id] = {
            probe: any(probe.casefold() in page for page in lowered_pages)
            for probe in probes
        }
    return json.dumps(diagnostics, sort_keys=True, separators=(",", ":"))


def acquire_naderi_reference_chain_evidence(
    *,
    qualification: Mapping[str, Any],
    fetcher: Fetcher = fetch_exact_source,
) -> dict[str, Any]:
    """Acquire one exact NIST-hosted paper and emit claim receipts only."""
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
        _claim_receipt(claim_id, anchor, scope, pages)
        for claim_id, anchor, scope in CLAIMS
    ]
    failed_claim_ids = [item["claim_id"] for item in claims if not item["matched"]]
    if failed_claim_ids:
        diagnostics = _claim_diagnostics(failed_claim_ids, pages)
        raise NistMds22923ReferenceChainEvidenceError(
            "required Naderi reference-chain claim did not match: "
            + ", ".join(failed_claim_ids)
            + "; bounded_probe_hits="
            + diagnostics
        )

    report: dict[str, Any] = {
        "schema_version": "1.0",
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
