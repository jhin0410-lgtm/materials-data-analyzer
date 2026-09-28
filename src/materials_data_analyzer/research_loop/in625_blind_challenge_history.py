"""Typed, finite NIST evidence search for AMB2018-02 blind-challenge history.

This action is intentionally narrower than a general web search. It may only fetch four
predeclared NIST HTTPS pages after an externally pinned request has been explicitly
authorized. The result establishes historical aggregate context, not individual submission
predictions and not model-specific blind validation.
"""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .evidence_packet import canonical_sha256
from .in625_geometry_condition_source_acquisition import fetch_exact_source

SCHEMA_VERSION = "1.0"
ACTION_TYPE = "in625_amb2018_blind_challenge_history_acquisition"
ACTION_VERSION = "1.0"

ALLOWED_HOSTS = ("www.nist.gov",)
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 180.0

_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "source_id": "nist-amb2018-submissions-awards",
        "url": "https://www.nist.gov/ambench/am-bench-2018-challenge-submissions-and-awards",
        "filename": "01_submissions_awards.html",
        "claims": (
            {
                "claim_id": "amb2018-02-mp-submission-count-10",
                "pattern": r"Melt pool geometry.{0,600}CHAL-AMB2018-02-MP.{0,220}10",
            },
        ),
    },
    {
        "source_id": "nist-amb2018-outcomes-publication",
        "url": "https://www.nist.gov/publications/outcomes-and-conclusions-2018-am-bench-measurements-challenge-problems-modeling",
        "filename": "02_outcomes_publication.html",
        "claims": (
            {
                "claim_id": "amb2018-total-blind-modeling-simulations-46",
                "pattern": r"46 blind modeling simulations were submitted",
            },
        ),
    },
    {
        "source_id": "nist-am-bench-higher-trl-retrospective",
        "url": "https://www.nist.gov/ambench/new-am-bench-focus-higher-technology-readiness-level-applications",
        "filename": "03_higher_trl_retrospective.html",
        "claims": (
            {
                "claim_id": "amb2018-mp-ten-groups-did-not-approach-measurements",
                "pattern": (
                    r"none of the 10 research groups.{0,500}"
                    r"width, depth, and length.{0,500}"
                    r"came close to predicting the measured values"
                ),
            },
        ),
    },
    {
        "source_id": "nist-amb2018-challenges-corrections",
        "url": "https://www.nist.gov/ambench/challenges-and-descriptions",
        "filename": "04_challenges_corrections.html",
        "claims": (
            {
                "claim_id": "amb2018-ammt-corrected-power-levels",
                "pattern": (
                    r"true laser power levels for AMMT were.{0,80}"
                    r"A\).{0,80}137\.9 W.{0,80}400 mm/s.{0,160}"
                    r"B\).{0,80}179\.2 W.{0,80}800 mm/s.{0,160}"
                    r"C\).{0,80}179\.2 W.{0,80}1200 mm/s"
                ),
            },
            {
                "claim_id": "amb2018-corrected-spot-sizes",
                "pattern": (
                    r"true laser spot sizes.{0,500}"
                    r"AMMT.{0,220}170.{0,220}"
                    r"CBM.{0,220}100"
                ),
            },
        ),
    },
)


class In625BlindHistoryError(ValueError):
    """Raised when blind-history acquisition would widen its fixed authority."""


class _TextCollector(HTMLParser):
    _IGNORED = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in self._IGNORED:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and data.strip():
            self.parts.append(data)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625BlindHistoryError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value),
        f"{field} must be lowercase SHA-256",
    )
    return str(value)


def _normalized_html(raw: bytes) -> str:
    parser = _TextCollector()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def _anchor(text: str, pattern: str, claim_id: str) -> dict[str, Any]:
    compiled = re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    match = compiled.search(text)
    _require(match is not None, f"required NIST claim anchor missing: {claim_id}")
    matched = match.group(0).encode("utf-8")
    return {
        "claim_id": claim_id,
        "pattern_sha256": hashlib.sha256(pattern.encode("utf-8")).hexdigest(),
        "matched_text_sha256": hashlib.sha256(matched).hexdigest(),
        "matched_utf8_bytes": len(matched),
    }


def _authenticate_inquiry(
    inquiry: Mapping[str, Any],
    *,
    trusted_inquiry_sha256: str,
) -> tuple[dict[str, Any], str]:
    trusted = _sha(trusted_inquiry_sha256, "trusted_inquiry_sha256")
    snapshot = copy.deepcopy(dict(inquiry))
    _require(
        canonical_sha256(snapshot) == trusted,
        "model-discrepancy inquiry does not match external trust-root SHA-256",
    )
    unsigned = copy.deepcopy(snapshot)
    embedded = _sha(unsigned.pop("inquiry_sha256", None), "inquiry.inquiry_sha256")
    _require(canonical_sha256(unsigned) == embedded, "inquiry self-hash mismatch")

    plan = snapshot.get("plan")
    boundary = snapshot.get("authority_boundary")
    _require(isinstance(plan, Mapping), "inquiry plan is missing")
    _require(isinstance(boundary, Mapping), "inquiry authority boundary is missing")
    selected = plan.get("selected_next_action")
    _require(isinstance(selected, Mapping), "inquiry selected action is missing")
    _require(
        selected.get("action_class") == "external_evidence_search"
        and selected.get("automatic_execution_authorized") is False,
        "blind-history action requires one unauthorized external_evidence_search selection",
    )
    required = selected.get("required_evidence")
    _require(isinstance(required, list) and bool(required), "selected search evidence requirement is missing")
    required_text = " ".join(str(item) for item in required).casefold()
    _require(
        (
            ("blind" in required_text and "submission" in required_text)
            or ("correct" in required_text and "chronolog" in required_text)
        ),
        "selected search is not the AMB2018 blind-submission/correction-history blocker",
    )
    _require(
        boundary.get("network_execution_authorized") is False
        and boundary.get("scientific_status_promoted") is False,
        "inquiry authority was already widened",
    )
    return snapshot, embedded


def _fixed_source_contract() -> list[dict[str, Any]]:
    return [
        {
            "source_id": item["source_id"],
            "url": item["url"],
            "filename": item["filename"],
            "claim_ids": [claim["claim_id"] for claim in item["claims"]],
        }
        for item in _SOURCES
    ]


def build_in625_blind_history_request(
    inquiry: Mapping[str, Any],
    *,
    trusted_inquiry_sha256: str,
) -> dict[str, Any]:
    """Compile the planner-selected search into a finite, non-authorized network request."""

    snapshot, inquiry_sha = _authenticate_inquiry(
        inquiry,
        trusted_inquiry_sha256=trusted_inquiry_sha256,
    )
    selected = snapshot["plan"]["selected_next_action"]
    request: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "source_inquiry_sha256": inquiry_sha,
        "selected_planner_action": {
            "action_id": selected.get("action_id"),
            "action_class": selected.get("action_class"),
            "execution_mode": selected.get("execution_mode"),
            "required_evidence": copy.deepcopy(selected.get("required_evidence")),
        },
        "network_contract": {
            "scheme": "https",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "max_requests": len(_SOURCES),
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "timeout_seconds": TIMEOUT_SECONDS,
            "sources": _fixed_source_contract(),
            "unrestricted_search_authorized": False,
            "caller_authored_urls_authorized": False,
        },
        "scientific_boundary": {
            "individual_submission_prediction_values_expected": False,
            "individual_submission_identity_mapping_expected": False,
            "historical_aggregate_context_only": True,
            "scientific_status_promotion_authorized": False,
        },
        "authority_boundary": {
            "network_execution_authorized": False,
            "physical_experiment_authorized": False,
            "arbitrary_url_fetch_authorized": False,
            "scientific_status_promoted": False,
        },
    }
    request["request_sha256"] = canonical_sha256(request)
    return request


def authorize_in625_blind_history_request(
    request: Mapping[str, Any],
    *,
    trusted_request_sha256: str,
) -> dict[str, Any]:
    """Authorize only the externally pinned exact fixed-source request."""

    trusted = _sha(trusted_request_sha256, "trusted_request_sha256")
    snapshot = copy.deepcopy(dict(request))
    _require(
        canonical_sha256(snapshot) == trusted,
        "blind-history request does not match external authorization trust-root SHA-256",
    )
    unsigned = copy.deepcopy(snapshot)
    embedded = _sha(unsigned.pop("request_sha256", None), "request.request_sha256")
    _require(canonical_sha256(unsigned) == embedded, "blind-history request self-hash mismatch")
    network = snapshot.get("network_contract")
    boundary = snapshot.get("authority_boundary")
    _require(isinstance(network, Mapping), "network contract is missing")
    _require(isinstance(boundary, Mapping), "request authority boundary is missing")
    _require(
        network.get("scheme") == "https"
        and network.get("allowed_hosts") == list(ALLOWED_HOSTS)
        and network.get("max_requests") == len(_SOURCES)
        and network.get("max_source_bytes") == MAX_SOURCE_BYTES
        and network.get("max_total_bytes") == MAX_TOTAL_BYTES
        and network.get("sources") == _fixed_source_contract()
        and network.get("unrestricted_search_authorized") is False
        and network.get("caller_authored_urls_authorized") is False,
        "blind-history network contract drifted or widened",
    )
    _require(
        boundary.get("network_execution_authorized") is False
        and boundary.get("arbitrary_url_fetch_authorized") is False
        and boundary.get("scientific_status_promoted") is False,
        "request self-authorized or widened authority",
    )

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "authorization_type": "explicit_exact_fixed_nist_source_authorization",
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": embedded,
        "trusted_request_sha256": trusted,
        "network_execution_authorized": True,
        "allowed_hosts": list(ALLOWED_HOSTS),
        "authorized_request_count": len(_SOURCES),
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "physical_experiment_authorized": False,
        "scientific_status_promotion_authorized": False,
    }
    receipt["authorization_sha256"] = canonical_sha256(receipt)
    return receipt


def _authenticate_execution_inputs(
    request: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    *,
    trusted_authorization_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    request_snapshot = copy.deepcopy(dict(request))
    request_unsigned = copy.deepcopy(request_snapshot)
    request_sha = _sha(request_unsigned.pop("request_sha256", None), "request.request_sha256")
    _require(canonical_sha256(request_unsigned) == request_sha, "request self-hash mismatch")

    trusted_auth = _sha(trusted_authorization_sha256, "trusted_authorization_sha256")
    receipt = copy.deepcopy(dict(authorization_receipt))
    _require(
        canonical_sha256(receipt) == trusted_auth,
        "authorization receipt does not match external trust-root SHA-256",
    )
    auth_unsigned = copy.deepcopy(receipt)
    auth_sha = _sha(
        auth_unsigned.pop("authorization_sha256", None),
        "authorization.authorization_sha256",
    )
    _require(canonical_sha256(auth_unsigned) == auth_sha, "authorization self-hash mismatch")
    _require(
        receipt.get("request_sha256") == request_sha
        and receipt.get("network_execution_authorized") is True
        and receipt.get("allowed_hosts") == list(ALLOWED_HOSTS)
        and receipt.get("authorized_request_count") == len(_SOURCES)
        and receipt.get("unrestricted_search_authorized") is False
        and receipt.get("arbitrary_url_fetch_authorized") is False
        and receipt.get("scientific_status_promotion_authorized") is False,
        "authorization does not bind the exact finite request",
    )
    _require(
        request_snapshot.get("network_contract", {}).get("sources") == _fixed_source_contract(),
        "execution request source contract drifted",
    )
    return request_snapshot, receipt, request_sha, auth_sha


def _report_from_source_bytes(
    source_bytes_by_id: Mapping[str, bytes],
    *,
    request_sha256: str,
    authorization_sha256: str,
    source_root: Path,
) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    total = 0
    for item in _SOURCES:
        source_id = str(item["source_id"])
        raw = source_bytes_by_id.get(source_id)
        _require(isinstance(raw, bytes) and bool(raw), f"source bytes missing: {source_id}")
        _require(len(raw) <= MAX_SOURCE_BYTES, f"source byte budget exceeded: {source_id}")
        total += len(raw)
        _require(total <= MAX_TOTAL_BYTES, "total source byte budget exceeded")
        text = _normalized_html(raw)
        anchors = [
            _anchor(text, str(claim["pattern"]), str(claim["claim_id"]))
            for claim in item["claims"]
        ]
        receipts.append(
            {
                "source_id": source_id,
                "requested_url": item["url"],
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "source_size_bytes": len(raw),
                "retained_filename": str(item["filename"]),
                "claim_anchors": anchors,
                "all_claim_anchors_matched": True,
            }
        )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": request_sha256,
        "authorization_sha256": authorization_sha256,
        "acquisition_status": "exact_nist_blind_challenge_history_acquired",
        "source_count": len(receipts),
        "source_receipts": receipts,
        "verified_historical_context": {
            "amb2018_total_blind_modeling_simulations": 46,
            "amb2018_02_melt_pool_geometry_submission_count": 10,
            "nist_retrospective_statement_none_of_10_mp_groups_came_close_to_measurements": True,
            "current_corrected_ammt_process_conditions": {
                "A": {"actual_power_w": 137.9, "scan_speed_mm_s": 400.0},
                "B": {"actual_power_w": 179.2, "scan_speed_mm_s": 800.0},
                "C": {"actual_power_w": 179.2, "scan_speed_mm_s": 1200.0},
            },
            "current_corrected_spot_d4sigma_um": {
                "AMMT": 170.0,
                "CBM": 100.0,
            },
            "individual_blind_submission_numeric_predictions_acquired": False,
            "individual_submission_to_model_identity_mapping_acquired": False,
        },
        "bounded_interpretation": {
            "historical_blind_challenge_performance_context_acquired": True,
            "retrospective_published_accuracy_equals_original_blind_accuracy_established": False,
            "specific_cause_of_retrospective_improvement_established": False,
            "post_challenge_refinement_established_for_specific_model": False,
            "corrected_input_semantics_explain_improvement_established": False,
            "remaining_high_value_evidence": (
                "original per-submission prediction tables/files with submission timestamps "
                "and model identity or equivalent authoritative archival record"
            ),
        },
        "authority_boundary": {
            "raw_nist_pages_are_empirical_measurements": False,
            "aggregate_history_promoted_to_individual_submission_values": False,
            "causal_model_explanation_established": False,
            "prospective_blind_validation_established": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    report["result_sha256"] = canonical_sha256(report)
    return report


def execute_in625_blind_history_acquisition(
    request: Mapping[str, Any],
    *,
    authorization_receipt: Mapping[str, Any],
    trusted_authorization_sha256: str,
    source_output_dir: str | Path,
) -> dict[str, Any]:
    """Fetch only the four authorized NIST pages and persist exact bytes for replay."""

    _request, _receipt, request_sha, auth_sha = _authenticate_execution_inputs(
        request,
        authorization_receipt,
        trusted_authorization_sha256=trusted_authorization_sha256,
    )
    root = Path(source_output_dir).expanduser().resolve()
    _require(not root.exists(), "source_output_dir must not already exist")
    root.mkdir(parents=True)

    source_bytes: dict[str, bytes] = {}
    for item in _SOURCES:
        fetched = fetch_exact_source(
            str(item["url"]),
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_SOURCE_BYTES,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        raw = bytes(fetched.body)
        source_bytes[str(item["source_id"])] = raw
        (root / str(item["filename"])).write_bytes(raw)

    return _report_from_source_bytes(
        source_bytes,
        request_sha256=request_sha,
        authorization_sha256=auth_sha,
        source_root=root,
    )


def verify_in625_blind_history_acquisition(
    result: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    trusted_authorization_sha256: str,
    source_output_dir: str | Path,
) -> dict[str, Any]:
    """Rebuild the result from retained exact source bytes without network access."""

    _request, _receipt, request_sha, auth_sha = _authenticate_execution_inputs(
        request,
        authorization_receipt,
        trusted_authorization_sha256=trusted_authorization_sha256,
    )
    supplied = copy.deepcopy(dict(result))
    supplied_unsigned = copy.deepcopy(supplied)
    embedded = _sha(supplied_unsigned.pop("result_sha256", None), "result.result_sha256")
    _require(canonical_sha256(supplied_unsigned) == embedded, "blind-history result self-hash mismatch")

    root = Path(source_output_dir).expanduser().resolve(strict=True)
    source_bytes = {
        str(item["source_id"]): (root / str(item["filename"])).read_bytes()
        for item in _SOURCES
    }
    expected = _report_from_source_bytes(
        source_bytes,
        request_sha256=request_sha,
        authorization_sha256=auth_sha,
        source_root=root,
    )
    _require(supplied == expected, "blind-history result differs from retained-byte replay")
    return expected


__all__ = [
    "ACTION_TYPE",
    "ACTION_VERSION",
    "In625BlindHistoryError",
    "SCHEMA_VERSION",
    "authorize_in625_blind_history_request",
    "build_in625_blind_history_request",
    "execute_in625_blind_history_acquisition",
    "verify_in625_blind_history_acquisition",
]
