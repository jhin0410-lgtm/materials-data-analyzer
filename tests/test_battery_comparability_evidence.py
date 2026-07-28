import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.platform_core.battery_comparability_evidence import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_TRACKED_SUMMARY,
    PACKAGE_ID,
    PACKAGE_VERSION,
    REQUIRED_EVIDENCE_FIELDS,
    BatteryComparabilityEvidenceConfig,
    build_compact_summary,
    load_config,
    main,
    preview_package,
    run_package,
    validate_result_payload,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_fixture(root: Path) -> tuple[Path, dict]:
    source_rows = []
    for group_index in range(4):
        for cycle in range(1, 7):
            temperature = 24 if group_index < 3 else (24 if cycle < 4 else 43)
            source_rows.append(
                {
                    "battery_id": f"B{group_index:04d}",
                    "cycle_index": cycle,
                    "ambient_temperature_c": temperature,
                    "reference_capacity_ah": 1.8,
                }
            )
    source_path = root / "data/processed/source.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(source_rows).to_csv(source_path, index=False)

    lineage_path = root / "data/processed/lineage.json"
    _write_json(
        lineage_path,
        {
            "schema_version": "2.3.5",
            "exact_lineage_cell_count": 4,
            "analysis_ready_rows": 24,
            "exact_source_key_match_rows": 24,
            "source_evidence_checksum": "0" * 64,
            "archive_sha256": "1" * 64,
            "metadata_sha256": "2" * 64,
        },
    )
    metadata_path = root / "data/processed/metadata.csv"
    pd.DataFrame(
        [
            {
                "metadata_field": "documented_protocol_group",
                "expected_records": 4,
                "supported_records": 4,
                "recovery_status": "recovered_with_group_granularity",
                "integration_status": "local_cell_lineage_only",
                "external_data_required": False,
                "limitation": "cycle-specific command log unavailable",
            },
            {
                "metadata_field": "measured_current_summary",
                "expected_records": 24,
                "supported_records": 24,
                "recovery_status": "recovered_exact",
                "integration_status": "local_cycle_metadata_only",
                "external_data_required": False,
                "limitation": "observed current is not a commanded protocol log",
            },
            {
                "metadata_field": "measurement_uncertainty",
                "expected_records": 24,
                "supported_records": 0,
                "recovery_status": "genuinely_unavailable",
                "integration_status": "unavailable",
                "external_data_required": True,
                "limitation": "zero uncertainty was not assigned",
            },
            {
                "metadata_field": "official_original_snapshot_version",
                "expected_records": 1,
                "supported_records": 0,
                "recovery_status": "genuinely_unavailable",
                "integration_status": "unavailable",
                "external_data_required": True,
                "limitation": "official NASA snapshot/version is not verified",
            },
        ]
    ).to_csv(metadata_path, index=False)

    metrics = [
        {
            "model": "persistence",
            "prediction_count": 20,
            "mae": 3.425575369058076,
            "rmse": 11.57285420986917,
        },
        {
            "model": "ridge",
            "prediction_count": 20,
            "mae": 4.15369918179312,
            "rmse": 11.222329810780126,
        },
    ]
    benchmark_path = root / "data/processed/benchmark.json"
    diagnostic_path = root / "data/processed/diagnostic.json"
    benchmark_checksum = "a" * 64
    diagnostic_checksum = "b" * 64
    _write_json(
        benchmark_path,
        {
            "aggregate_metrics": metrics,
            "scientific_assessment": {"status": "unsupported"},
            "deterministic_result_checksum": benchmark_checksum,
        },
    )
    _write_json(
        diagnostic_path,
        {
            "aggregate_metrics": metrics,
            "comparability_readiness": {
                "status": "comparability_not_established"
            },
            "deterministic_result_checksum": diagnostic_checksum,
        },
    )

    payload = {
        "schema_version": PACKAGE_VERSION,
        "package_id": PACKAGE_ID,
        "case_study_id": "kaggle_battery",
        "source_analysis_ready_path": "data/processed/source.csv",
        "source_lineage_path": "data/processed/lineage.json",
        "metadata_recovery_summary_path": "data/processed/metadata.csv",
        "source_benchmark_summary_path": "data/processed/benchmark.json",
        "source_diagnostic_summary_path": "data/processed/diagnostic.json",
        "expected_benchmark_checksum": benchmark_checksum,
        "expected_diagnostic_checksum": diagnostic_checksum,
        "group_column": "battery_id",
        "temperature_column": "ambient_temperature_c",
        "required_evidence_fields": list(REQUIRED_EVIDENCE_FIELDS),
        "credential_policy": {
            "store_credentials": False,
            "network_access_required": False,
        },
        "output_root": DEFAULT_OUTPUT_ROOT,
        "tracked_summary_path": DEFAULT_TRACKED_SUMMARY,
        "output_policy": "local_details_and_tracked_compact_summary",
    }
    config_path = root / "configs/comparability.json"
    _write_json(config_path, payload)
    return config_path, payload


def test_evidence_matrix_is_predeclared_and_non_inferential(tmp_path):
    config_path, _ = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    result = run_package(config, tmp_path, write_outputs=False)["result"]
    matrix = result["evidence_matrix"]

    assert [row["evidence_field"] for row in matrix] == list(
        REQUIRED_EVIDENCE_FIELDS
    )
    assert all(row["inference_performed"] is False for row in matrix)
    assert all(
        row["same_condition_assumption_made"] is False for row in matrix
    )
    assert all(row["comparability_established"] is False for row in matrix)
    statuses = {row["evidence_field"]: row["evidence_status"] for row in matrix}
    assert statuses["chemistry"] == "unresolved"
    assert statuses["nominal_capacity"] == "unresolved_derived_reference_only"
    assert statuses["ambient_temperature"] == "observed_heterogeneous"
    assert statuses["charge_protocol"] == "partial_group_level_only"
    assert statuses["cutoff_voltage"] == "unresolved"
    assert result["comparability_decision"]["status"] == (
        "comparability_not_established"
    )
    assert result["scientific_closeout"]["status"] == "inconclusive"


def test_model_metrics_and_prior_conclusions_are_preserved(tmp_path):
    config_path, _ = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    result = run_package(config, tmp_path, write_outputs=False)["result"]
    checks = result["preservation_checks"]

    assert checks["benchmark_checksum_verified"] is True
    assert checks["diagnostic_checksum_verified"] is True
    assert checks["model_metrics_unchanged"] is True
    assert checks["prior_scientific_assessment"] == "unsupported"
    assert checks["prior_comparability_status"] == (
        "comparability_not_established"
    )
    assert checks["model_or_metric_change_performed"] is False
    assert result["model_retrained"] is False
    assert result["metrics_recomputed"] is False


def test_source_files_are_unchanged_and_result_is_deterministic(tmp_path):
    config_path, _ = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    before = {
        path.relative_to(tmp_path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    result = run_package(config, tmp_path, write_outputs=False)["result"]

    after = {
        path.relative_to(tmp_path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert result["source_hashes_before"] == result["source_hashes_after"]
    assert result["first_run_checksum"] == result["second_run_checksum"]
    assert result["deterministic_rerun_match"] is True
    assert validate_result_payload(result)["valid"] is True
    compact = build_compact_summary(result)
    assert validate_result_payload(compact)["valid"] is True


def test_preview_is_side_effect_free(tmp_path):
    config_path, _ = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    payload = preview_package(config, tmp_path)

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert before == after
    assert payload["status"] == "ready"
    assert payload["writes_performed"] is False
    assert payload["comparability_status"] == "comparability_not_established"
    assert payload["model_retrained"] is False
    assert payload["metrics_recomputed"] is False
    assert payload["data_inference_performed"] is False


def test_run_and_validate_module_cli(tmp_path, monkeypatch, capsys):
    _write_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(
        ["--json", "preview", "configs/comparability.json"]
    ) == 0
    assert json.loads(capsys.readouterr().out)["writes_performed"] is False

    assert main(["--json", "run", "configs/comparability.json"]) == 0
    run_payload = json.loads(capsys.readouterr().out)
    assert len(run_payload["written"]) == 3
    result_path = (
        "outputs/v2_6_battery_comparability/comparability_summary.json"
    )
    assert main(["--json", "validate", result_path]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_checksum_mismatch_tampering_and_dynamic_fields_are_rejected(tmp_path):
    config_path, payload = _write_fixture(tmp_path)
    payload["expected_benchmark_checksum"] = "f" * 64
    _write_json(config_path, payload)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    with pytest.raises(ValueError, match="source benchmark checksum mismatch"):
        run_package(config, tmp_path, write_outputs=False)

    _, payload = _write_fixture(tmp_path)
    payload["model_class"] = "sklearn.linear_model.Ridge"
    with pytest.raises(ValueError, match="unknown config field"):
        BatteryComparabilityEvidenceConfig.from_mapping(payload)

    config = BatteryComparabilityEvidenceConfig.from_mapping(
        _write_fixture(tmp_path)[1]
    )
    result = run_package(config, tmp_path, write_outputs=False)["result"]
    result["coverage_summary"]["battery_count"] += 1
    validation = validate_result_payload(result)
    assert validation["valid"] is False
    assert "deterministic checksum mismatch" in validation["errors"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_analysis_ready_path", "../outside.csv"),
        ("source_lineage_path", "C:/outside/lineage.json"),
        ("output_root", "/tmp/output"),
    ],
)
def test_absolute_and_traversal_paths_are_rejected(tmp_path, field, value):
    _, payload = _write_fixture(tmp_path)
    payload[field] = value
    with pytest.raises(ValueError) as exc_info:
        BatteryComparabilityEvidenceConfig.from_mapping(payload)
    assert (
        "repository-relative" in str(exc_info.value)
        or "output paths do not match" in str(exc_info.value)
    )


def test_actual_tracked_summary_preserves_v2_6_boundaries():
    path = Path(
        "data/processed/battery_v2_6_3_comparability_evidence_summary.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert validate_result_payload(payload)["valid"] is True
    assert payload["coverage_summary"]["battery_count"] == 34
    assert payload["coverage_summary"]["analysis_ready_row_count"] == 2495
    assert payload["comparability_decision"]["status"] == (
        "comparability_not_established"
    )
    assert payload["scientific_closeout"]["status"] == "inconclusive"
    assert payload["preservation_checks"]["prior_scientific_assessment"] == (
        "unsupported"
    )
    metrics = {
        row["model"]: row
        for row in payload["preservation_checks"]["preserved_metrics"]
    }
    assert metrics["persistence"]["mae"] == pytest.approx(3.425575369058076)
    assert metrics["ridge"]["mae"] == pytest.approx(4.15369918179312)
    from src.platform_core.version import PLATFORM_VERSION

    assert PLATFORM_VERSION == "2.7.0"


def test_config_result_schemas_and_example_config_parse():
    for path in (
        Path(
            "data/platform/"
            "battery_comparability_evidence_config_schema_v1.json"
        ),
        Path(
            "data/platform/"
            "battery_comparability_evidence_result_schema_v1.json"
        ),
        Path("configs/examples/battery_comparability_evidence.json"),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_module_has_no_model_network_dynamic_execution_or_pickle():
    text = Path(
        "src/platform_core/battery_comparability_evidence.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "from sklearn",
        "import requests",
        "import urllib",
        "importlib",
        "subprocess",
        "pickle",
        "eval(",
        "exec(",
        ".fit(",
        ".predict(",
    )
    for token in forbidden:
        assert token not in text
