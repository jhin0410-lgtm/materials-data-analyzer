from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_nist_ambench_2018_02_process_design.py"


def _module():
    spec = importlib.util.spec_from_file_location("nist_design_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _nist_table() -> pd.DataFrame:
    rows = []
    for case_id, power, speed, traces in (
        ("A", 137.9, 400.0, (5, 6, 7)),
        ("B", 179.2, 800.0, (8, 9, 10)),
        ("C", 179.2, 1200.0, (1, 2, 3, 4)),
    ):
        for trace in traces:
            rows.append(
                {
                    "sample_id": f"amb2018_02_ammt_trace_{trace:02d}",
                    "case_id": case_id,
                    "actual_laser_power_w": power,
                    "scan_speed_mm_s": speed,
                    "char__optical_microscopy_metrology__melt_pool_width_mean__um": 100.0
                    + trace,
                }
            )
    return pd.DataFrame(rows)


def test_audit_reports_replication_rank_and_modeling_block() -> None:
    module = _module()
    conditions, audit = module.audit_process_design(_nist_table())

    assert conditions[["case_id", "replicate_count"]].to_dict("records") == [
        {"case_id": "A", "replicate_count": 3},
        {"case_id": "B", "replicate_count": 3},
        {"case_id": "C", "replicate_count": 4},
    ]
    assert audit["sample_count"] == 10
    assert audit["unique_condition_count"] == 3
    assert audit["condition_identity_contract"] == {
        "case_id_to_process_condition_one_to_one": True,
        "process_condition_to_case_id_one_to_one": True,
        "condition_key": ["actual_laser_power_w", "scan_speed_mm_s"],
    }
    assert audit["replication"]["pure_error_degrees_of_freedom"] == 7
    assert audit["factor_support"]["full_factorial_condition_count"] == 6
    assert audit["factor_support"]["observed_factorial_condition_count"] == 3
    assert audit["factor_support"]["factorial_coverage_fraction"] == pytest.approx(0.5)
    assert (
        audit["factor_support"]["direct_matched_speed_power_contrast_available"]
        is False
    )
    assert (
        audit["factor_support"]["direct_within_power_speed_contrast_available"]
        is True
    )
    assert audit["design_models"]["main_effects"] == {
        "name": "intercept + power + speed",
        "parameter_names": ["intercept", "actual_laser_power_w", "scan_speed_mm_s"],
        "parameter_count": 3,
        "matrix_rank": 3,
        "full_column_rank": True,
        "condition_level_residual_df": 0,
        "identifiable_from_observed_conditions": True,
        "model_adequacy_test_available": False,
    }
    assert audit["design_models"]["main_effects_plus_interaction"]["matrix_rank"] == 3
    assert (
        audit["design_models"]["main_effects_plus_interaction"][
            "identifiable_from_observed_conditions"
        ]
        is False
    )
    assert audit["design_models"]["quadratic_response_surface"]["matrix_rank"] == 3
    assert audit["readiness"]["overall"] == "not_ready_for_predictive_or_causal_modeling"
    assert audit["readiness"]["main_effect_coefficient_fitting"] == (
        "algebraically_estimable_but_not_scientifically_validated"
    )
    assert audit["software_validation"] == {
        "model_trained": False,
        "response_metric_recomputed": False,
        "optimization_performed": False,
        "row_order_used": False,
        "missing_conditions_inferred": False,
    }


def test_audit_is_row_order_independent_and_deterministic(tmp_path: Path) -> None:
    module = _module()
    first_source = tmp_path / "first.csv"
    second_source = tmp_path / "second.csv"
    table = _nist_table()
    table.to_csv(first_source, index=False)
    table.sample(frac=1.0, random_state=42).to_csv(second_source, index=False)

    first = module.run_audit(first_source, tmp_path / "first")
    second = module.run_audit(second_source, tmp_path / "second")

    assert first["condition_matrix"].read_bytes() == second["condition_matrix"].read_bytes()
    first_audit = json.loads(first["audit"].read_text(encoding="utf-8"))
    second_audit = json.loads(second["audit"].read_text(encoding="utf-8"))
    first_audit.pop("input")
    second_audit.pop("input")
    assert first_audit == second_audit
    assert first["report"].read_bytes() == second["report"].read_bytes()


def test_audit_rejects_invalid_identity_and_process_values() -> None:
    module = _module()
    duplicate = _nist_table()
    duplicate.loc[1, "sample_id"] = duplicate.loc[0, "sample_id"]
    with pytest.raises(ValueError, match="sample_id values must be unique"):
        module.audit_process_design(duplicate)

    invalid = _nist_table()
    invalid.loc[0, "scan_speed_mm_s"] = -1
    with pytest.raises(ValueError, match="must be positive"):
        module.audit_process_design(invalid)

    ambiguous = _nist_table()
    ambiguous.loc[
        ambiguous["case_id"].eq("A"), "actual_laser_power_w"
    ] = [137.9, 138.0, 137.9]
    with pytest.raises(ValueError, match="case_id must map to exactly one"):
        module.audit_process_design(ambiguous)


def test_audit_rejects_multiple_case_ids_for_one_physical_condition() -> None:
    module = _module()
    duplicated_condition = _nist_table()
    duplicated_condition.loc[
        duplicated_condition["case_id"].eq("B"),
        ["actual_laser_power_w", "scan_speed_mm_s"],
    ] = [137.9, 400.0]

    with pytest.raises(
        ValueError,
        match="physical process condition must map to exactly one case_id",
    ):
        module.audit_process_design(duplicated_condition)


def test_cli_writes_checksummed_outputs_and_no_model_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "integrated_sample_table.csv"
    _nist_table().to_csv(source, index=False)
    output = tmp_path / "audit"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--integrated-table",
            str(source),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "audit completed" in completed.stdout.lower()
    manifest = json.loads(
        (output / "process_design_audit_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["model_trained"] is False
    assert manifest["optimization_performed"] is False
    assert manifest["scientific_status"] == "Diagnostic"
    for name, filename in manifest["outputs"].items():
        assert manifest["output_sha256"][name] == module_sha(output / filename)
    assert not list(output.glob("*.pkl"))
    assert not list(output.glob("*model*"))


def module_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_nonempty_output_is_preserved(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "input.csv"
    _nist_table().to_csv(source, index=False)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        module.run_audit(source, output)
    assert sentinel.read_text(encoding="utf-8") == "keep"
