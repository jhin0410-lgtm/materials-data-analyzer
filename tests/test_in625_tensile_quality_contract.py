from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_tensile_quality_contract import (
    In625TensileQualityContractError,
    verify_in625_tensile_observed_quality,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/research/in625_tensile_observed_quality.v1.json"
ARCHIVE_SHA = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
WORKBOOK_SHA = "c889e4e6cd1b86d6efb603f53ce9eda64137f6898b3e6f2b490c70a0db73140c"
SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _manifest() -> dict[str, object]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    sheets = []
    for name, quality in contract["sheet_quality"].items():
        sheets.append(
            {
                "sheet_name": name,
                "parallel_test_block_count": quality["parallel_test_block_count"],
                "measurement_row_count": quality["measurement_row_count"],
                "complete_numeric_row_count": quality["complete_numeric_row_count"],
                "incomplete_numeric_row_count": quality["incomplete_numeric_row_count"],
            }
        )
    value: dict[str, object] = {
        "schema_version": "2.0",
        "source_id": SOURCE_ID,
        "source_archive_sha256": ARCHIVE_SHA,
        "workbook": {"sha256": WORKBOOK_SHA},
        "measurement_row_count": 200289,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "reviewed_numeric_field_quality_counts": contract[
            "reviewed_numeric_field_quality_counts"
        ],
        "bounded_incomplete_row_examples": contract["known_incomplete_rows"],
        "sheets": sheets,
        "reviewed_semantics": {
            "missing_values_imputed": False,
            "non_numeric_values_coerced": False,
            "parallel_test_independence_established": False,
        },
        "evidence_quality": {
            "incomplete_rows_retained_as_evidence": True,
            "numeric_completeness_fraction_is_scientific_confidence": False,
            "missingness_mechanism_established": False,
        },
    }
    value["manifest_sha256"] = _sha(value)
    return value


def _rehash(value: dict[str, object]) -> None:
    value.pop("manifest_sha256", None)
    value["manifest_sha256"] = _sha(value)


def test_quality_contract_accepts_exact_isolated_missingness() -> None:
    result = verify_in625_tensile_observed_quality(
        reviewed_tensile_manifest=_manifest(),
        quality_contract_path=CONTRACT,
    )
    assert result["quality_status"] == "verified_observed_source_quality"
    assert result["measurement_row_count"] == 200289
    assert result["complete_numeric_measurement_row_count"] == 200288
    assert result["incomplete_numeric_measurement_row_count"] == 1
    assert result["known_incomplete_rows"][0]["sheet_name"] == "AM-AB-H"
    assert result["known_incomplete_rows"][0]["excel_row_number"] == 79
    assert result["missing_value_imputation_authorized"] is False
    assert result["direct_nist_condition_comparability_established"] is False
    assert result["scientific_status_changed"] is False


def test_quality_contract_rejects_missingness_count_drift() -> None:
    manifest = _manifest()
    manifest["complete_numeric_measurement_row_count"] = 200289
    manifest["incomplete_numeric_measurement_row_count"] = 0
    _rehash(manifest)
    with pytest.raises(In625TensileQualityContractError, match="differs"):
        verify_in625_tensile_observed_quality(
            reviewed_tensile_manifest=manifest,
            quality_contract_path=CONTRACT,
        )


def test_quality_contract_rejects_anomaly_location_substitution() -> None:
    manifest = _manifest()
    manifest["bounded_incomplete_row_examples"][0]["excel_row_number"] = 80
    _rehash(manifest)
    with pytest.raises(In625TensileQualityContractError, match="identity differs"):
        verify_in625_tensile_observed_quality(
            reviewed_tensile_manifest=manifest,
            quality_contract_path=CONTRACT,
        )


def test_quality_contract_rejects_load_field_quality_drift() -> None:
    manifest = _manifest()
    load = manifest["reviewed_numeric_field_quality_counts"]["load_n"]
    load["numeric"] = 200289
    load["blank"] = 0
    _rehash(manifest)
    with pytest.raises(In625TensileQualityContractError, match="load_n"):
        verify_in625_tensile_observed_quality(
            reviewed_tensile_manifest=manifest,
            quality_contract_path=CONTRACT,
        )


def test_quality_contract_rejects_imputation_claim() -> None:
    manifest = _manifest()
    manifest["reviewed_semantics"]["missing_values_imputed"] = True
    _rehash(manifest)
    with pytest.raises(In625TensileQualityContractError, match="altered missingness"):
        verify_in625_tensile_observed_quality(
            reviewed_tensile_manifest=manifest,
            quality_contract_path=CONTRACT,
        )


def test_quality_contract_rejects_tampered_manifest_digest() -> None:
    manifest = _manifest()
    manifest["measurement_row_count"] = 1
    with pytest.raises(In625TensileQualityContractError, match="canonical SHA-256"):
        verify_in625_tensile_observed_quality(
            reviewed_tensile_manifest=manifest,
            quality_contract_path=CONTRACT,
        )
