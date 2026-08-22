"""Verify the observed quality contract of the exact IN625 tensile workbook.

The contract binds the deterministic output of the row-preserving v2 intake to the exact
source archive/workbook bytes.  It records one observed source missingness event without
turning that observation into an imputation, row-exclusion rule, scientific confidence score,
or physical-comparability claim.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError

QUALITY_CONTRACT_SCHEMA_VERSION = "1.0"
EXPECTED_INTAKE_SCHEMA_VERSION = "2.0"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_ARCHIVE_SHA256 = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
EXPECTED_WORKBOOK_SHA256 = "c889e4e6cd1b86d6efb603f53ce9eda64137f6898b3e6f2b490c70a0db73140c"
_EXPECTED_FIELDS = {
    "time_s",
    "extension_mm",
    "strain_percent",
    "load_n",
    "tensile_stress_mpa",
    "tensile_extension_mm",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class In625TensileQualityContractError(ResearchLoopError):
    """Raised when live reviewed rows differ from the bound observed-quality contract."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise In625TensileQualityContractError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625TensileQualityContractError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise In625TensileQualityContractError(f"{field} must be a sequence")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise In625TensileQualityContractError(
            f"{field} must be a nonnegative integer"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result == 0:
        raise In625TensileQualityContractError(f"{field} must be positive")
    return result


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise In625TensileQualityContractError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _canonical_sha(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise In625TensileQualityContractError(
            "quality evidence must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _load_contract(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = path.expanduser().resolve(strict=True)
    raw = resolved.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625TensileQualityContractError(
            "quality contract must be valid duplicate-free UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise In625TensileQualityContractError("quality contract root must be an object")
    return value, {
        "path": str(resolved),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _verified_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(_mapping(value, "reviewed_tensile_manifest"))
    embedded = _sha(
        manifest.pop("manifest_sha256", None),
        "reviewed_tensile_manifest.manifest_sha256",
    )
    if _canonical_sha(manifest) != embedded:
        raise In625TensileQualityContractError(
            "reviewed tensile manifest canonical SHA-256 does not match its content"
        )
    manifest["manifest_sha256"] = embedded
    return manifest


def _count_triplet(value: object, field: str) -> dict[str, int]:
    counts = _mapping(value, field)
    if set(counts) != {"numeric", "blank", "non_numeric"}:
        raise In625TensileQualityContractError(
            f"{field} must contain exactly numeric/blank/non_numeric"
        )
    return {
        key: _nonnegative_int(counts.get(key), f"{field}.{key}")
        for key in ("numeric", "blank", "non_numeric")
    }


def _sheet_quality_from_manifest(manifest: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    sheets = _sequence(manifest.get("sheets"), "reviewed_tensile_manifest.sheets")
    result: dict[str, dict[str, int]] = {}
    for index, raw in enumerate(sheets):
        item = _mapping(raw, f"reviewed_tensile_manifest.sheets[{index}]")
        name = item.get("sheet_name")
        if not isinstance(name, str) or not name or name in result:
            raise In625TensileQualityContractError(
                "reviewed tensile manifest contains invalid/duplicate sheet identity"
            )
        result[name] = {
            "parallel_test_block_count": _positive_int(
                item.get("parallel_test_block_count"),
                f"sheet {name} parallel_test_block_count",
            ),
            "measurement_row_count": _positive_int(
                item.get("measurement_row_count"),
                f"sheet {name} measurement_row_count",
            ),
            "complete_numeric_row_count": _nonnegative_int(
                item.get("complete_numeric_row_count"),
                f"sheet {name} complete_numeric_row_count",
            ),
            "incomplete_numeric_row_count": _nonnegative_int(
                item.get("incomplete_numeric_row_count"),
                f"sheet {name} incomplete_numeric_row_count",
            ),
        }
        if (
            result[name]["complete_numeric_row_count"]
            + result[name]["incomplete_numeric_row_count"]
            != result[name]["measurement_row_count"]
        ):
            raise In625TensileQualityContractError(
                f"sheet {name} complete/incomplete counts do not sum to row count"
            )
    return result


def verify_in625_tensile_observed_quality(
    *,
    reviewed_tensile_manifest: Mapping[str, Any],
    quality_contract_path: str | Path,
) -> dict[str, Any]:
    """Verify exact v2 row-quality observations against the repository contract."""
    manifest = _verified_manifest(reviewed_tensile_manifest)
    contract, contract_record = _load_contract(Path(quality_contract_path))

    if contract.get("schema_version") != QUALITY_CONTRACT_SCHEMA_VERSION:
        raise In625TensileQualityContractError("unsupported quality contract schema_version")
    if (
        contract.get("source_id") != EXPECTED_SOURCE_ID
        or contract.get("source_archive_sha256") != EXPECTED_ARCHIVE_SHA256
        or contract.get("workbook_sha256") != EXPECTED_WORKBOOK_SHA256
        or contract.get("reviewed_intake_schema_version")
        != EXPECTED_INTAKE_SCHEMA_VERSION
    ):
        raise In625TensileQualityContractError(
            "quality contract source/workbook/intake identity drifted"
        )
    if (
        manifest.get("schema_version") != EXPECTED_INTAKE_SCHEMA_VERSION
        or manifest.get("source_id") != EXPECTED_SOURCE_ID
        or manifest.get("source_archive_sha256") != EXPECTED_ARCHIVE_SHA256
    ):
        raise In625TensileQualityContractError(
            "reviewed tensile manifest source/intake identity drifted"
        )
    workbook = _mapping(manifest.get("workbook"), "reviewed_tensile_manifest.workbook")
    if workbook.get("sha256") != EXPECTED_WORKBOOK_SHA256:
        raise In625TensileQualityContractError(
            "reviewed tensile manifest workbook SHA-256 drifted"
        )

    row_count = _positive_int(manifest.get("measurement_row_count"), "measurement_row_count")
    complete = _nonnegative_int(
        manifest.get("complete_numeric_measurement_row_count"),
        "complete_numeric_measurement_row_count",
    )
    incomplete = _nonnegative_int(
        manifest.get("incomplete_numeric_measurement_row_count"),
        "incomplete_numeric_measurement_row_count",
    )
    if complete + incomplete != row_count:
        raise In625TensileQualityContractError(
            "complete/incomplete reviewed row counts do not sum to measurement_row_count"
        )
    for field, observed, expected_key in (
        ("measurement_row_count", row_count, "measurement_row_count"),
        (
            "complete_numeric_measurement_row_count",
            complete,
            "complete_numeric_measurement_row_count",
        ),
        (
            "incomplete_numeric_measurement_row_count",
            incomplete,
            "incomplete_numeric_measurement_row_count",
        ),
    ):
        expected = _nonnegative_int(contract.get(expected_key), f"contract.{expected_key}")
        if observed != expected:
            raise In625TensileQualityContractError(
                f"{field} differs from the exact observed-quality contract"
            )

    observed_fields = _mapping(
        manifest.get("reviewed_numeric_field_quality_counts"),
        "reviewed_tensile_manifest.reviewed_numeric_field_quality_counts",
    )
    expected_fields = _mapping(
        contract.get("reviewed_numeric_field_quality_counts"),
        "quality_contract.reviewed_numeric_field_quality_counts",
    )
    if set(observed_fields) != _EXPECTED_FIELDS or set(expected_fields) != _EXPECTED_FIELDS:
        raise In625TensileQualityContractError(
            "reviewed numeric field set differs from the six-field contract"
        )
    normalized_fields: dict[str, dict[str, int]] = {}
    for field in sorted(_EXPECTED_FIELDS):
        observed_counts = _count_triplet(
            observed_fields[field],
            f"manifest field quality {field}",
        )
        expected_counts = _count_triplet(
            expected_fields[field],
            f"contract field quality {field}",
        )
        if sum(observed_counts.values()) != row_count:
            raise In625TensileQualityContractError(
                f"manifest field quality counts do not sum to row_count for {field}"
            )
        if observed_counts != expected_counts:
            raise In625TensileQualityContractError(
                f"reviewed field quality drifted from contract for {field}"
            )
        normalized_fields[field] = observed_counts

    observed_sheet_quality = _sheet_quality_from_manifest(manifest)
    contract_sheet_raw = _mapping(contract.get("sheet_quality"), "quality_contract.sheet_quality")
    expected_sheet_quality: dict[str, dict[str, int]] = {}
    for name, raw in contract_sheet_raw.items():
        if not isinstance(name, str) or not name:
            raise In625TensileQualityContractError("quality contract has invalid sheet name")
        item = _mapping(raw, f"quality_contract.sheet_quality.{name}")
        expected_sheet_quality[name] = {
            "parallel_test_block_count": _positive_int(
                item.get("parallel_test_block_count"),
                f"contract sheet {name} blocks",
            ),
            "measurement_row_count": _positive_int(
                item.get("measurement_row_count"),
                f"contract sheet {name} rows",
            ),
            "complete_numeric_row_count": _nonnegative_int(
                item.get("complete_numeric_row_count"),
                f"contract sheet {name} complete rows",
            ),
            "incomplete_numeric_row_count": _nonnegative_int(
                item.get("incomplete_numeric_row_count"),
                f"contract sheet {name} incomplete rows",
            ),
        }
    if observed_sheet_quality != expected_sheet_quality:
        raise In625TensileQualityContractError(
            "per-sheet reviewed quality differs from the exact observed contract"
        )

    observed_examples = list(
        _sequence(
            manifest.get("bounded_incomplete_row_examples"),
            "reviewed_tensile_manifest.bounded_incomplete_row_examples",
        )
    )
    expected_examples = list(
        _sequence(contract.get("known_incomplete_rows"), "quality_contract.known_incomplete_rows")
    )
    if incomplete > len(observed_examples):
        raise In625TensileQualityContractError(
            "bounded anomaly examples are insufficient to bind all incomplete rows"
        )
    if observed_examples != expected_examples:
        raise In625TensileQualityContractError(
            "incomplete-row identity differs from the exact observed-quality contract"
        )

    semantics = _mapping(manifest.get("reviewed_semantics"), "reviewed_tensile_manifest.reviewed_semantics")
    if (
        semantics.get("missing_values_imputed") is not False
        or semantics.get("non_numeric_values_coerced") is not False
        or semantics.get("parallel_test_independence_established") is not False
    ):
        raise In625TensileQualityContractError(
            "reviewed tensile intake altered missingness or over-claimed independence"
        )
    evidence_quality = _mapping(manifest.get("evidence_quality"), "reviewed_tensile_manifest.evidence_quality")
    if (
        evidence_quality.get("incomplete_rows_retained_as_evidence") is not True
        or evidence_quality.get("numeric_completeness_fraction_is_scientific_confidence")
        is not False
        or evidence_quality.get("missingness_mechanism_established") is not False
    ):
        raise In625TensileQualityContractError(
            "reviewed tensile evidence-quality semantics drifted"
        )
    interpretation = _mapping(contract.get("interpretation"), "quality_contract.interpretation")
    for key in (
        "missing_value_imputation_authorized",
        "inverse_reconstruction_from_tensile_stress_authorized",
        "row_exclusion_authorized",
        "statistical_independence_established",
        "direct_nist_condition_comparability_established",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "positive_scientific_closeout_established",
    ):
        if interpretation.get(key) is not False:
            raise In625TensileQualityContractError(
                f"quality contract interpretation improperly widens authority: {key}"
            )

    verification: dict[str, Any] = {
        "schema_version": "1.0",
        "quality_status": "verified_observed_source_quality",
        "source_id": EXPECTED_SOURCE_ID,
        "source_archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "workbook_sha256": EXPECTED_WORKBOOK_SHA256,
        "reviewed_tensile_manifest_sha256": manifest["manifest_sha256"],
        "quality_contract": contract_record,
        "measurement_row_count": row_count,
        "complete_numeric_measurement_row_count": complete,
        "incomplete_numeric_measurement_row_count": incomplete,
        "reviewed_numeric_field_quality_counts": normalized_fields,
        "sheet_quality": observed_sheet_quality,
        "known_incomplete_rows": observed_examples,
        "isolated_source_missingness_observed": incomplete == 1,
        "missingness_mechanism_established": False,
        "missing_value_imputation_authorized": False,
        "row_exclusion_authorized": False,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_established": False,
        "scientific_status_changed": False,
    }
    verification["verification_sha256"] = _canonical_sha(verification)
    return verification


__all__ = [
    "In625TensileQualityContractError",
    "verify_in625_tensile_observed_quality",
]
