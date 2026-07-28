import hashlib
import json
from pathlib import Path

import pytest

from src.platform_core.battery_external_cohort_admission import (
    ADMISSION_STAGES,
    GATE_ID,
    GATE_VERSION,
    REQUIRED_EVIDENCE_FIELDS,
    BatteryExternalCohortAdmissionConfig,
    build_admission_matrix,
    canonical_checksum,
    load_config,
    main,
    preview_admission,
    run_admission,
    validate_candidate_manifest,
    validate_result_payload,
)


def _write_fixture(root: Path) -> Path:
    manifest = json.loads(
        Path("data/platform/battery_archive_candidate_manifest_v1.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(
        Path("configs/examples/battery_external_cohort_admission.json").read_text(
            encoding="utf-8"
        )
    )
    manifest_path = root / config["candidate_manifest_path"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    prior = {
        "schema_version": "2.6.3",
        "artifact_kind": "battery_comparability_evidence_compact_summary",
        "deterministic_result_checksum": config["expected_comparability_checksum"],
        "comparability_decision": {"status": "comparability_not_established"},
        "data_inference_performed": False,
        "model_retrained": False,
        "metrics_recomputed": False,
        "preservation_checks": {
            "preserved_metrics": [
                {"model": "persistence", "mae": config["expected_persistence_mae"]},
                {"model": "ridge", "mae": config["expected_ridge_mae"]},
            ]
        },
    }
    prior_path = root / config["source_comparability_summary_path"]
    prior_path.parent.mkdir(parents=True, exist_ok=True)
    prior_path.write_text(json.dumps(prior, indent=2), encoding="utf-8")

    for field in ("source_inventory_audit_path", "source_case_study_spec_path"):
        path = root / config[field]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# fixture for {field}\n", encoding="utf-8")

    config_path = root / "configs/admission.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_candidate_is_inventory_only_and_not_admitted_for_validation(tmp_path):
    config_path = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    execution = run_admission(config, tmp_path, write_outputs=False)
    result = execution["result"]

    assert result["admission_decision"]["inventory_review"]["status"] == (
        "admitted_with_restrictions"
    )
    assert result["admission_decision"]["cross_cohort_comparability"]["status"] == (
        "not_admitted"
    )
    assert result["admission_decision"]["predictive_validation"]["status"] == (
        "blocked"
    )
    assert result["admission_decision"]["overall_status"] == (
        "not_admitted_for_cross_cohort_validation"
    )
    assert result["coverage_summary"]["requirement_satisfied_count"] == 0
    assert result["unresolved_information"] == list(REQUIRED_EVIDENCE_FIELDS)


def test_filename_labels_and_observed_signals_do_not_satisfy_source_evidence(tmp_path):
    config_path = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    manifest = validate_candidate_manifest(
        json.loads((tmp_path / config.candidate_manifest_path).read_text())
    )
    matrix = build_admission_matrix(manifest).set_index("evidence_field")

    assert matrix.loc["chemistry", "filename_derived"]
    assert matrix.loc["chemistry", "inference_required"]
    assert not matrix.loc["chemistry", "requirement_satisfied"]
    assert matrix.loc["charge_protocol", "filename_derived"]
    assert not matrix.loc["charge_protocol", "requirement_satisfied"]
    assert matrix.loc["ambient_temperature", "source_backed"]
    assert not matrix.loc["ambient_temperature", "commanded_condition_evidence"]
    assert not matrix.loc["ambient_temperature", "requirement_satisfied"]
    assert not matrix.loc["cutoff_voltage", "requirement_satisfied"]


def test_prior_metrics_and_comparability_conclusion_are_preserved(tmp_path):
    config_path = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    result = run_admission(config, tmp_path, write_outputs=False)["result"]
    checks = result["preservation_checks"]

    assert checks["comparability_checksum_verified"] is True
    assert checks["prior_comparability_status"] == "comparability_not_established"
    assert checks["prior_comparability_status_preserved"] is True
    assert checks["model_metrics_unchanged"] is True
    assert checks["model_or_metric_change_performed"] is False
    assert checks["preserved_metrics"] == [
        {"model": "persistence", "mae": pytest.approx(3.425575369058076)},
        {"model": "ridge", "mae": pytest.approx(4.15369918179312)},
    ]


def test_deterministic_non_mutating_and_no_execution(tmp_path):
    config_path = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    before = _hashes(tmp_path)
    execution = run_admission(config, tmp_path, write_outputs=False)
    result = execution["result"]
    after = _hashes(tmp_path)

    assert before == after
    assert result["first_run_checksum"] == result["second_run_checksum"]
    assert result["deterministic_rerun_match"] is True
    for field in (
        "network_called",
        "credentials_read",
        "raw_data_read",
        "archives_extracted",
        "filename_metadata_parsed",
        "source_mutation_performed",
        "model_trained",
        "model_evaluated",
        "metrics_recomputed",
        "data_inference_performed",
    ):
        assert result[field] is False
        assert execution[field] is False
    assert validate_result_payload(result)["valid"] is True


def test_preview_is_side_effect_free(tmp_path):
    config_path = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    before = _hashes(tmp_path)
    preview = preview_admission(config, tmp_path)
    after = _hashes(tmp_path)

    assert before == after
    assert preview["status"] == "ready"
    assert preview["writes_performed"] is False
    assert preview["overall_status"] == "not_admitted_for_cross_cohort_validation"
    assert preview["blocking_fields"] == list(REQUIRED_EVIDENCE_FIELDS)


def test_cli_run_and_validate_registered_outputs(tmp_path, monkeypatch, capsys):
    _write_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["--json", "--config", "configs/admission.json", "preview"]) == 0
    assert json.loads(capsys.readouterr().out)["writes_performed"] is False

    assert main(["--json", "--config", "configs/admission.json", "run"]) == 0
    run_payload = json.loads(capsys.readouterr().out)
    assert len(run_payload["written"]) == 3
    assert run_payload["admission_decision"]["predictive_validation"]["status"] == (
        "blocked"
    )

    result_path = (
        "outputs/v2_6_battery_external_cohort_admission/admission_summary.json"
    )
    assert main(["--json", "validate", result_path]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_checksum_mismatch_and_result_tampering_are_rejected(tmp_path):
    config_path = _write_fixture(tmp_path)
    payload = json.loads(config_path.read_text())
    payload["expected_comparability_checksum"] = "0" * 64
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    with pytest.raises(ValueError, match="source comparability checksum mismatch"):
        run_admission(config, tmp_path, write_outputs=False)

    _write_fixture(tmp_path)
    config = load_config("configs/admission.json", tmp_path)
    result = run_admission(config, tmp_path, write_outputs=False)["result"]
    result["coverage_summary"]["requirement_satisfied_count"] = 8
    validation = validate_result_payload(result)
    assert validation["valid"] is False
    assert "deterministic checksum mismatch" in validation["errors"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_manifest_path", "../outside.json"),
        ("source_inventory_audit_path", "C:/outside.md"),
        ("output_root", "/tmp/output"),
    ],
)
def test_absolute_and_traversal_paths_are_rejected(tmp_path, field, value):
    config_path = _write_fixture(tmp_path)
    payload = json.loads(config_path.read_text())
    payload[field] = value
    with pytest.raises(ValueError) as exc_info:
        BatteryExternalCohortAdmissionConfig.from_mapping(payload)
    assert (
        "repository-relative" in str(exc_info.value)
        or "output_root does not match" in str(exc_info.value)
    )


def test_unknown_manifest_fields_and_claim_promotion_are_rejected(tmp_path):
    config_path = _write_fixture(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    manifest_path = tmp_path / config.candidate_manifest_path
    manifest = json.loads(manifest_path.read_text())
    manifest["unexpected"] = "value"
    with pytest.raises(ValueError, match="unknown candidate manifest field"):
        validate_candidate_manifest(manifest)

    manifest.pop("unexpected")
    manifest["claim_policy"]["filename_labels_are_source_evidence"] = True
    with pytest.raises(ValueError, match="prohibit inferred equivalence"):
        validate_candidate_manifest(manifest)


def test_schema_and_config_files_parse():
    paths = (
        Path("data/platform/battery_external_cohort_admission_config_schema_v1.json"),
        Path("data/platform/battery_external_cohort_manifest_schema_v1.json"),
        Path("data/platform/battery_external_cohort_admission_result_schema_v1.json"),
        Path("data/platform/battery_archive_candidate_manifest_v1.json"),
        Path("configs/examples/battery_external_cohort_admission.json"),
    )
    for path in paths:
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_actual_tracked_summary_matches_closeout_and_platform_version():
    path = Path(
        "data/processed/battery_v2_6_4_external_cohort_admission_summary.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    validation = validate_result_payload(payload)

    assert validation["valid"] is True
    assert payload["schema_version"] == GATE_VERSION
    assert payload["gate_id"] == GATE_ID
    assert payload["required_evidence_fields"] == list(REQUIRED_EVIDENCE_FIELDS)
    assert payload["admission_stages"] == list(ADMISSION_STAGES)
    assert payload["admission_decision"]["overall_status"] == (
        "not_admitted_for_cross_cohort_validation"
    )
    assert payload["scientific_closeout"]["status"] == "inconclusive"
    assert payload["coverage_summary"]["requirement_satisfied_count"] == 0
    assert payload["preservation_checks"]["model_metrics_unchanged"] is True

    from src.platform_core.version import PLATFORM_VERSION

    assert PLATFORM_VERSION == "2.7.0"


def test_module_has_no_network_archive_model_or_dynamic_execution():
    text = Path(
        "src/platform_core/battery_external_cohort_admission.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "import requests",
        "import urllib",
        "import zipfile",
        "from sklearn",
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
