"""Cross-artifact semantic hardening for autonomous-production live verification.

Self-consistent re-hashing is not sufficient scientific authentication. This module verifies
that predecessor artifacts continue to encode the exact fail-closed authority state and that
their scientific/data-quality claims agree across artifact boundaries on every accepted live
outcome, not only on temporary transport stops.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TRANSPORT_STOP_REASON_CODE = "source_transport_temporarily_unavailable"

_EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
_EXPECTED_ARCHIVE_SHA256 = (
    "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
)
_EXPECTED_WORKBOOK_SHA256 = (
    "c889e4e6cd1b86d6efb603f53ce9eda64137f6898b3e6f2b490c70a0db73140c"
)
_EXPECTED_QUALITY_CONTRACT_NAME = "in625_tensile_observed_quality.v1.json"
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
_QUALITY_INTERPRETATION_FALSE_FIELDS = (
    "missing_value_imputation_authorized",
    "inverse_reconstruction_from_tensile_stress_authorized",
    "row_exclusion_authorized",
    "statistical_independence_established",
    "direct_nist_condition_comparability_established",
    "empirical_model_validation_established",
    "hypothesis_truth_established",
    "positive_scientific_closeout_established",
)


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


def _load_bound_quality_contract(
    *, root: Path, quality: Mapping[str, Any]
) -> dict[str, Any]:
    record = _mapping(quality.get("quality_contract"), "tensile quality quality_contract")
    _require(
        set(record) == {"path", "sha256", "bytes"},
        "tensile quality contract binding field set drifted",
    )
    raw_path = record.get("path")
    digest = record.get("sha256")
    byte_count = record.get("bytes")
    _require(
        isinstance(raw_path, str) and raw_path,
        "tensile quality contract binding path is invalid",
    )
    _require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        "tensile quality contract binding SHA is invalid",
    )
    _require(
        isinstance(byte_count, int)
        and not isinstance(byte_count, bool)
        and byte_count > 0,
        "tensile quality contract binding byte count is invalid",
    )
    try:
        contract_path = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise AutonomousProductionSemanticHardeningError(
            "tensile quality contract binding path does not resolve"
        ) from exc
    _require(contract_path.is_file(), "tensile quality contract binding is not a file")
    _require(
        contract_path.name == _EXPECTED_QUALITY_CONTRACT_NAME
        and contract_path.parent.name == "research"
        and contract_path.parent.parent.name == "configs",
        "tensile quality contract binding escaped the exact repository contract location",
    )
    _require(
        any(parent == contract_path.parent.parent.parent for parent in root.parents),
        "tensile quality contract binding is outside the autonomous run repository",
    )
    raw = contract_path.read_bytes()
    _require(len(raw) == byte_count, "tensile quality contract byte count mismatch")
    _require(
        hashlib.sha256(raw).hexdigest() == digest,
        "tensile quality contract SHA-256 mismatch",
    )
    try:
        contract = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionSemanticHardeningError(
            "tensile quality contract must be valid UTF-8 JSON"
        ) from exc
    _require(isinstance(contract, dict), "tensile quality contract root must be an object")
    _require(
        contract.get("schema_version") == "1.0"
        and contract.get("source_id") == _EXPECTED_SOURCE_ID
        and contract.get("source_archive_sha256") == _EXPECTED_ARCHIVE_SHA256
        and contract.get("workbook_sha256") == _EXPECTED_WORKBOOK_SHA256
        and contract.get("reviewed_intake_schema_version") == "2.0"
        and contract.get("measurement_row_count") == 200289
        and contract.get("complete_numeric_measurement_row_count") == 200288
        and contract.get("incomplete_numeric_measurement_row_count") == 1
        and contract.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS,
        "tensile quality contract observed-evidence identity drifted",
    )
    interpretation = _mapping(
        contract.get("interpretation"), "tensile quality contract interpretation"
    )
    for key in _QUALITY_INTERPRETATION_FALSE_FIELDS:
        _require(
            interpretation.get(key) is False,
            f"tensile quality contract improperly authorizes scientific/data alteration: {key}",
        )
    return contract


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


def _verify_pretransport_science(
    root: Path, *, manifest: Mapping[str, Any]
) -> None:
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
        manifest.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS
        and manifest.get("known_incomplete_rows") == quality.get("known_incomplete_rows"),
        "autonomous manifest incomplete-row identity disagrees with verified quality evidence",
    )
    _load_bound_quality_contract(root=root, quality=quality)
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
        "quality evidence scientific state drifted: tensile quality authority",
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
    """Reject self-consistent artifacts that widen persisted scientific authority."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load(root, "autonomous-production-manifest.json")
    bounded_stop = _load(root, "bounded-stop.json")

    _require(
        manifest.get("paper_evidence_promoted_to_row_level_authority") is False,
        "autonomous manifest must explicitly deny paper evidence row-level authority",
    )
    stop = _mapping(manifest.get("stop"), "autonomous production manifest stop")
    _require(
        dict(stop) == bounded_stop,
        "bounded-stop artifact does not match autonomous manifest stop",
    )

    # These predecessor scientific boundaries exist before the NIST delivery result and must be
    # re-authenticated for both accepted outcomes: full success and typed transport unavailability.
    _verify_qualification(root)
    _verify_pretransport_science(root, manifest=manifest)


__all__ = [
    "AutonomousProductionSemanticHardeningError",
    "TRANSPORT_STOP_REASON_CODE",
    "verify_persisted_semantic_boundaries",
]
