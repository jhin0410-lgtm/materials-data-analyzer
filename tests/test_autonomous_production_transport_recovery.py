from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

_BASE_PATH = Path(__file__).with_name("autonomous_production_transport_recovery_regression_base.py")
_SPEC = importlib.util.spec_from_file_location(
    "_autonomous_production_transport_recovery_regression_base",
    _BASE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_base)

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
_original_prepare = _base._prepare_pretransport_state


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rehash(value: dict[str, Any], field: str) -> None:
    value.pop(field, None)
    value[field] = _base.recovery._canonical_sha(value)


def _prepare_pretransport_state(
    root: Path,
    output_root: str | Path,
    *,
    persist_partial_nist_bytes: bool = True,
) -> Path:
    output = _original_prepare(
        root,
        output_root,
        persist_partial_nist_bytes=persist_partial_nist_bytes,
    )
    quality_path = output / "tensile-quality-verification.json"
    quality = _read(quality_path)
    quality.update(
        {
            "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
            "isolated_source_missingness_observed": True,
            "missingness_mechanism_established": False,
        }
    )
    _rehash(quality, "verification_sha256")
    _base._write_json(quality_path, quality)

    rediagnosis_path = output / "quality-aware-rediagnosis.json"
    rediagnosis = _read(rediagnosis_path)
    rediagnosis["observed_quality_verification_sha256"] = quality["verification_sha256"]
    rediagnosis["observed_quality_verification"] = quality
    rediagnosis["evidence_state"] = {
        "real_external_source_acquired": True,
        "real_row_level_measurements_observed": True,
        "measurement_semantics_partially_reviewed": True,
        "replicate_independence_established": False,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "observed_source_quality_contract_verified": True,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "isolated_source_missingness_observed": True,
        "missingness_mechanism_established": False,
        "missing_value_imputation_authorized": False,
    }
    next_action = dict(rediagnosis["next_action"])
    next_action["source_quality_constraint"] = {
        "quality_contract_verified": True,
        "affected_field": "load_n",
        "affected_row_count": 1,
        "missing_value_imputation_authorized": False,
        "inverse_reconstruction_authorized": False,
        "row_exclusion_authorized": False,
    }
    rediagnosis["next_action"] = next_action
    _rehash(rediagnosis, "rediagnosis_sha256")
    _base._write_json(rediagnosis_path, rediagnosis)

    assessment_path = output / "physical-comparability-assessment.json"
    assessment = _read(assessment_path)
    assessment["predecessor_rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    assessment["observed_quality_verification_sha256"] = quality["verification_sha256"]
    assessment["source_quality_constraint"] = {
        "known_incomplete_row_count": 1,
        "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
        "missing_value_imputation_authorized": False,
        "inverse_reconstruction_authorized": False,
        "row_exclusion_authorized": False,
        "missingness_mechanism_established": False,
    }
    _rehash(assessment, "assessment_sha256")
    _base._write_json(assessment_path, assessment)

    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    cycle1, cycle2 = [dict(item) for item in manifest["cycles"]]
    cycle1["quality_verification_sha256"] = quality["verification_sha256"]
    cycle1["rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    _rehash(cycle1, "cycle_sha256")
    cycle2["predecessor_cycle_sha256"] = cycle1["cycle_sha256"]
    cycle2["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(cycle2, "cycle_sha256")
    manifest["cycles"] = [cycle1, cycle2]
    manifest["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(manifest, "manifest_sha256")
    _base._write_json(manifest_path, manifest)

    qualification_path = output / "nist-network-policy-qualification.json"
    qualification = _read(qualification_path)
    qualification["issue_76_automatic_promotion_authorized"] = False
    qualification["paper_and_other_source_lanes_remain_allowed"] = True
    _rehash(qualification, "qualification_sha256")
    _base._write_json(qualification_path, qualification)
    return output


_base._prepare_pretransport_state = _prepare_pretransport_state

for _name in dir(_base):
    if _name.startswith("test_"):
        globals()[_name] = getattr(_base, _name)
