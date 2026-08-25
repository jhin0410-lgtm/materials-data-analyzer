"""Cross-artifact semantic hardening for autonomous-production live verification.

Self-consistent re-hashing is not sufficient scientific authentication.  This module verifies
that the preserved predecessor artifacts continue to encode the exact fail-closed authority
state and that their scientific/data-quality claims agree across artifact boundaries.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TRANSPORT_STOP_REASON_CODE = "source_transport_temporarily_unavailable"

_EXPECTED_INCOMPLETE_ROWS = [
    {
        "sheet_name": "AM-AB-H",
        "block_index": 1,
        "excel_row_number": 79,
        "missing_reviewed_numeric_fields": ["load_n"],
        "non_numeric_reviewed_fields": [],
        "raw_anomalous_cell_text": {"load_n": ""},
    }
]


class AutonomousProductionSemanticHardeningError(ValueError):
    """Raised when authenticated artifacts disagree about scientific authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionSemanticHardeningError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionSemanticHardeningError(
            f"{name} must be valid persisted UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{name} root must be an object")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field} must be an object")
    return value


def _verify_self_hash(value: Mapping[str, Any], field: str, *, label: str) -> str:
    digest = value.get(field)
    _require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        f"{label} {field} is missing or non-canonical",
    )
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{label} self-hash mismatch")
    return digest


def _verify_qualification(root: Path) -> None:
    qualification = _load(root, "nist-network-policy-qualification.json")
    _verify_self_hash(
        qualification,
        "qualification_sha256",
        label="NIST network policy qualification",
    )
    _require(
        qualification.get("issue_76_automatic_promotion_authorized") is False,
        "NIST qualification authorized Issue #76 automatic promotion",
    )
    _require(
        qualification.get("paper_and_other_source_lanes_remain_allowed") is True,
        "NIST qualification closed independent paper/other-source evidence lanes",
    )
    _require(
        qualification.get("network_access_performed") is False
        and qualification.get("unrestricted_search_authorized") is False
        and qualification.get("arbitrary_url_fetch_authorized") is False
        and qualification.get("scientific_status_changed") is False,
        "NIST qualification widened network or scientific authority",
    )


def _verify_pretransport_science(root: Path) -> None:
    quality = _load(root, "tensile-quality-verification.json")
    rediagnosis = _load(root, "quality-aware-rediagnosis.json")
    assessment = _load(root, "physical-comparability-assessment.json")

    quality_sha = _verify_self_hash(
        quality,
        "verification_sha256",
        label="tensile quality verification",
    )
    rediagnosis_sha = _verify_self_hash(
        rediagnosis,
        "rediagnosis_sha256",
        label="quality-aware rediagnosis",
    )
    _verify_self_hash(
        assessment,
        "assessment_sha256",
        label="physical comparability assessment",
    )

    _require(
        quality.get("measurement_row_count") == 200289
        and quality.get("complete_numeric_measurement_row_count") == 200288
        and quality.get("incomplete_numeric_measurement_row_count") == 1,
        "tensile quality row-count identity drifted",
    )
    _require(
        quality.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS,
        "tensile quality incomplete-row identity drifted",
    )
    _require(
        quality.get("isolated_source_missingness_observed") is True
        and quality.get("missingness_mechanism_established") is False
        and quality.get("missing_value_imputation_authorized") is False
        and quality.get("row_exclusion_authorized") is False
        and quality.get("direct_nist_condition_comparability_established") is False
        and quality.get("empirical_model_validation_established") is False
        and quality.get("hypothesis_truth_established") is False
        and quality.get("positive_scientific_closeout_established") is False
        and quality.get("scientific_status_changed") is False,
        "tensile quality scientific authority drifted",
    )

    _require(
        rediagnosis.get("observed_quality_verification_sha256") == quality_sha,
        "rediagnosis/quality digest binding mismatch",
    )
    _require(
        rediagnosis.get("observed_quality_verification") == quality,
        "rediagnosis embedded quality evidence disagrees with persisted verification",
    )
    evidence_state = _mapping(
        rediagnosis.get("evidence_state"),
        "quality-aware rediagnosis evidence_state",
    )
    _require(
        evidence_state.get("real_external_source_acquired") is True
        and evidence_state.get("real_row_level_measurements_observed") is True
        and evidence_state.get("observed_source_quality_contract_verified") is True
        and evidence_state.get("complete_numeric_measurement_row_count") == 200288
        and evidence_state.get("incomplete_numeric_measurement_row_count") == 1
        and evidence_state.get("isolated_source_missingness_observed") is True,
        "rediagnosis evidence_state lost verified observed evidence",
    )
    for key in (
        "replicate_independence_established",
        "direct_nist_condition_comparability_established",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "missingness_mechanism_established",
        "missing_value_imputation_authorized",
    ):
        _require(
            evidence_state.get(key) is False,
            f"rediagnosis evidence_state improperly promoted scientific authority: {key}",
        )

    next_action = _mapping(
        rediagnosis.get("next_action"),
        "quality-aware rediagnosis next_action",
    )
    rediagnosis_quality = _mapping(
        next_action.get("source_quality_constraint"),
        "quality-aware rediagnosis next_action.source_quality_constraint",
    )
    _require(
        rediagnosis_quality.get("quality_contract_verified") is True
        and rediagnosis_quality.get("affected_field") == "load_n"
        and rediagnosis_quality.get("affected_row_count") == 1
        and rediagnosis_quality.get("missing_value_imputation_authorized") is False
        and rediagnosis_quality.get("inverse_reconstruction_authorized") is False
        and rediagnosis_quality.get("row_exclusion_authorized") is False,
        "rediagnosis source-quality constraint drifted",
    )

    _require(
        assessment.get("predecessor_rediagnosis_sha256") == rediagnosis_sha,
        "comparability/rediagnosis digest binding mismatch",
    )
    _require(
        assessment.get("observed_quality_verification_sha256") == quality_sha,
        "comparability/quality digest binding mismatch",
    )
    source_quality = _mapping(
        assessment.get("source_quality_constraint"),
        "physical comparability source_quality_constraint",
    )
    _require(
        source_quality.get("known_incomplete_row_count") == 1
        and source_quality.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS
        and source_quality.get("known_incomplete_rows") == quality.get("known_incomplete_rows")
        and source_quality.get("missing_value_imputation_authorized") is False
        and source_quality.get("inverse_reconstruction_authorized") is False
        and source_quality.get("row_exclusion_authorized") is False
        and source_quality.get("missingness_mechanism_established") is False,
        "physical comparability source-quality constraint drifted",
    )


def verify_persisted_semantic_boundaries(output_root: str | Path) -> None:
    """Reject self-consistent artifacts that widen the persisted scientific authority."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load(root, "autonomous-production-manifest.json")

    _require(
        manifest.get("paper_evidence_promoted_to_row_level_authority") is False,
        "autonomous manifest must explicitly deny paper evidence row-level authority",
    )

    stop = _mapping(manifest.get("stop"), "autonomous production manifest stop")
    if stop.get("reason_code") != TRANSPORT_STOP_REASON_CODE:
        return

    _verify_qualification(root)
    _verify_pretransport_science(root)


__all__ = [
    "AutonomousProductionSemanticHardeningError",
    "TRANSPORT_STOP_REASON_CODE",
    "verify_persisted_semantic_boundaries",
]
