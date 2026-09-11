"""Acquire Weaver 2021 full text only from authenticated reference-graph authority."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from .in625_geometry_condition_source_acquisition import FetchResult, fetch_exact_source
from .weaver_2021_full_text_policy import (
    ACTION_CLASS,
    ALLOWED_HOSTS,
    AUTHORITY_EXTENSION_ID,
    AUTHORITY_EXTENSION_SHA256,
    BASE_MISSION_SHA256,
    CLAIMS,
    MAX_REQUESTS,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_BYTES,
    POLICY_ID,
    POLICY_SHA256,
    SOURCE_DOI,
    SOURCE_ID,
    SOURCE_PMCID,
    SOURCE_PMID,
    SOURCE_TITLE,
    SOURCE_URL,
    TIMEOUT_SECONDS,
)

NEXT_ACTION_CLASS = "mds2_2923_weaver_row_identity_binding_assessment"
MAX_CLAIM_SPAN_CHARS = 16_384
IMPLEMENTATION_ID = "weaver-2021-pmc-bioc-derived-full-text-acquisition-v1"
FACTORY_ID = "bounded-derived-primary-full-text-acquisition-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
    "provenance_bound_calibration_intake",
)


class Weaver2021FullTextAcquisitionError(ValueError):
    """Raised when Weaver acquisition leaves authenticated provenance authority."""


Fetcher = Callable[..., FetchResult]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Weaver2021FullTextAcquisitionError(message)


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


def _validate_self_hash(value: Mapping[str, Any], field: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _validate_manifest(value: Mapping[str, Any]) -> str:
    return _validate_self_hash(value, "manifest_sha256")


def _validate_exact_url(url: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise Weaver2021FullTextAcquisitionError("Weaver source URL has invalid port") from exc
    expected = urlparse(SOURCE_URL)
    _require(
        parsed.scheme == "https"
        and parsed.hostname == "www.ncbi.nlm.nih.gov"
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and parsed.path == expected.path
        and parsed.query == ""
        and parsed.fragment == "",
        "Weaver source URL left exact NCBI BioC authority",
    )


def _all_strings(value: object) -> list[str]:
    result: list[str] = []
    if isinstance(value, str):
        result.append(value)
    elif isinstance(value, Mapping):
        for key in sorted(value, key=str):
            result.extend(_all_strings(str(key)))
            result.extend(_all_strings(value[key]))
    elif isinstance(value, list):
        for item in value:
            result.extend(_all_strings(item))
    return result


def _normalize(value: str) -> str:
    value = value.replace("μ", "u").replace("µ", "u").replace("σ", "sigma")
    return re.sub(r"\s+", " ", value).strip()


def _bioc_text(body: bytes) -> tuple[object, str]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Weaver2021FullTextAcquisitionError("Weaver BioC response must be UTF-8 JSON") from exc
    _require(isinstance(value, (dict, list)), "Weaver BioC response root must be object or list")
    text = _normalize(" ".join(_all_strings(value)))
    _require(bool(text), "Weaver BioC response contains no textual content")
    return value, text


def _identity_receipt(text: str) -> dict[str, Any]:
    folded = text.casefold()
    title_ok = SOURCE_TITLE.casefold() in folded
    doi_ok = SOURCE_DOI.casefold() in folded
    pmcid_ok = SOURCE_PMCID.casefold() in folded
    pmid_ok = SOURCE_PMID.casefold() in folded
    authors_ok = all(token in folded for token in ("weaver", "heigel", "lane"))
    _require(title_ok, "Weaver BioC response title identity was not found")
    _require(doi_ok, "Weaver BioC response DOI identity was not found")
    _require(pmcid_ok or pmid_ok, "Weaver BioC response PMC/PubMed identity was not found")
    _require(authors_ok, "Weaver BioC response author identity was not found")
    receipt = {
        "title_matched": title_ok,
        "doi_matched": doi_ok,
        "pmcid_matched": pmcid_ok,
        "pmid_matched": pmid_ok,
        "authors_matched": authors_ok,
        "article_identity_established": True,
    }
    receipt["identity_sha256"] = _canonical_sha(receipt)
    return receipt


def _ordered_claim_receipt(
    *,
    claim_id: str,
    fragments: Sequence[str],
    scope: str,
    text: str,
) -> dict[str, Any]:
    folded = text.casefold()
    normalized = [_normalize(item).casefold() for item in fragments]
    start = 0
    positions: list[int] = []
    for fragment in normalized:
        index = folded.find(fragment, start)
        if index < 0:
            positions = []
            break
        positions.append(index)
        start = index + len(fragment)
    span_chars = 0
    matched = bool(positions)
    if matched:
        span_chars = start - positions[0]
        matched = span_chars <= MAX_CLAIM_SPAN_CHARS
    excerpt_sha = None
    if matched:
        excerpt = folded[positions[0]:start].encode("utf-8")
        excerpt_sha = _sha256(excerpt)
    return {
        "claim_id": claim_id,
        "match_mode": "ordered_normalized_fragments",
        "required_fragments": list(fragments),
        "required_fragments_sha256": _canonical_sha(list(fragments)),
        "scope": scope,
        "matched": matched,
        "matched_span_chars": span_chars if matched else None,
        "matched_span_sha256": excerpt_sha,
    }


def build_derived_weaver_authorization(
    *,
    qualification: Mapping[str, Any],
    reference_graph: Mapping[str, Any],
    predecessor_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one exact Weaver DOI locator to the separately authenticated PMC source policy."""
    _require(
        qualification.get("qualification_status")
        == "exact_weaver_2021_full_text_policy_authenticated",
        "Weaver full-text policy is not authenticated",
    )
    _require(
        qualification.get("policy_id") == POLICY_ID
        and qualification.get("policy_sha256") == POLICY_SHA256
        and qualification.get("authority_extension_id") == AUTHORITY_EXTENSION_ID
        and qualification.get("authority_extension_sha256") == AUTHORITY_EXTENSION_SHA256
        and qualification.get("mission_sha256") == BASE_MISSION_SHA256
        and qualification.get("action_class") == ACTION_CLASS,
        "Weaver qualification authority chain drifted",
    )
    graph_sha = _validate_self_hash(reference_graph, "report_sha256_without_self_field")
    manifest_sha = _validate_manifest(predecessor_manifest)
    _require(
        predecessor_manifest.get("reference_chain_assessment_sha256") == graph_sha
        and predecessor_manifest.get("generated_next_action_class") == ACTION_CLASS
        and predecessor_manifest.get("fifth_capability_gap_emitted") is True,
        "predecessor manifest did not reach exact Weaver frontier",
    )
    next_action = reference_graph.get("next_action")
    _require(isinstance(next_action, Mapping), "reference graph Weaver next action is missing")
    candidate = next_action.get("candidate")
    _require(isinstance(candidate, Mapping), "reference graph Weaver candidate is missing")
    _require(
        next_action.get("action_class") == ACTION_CLASS
        and next_action.get("automatic_acquisition_authorized") is False
        and next_action.get("caller_authored_url_authorized") is False
        and candidate.get("doi") == SOURCE_DOI
        and candidate.get("title") == SOURCE_TITLE
        and candidate.get("acquisition_authorized") is False,
        "reference graph did not preserve Weaver locator-only authority",
    )
    authorization: dict[str, Any] = {
        "schema_version": "1.0",
        "authorization_type": "provenance_derived_weaver_primary_full_text",
        "action_class": ACTION_CLASS,
        "policy_id": POLICY_ID,
        "policy_sha256": POLICY_SHA256,
        "authority_extension_id": AUTHORITY_EXTENSION_ID,
        "authority_extension_sha256": AUTHORITY_EXTENSION_SHA256,
        "mission_sha256": BASE_MISSION_SHA256,
        "reference_graph_sha256": graph_sha,
        "predecessor_manifest_sha256": manifest_sha,
        "source_id": SOURCE_ID,
        "doi": SOURCE_DOI,
        "pmcid": SOURCE_PMCID,
        "pmid": SOURCE_PMID,
        "title": SOURCE_TITLE,
        "source_url": SOURCE_URL,
        "allowed_hosts": list(ALLOWED_HOSTS),
        "max_requests": MAX_REQUESTS,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "doi_derived_from_reference_graph": True,
        "pmcid_derived_from_separately_pinned_policy": True,
        "caller_authored_url_used": False,
        "caller_authored_pmcid_used": False,
        "unrestricted_search_authorized": False,
        "scientific_status_change_authorized": False,
    }
    authorization["authorization_sha256"] = _canonical_sha(authorization)
    return authorization


def execute_derived_weaver_acquisition(
    *,
    authorization: Mapping[str, Any],
    fetcher: Fetcher = fetch_exact_source,
) -> dict[str, Any]:
    """Acquire and identity-check one fixed PMC BioC representation of the Weaver paper."""
    auth_sha = _validate_self_hash(authorization, "authorization_sha256")
    _require(
        authorization.get("policy_id") == POLICY_ID
        and authorization.get("policy_sha256") == POLICY_SHA256
        and authorization.get("authority_extension_id") == AUTHORITY_EXTENSION_ID
        and authorization.get("authority_extension_sha256") == AUTHORITY_EXTENSION_SHA256
        and authorization.get("mission_sha256") == BASE_MISSION_SHA256
        and authorization.get("action_class") == ACTION_CLASS,
        "Weaver authorization authority chain drifted",
    )
    _require(
        authorization.get("doi") == SOURCE_DOI
        and authorization.get("pmcid") == SOURCE_PMCID
        and authorization.get("pmid") == SOURCE_PMID
        and authorization.get("title") == SOURCE_TITLE
        and authorization.get("source_url") == SOURCE_URL,
        "Weaver authorization source identity drifted",
    )
    _require(
        authorization.get("allowed_hosts") == list(ALLOWED_HOSTS)
        and authorization.get("max_requests") == MAX_REQUESTS == 1
        and authorization.get("max_source_bytes") == MAX_SOURCE_BYTES
        and authorization.get("max_total_bytes") == MAX_TOTAL_BYTES
        and authorization.get("timeout_seconds") == TIMEOUT_SECONDS,
        "Weaver authorization network budget drifted",
    )
    _require(
        authorization.get("doi_derived_from_reference_graph") is True
        and authorization.get("pmcid_derived_from_separately_pinned_policy") is True
        and authorization.get("caller_authored_url_used") is False
        and authorization.get("caller_authored_pmcid_used") is False
        and authorization.get("unrestricted_search_authorized") is False
        and authorization.get("scientific_status_change_authorized") is False,
        "Weaver authorization widened forbidden authority",
    )
    _validate_exact_url(SOURCE_URL)
    fetched = fetcher(
        SOURCE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        max_bytes=min(MAX_SOURCE_BYTES, MAX_TOTAL_BYTES),
        timeout_seconds=TIMEOUT_SECONDS,
    )
    _require(isinstance(fetched, FetchResult), "Weaver fetcher must return FetchResult")
    _validate_exact_url(fetched.final_url)
    _require(200 <= fetched.status_code < 300, "Weaver source fetch returned non-success status")
    _require(0 < len(fetched.body) <= MAX_TOTAL_BYTES, "Weaver source bytes exceeded budget")
    _, text = _bioc_text(fetched.body)
    identity = _identity_receipt(text)
    claims = [
        _ordered_claim_receipt(
            claim_id=claim_id,
            fragments=fragments,
            scope=scope,
            text=text,
        )
        for claim_id, fragments, scope in CLAIMS
    ]
    by_id = {item["claim_id"]: item for item in claims}
    _require(len(by_id) == len(CLAIMS), "Weaver claim identities are not unique")
    core_claim_ids = {
        "weaver-primary-condition",
        "weaver-ammt-machine-condition",
        "weaver-d4sigma-definition",
        "weaver-cross-section-protocol",
        "weaver-dataset-size",
    }
    core_claims_matched = all(by_id[item]["matched"] is True for item in core_claim_ids)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": ACTION_CLASS,
        "acquisition_status": "exact_weaver_primary_full_text_acquired_and_identity_verified",
        "authorization_sha256": auth_sha,
        "policy_id": POLICY_ID,
        "policy_sha256": POLICY_SHA256,
        "authority_extension_id": AUTHORITY_EXTENSION_ID,
        "authority_extension_sha256": AUTHORITY_EXTENSION_SHA256,
        "mission_sha256": BASE_MISSION_SHA256,
        "reference_graph_sha256": authorization.get("reference_graph_sha256"),
        "predecessor_manifest_sha256": authorization.get("predecessor_manifest_sha256"),
        "source": {
            "source_id": SOURCE_ID,
            "doi": SOURCE_DOI,
            "pmcid": SOURCE_PMCID,
            "pmid": SOURCE_PMID,
            "title": SOURCE_TITLE,
            "requested_url": SOURCE_URL,
            "final_url": fetched.final_url,
            "source_sha256": _sha256(fetched.body),
            "source_size_bytes": len(fetched.body),
            "http_content_type": fetched.content_type,
            "raw_bytes_persisted": False,
            "full_text_persisted": False,
            "normalized_text_sha256": _sha256(text.encode("utf-8")),
            "normalized_text_utf8_bytes": len(text.encode("utf-8")),
        },
        "article_identity": identity,
        "claim_receipts": claims,
        "core_claims_matched": core_claims_matched,
        "evidence_scope": {
            "weaver_full_text_acquired": True,
            "weaver_article_identity_established": True,
            "primary_condition_established": by_id["weaver-primary-condition"]["matched"],
            "ammt_195w_800_condition_and_spot_range_established": by_id[
                "weaver-ammt-machine-condition"
            ]["matched"],
            "d4sigma_definition_established": by_id["weaver-d4sigma-definition"]["matched"],
            "cross_section_protocol_established": by_id["weaver-cross-section-protocol"]["matched"],
            "dataset_size_statement_established": by_id["weaver-dataset-size"]["matched"],
            "explicit_mds2_2923_identifier_found": by_id["weaver-explicit-mds2-id"]["matched"],
            "explicit_experiment_scoped_power_conversion_found": by_id[
                "weaver-explicit-power-conversion"
            ]["matched"],
        },
        "gate_assessment": {
            "exact_mds2_rows_to_weaver_experiment_established": False,
            "exact_mds2_experiment_identity_established": False,
            "machine_setting_to_calibrated_power_relation_established": False,
            "spot_size_transfer_authorized": False,
            "protocol_equivalence_established": False,
            "uncertainty_transfer_authorized": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "cross_machine_pooling_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
        "network_requests_performed": 1,
        "caller_authored_url_used": False,
        "caller_authored_pmcid_used": False,
        "unrestricted_search_performed": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "acquisition_success_establishes_scientific_bridge": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
        "positive_scientific_closeout": False,
        "global_evidence_unavailability_claimed": False,
        "next_action": {
            "action_class": NEXT_ACTION_CLASS,
            "objective": (
                "Compare exact mds2-2923 AMMT rows and physical-track identities against Weaver "
                "full-text experiment counts, AMMT spot-size conditions and measurement protocol, "
                "while keeping calibration-state transfer independently gated."
            ),
            "automatic_execution_authorized": False,
            "network_access_required": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "NEXT_ACTION_CLASS",
    "REQUIRED_VERIFIED_PRIMITIVES",
    "Weaver2021FullTextAcquisitionError",
    "build_derived_weaver_authorization",
    "execute_derived_weaver_acquisition",
]
