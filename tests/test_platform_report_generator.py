import json
import shutil
from pathlib import Path

import pytest

from src.platform_core.report_generator import (
    generate_report,
    load_report_json,
    load_report_manifest,
    validate_report_config,
)
from src.platform_core.run_registry import store_scientific_trust_evaluation
from src.platform_core.scientific_execution import (
    ScientificExecutionRequest,
    execute_scientific_request,
    get_scientific_execution,
    persist_scientific_execution,
)
from src.platform_core.scientific_trust import evaluate_scientific_trust


def _config(output_dir="outputs/platform_reports/test_platform_report_generator"):
    return {
        "schema_version": "2.0",
        "report_id": "test_platform_report_generator",
        "formats": ["json", "markdown"],
        "selected_case_studies": ["reliability"],
        "output_dir": output_dir,
        "credential_policy": {"store_credentials": False},
    }


def test_preview_report_has_no_side_effects():
    target = Path("outputs/platform_reports/test_platform_report_preview")
    if target.exists():
        shutil.rmtree(target)

    result = generate_report(_config(str(target).replace("\\", "/")), write=False)

    assert result.output_dir is None
    assert result.written_files == ()
    assert not target.exists()
    assert result.report.scientific_recomputation_performed is False


def test_generate_report_writes_only_report_directory_and_valid_manifest():
    target = Path("outputs/platform_reports/test_platform_report_generator")
    if target.exists():
        shutil.rmtree(target)

    result = generate_report(_config(), write=True)

    assert set(path.name for path in target.iterdir()) == {
        "platform_report.json",
        "platform_report.md",
        "report_manifest.json",
    }
    assert all(str(path).startswith("outputs/platform_reports/") for path in result.written_files)
    manifest = load_report_manifest(target)
    report = load_report_json(target)
    assert manifest["scientific_recomputation_performed"] is False
    assert report["case_studies"][0]["case_study_id"] == "reliability"
    assert "report_manifest.json" in {Path(path).name for path in manifest["output_files"]}


def test_generate_report_rejects_overwrite_by_default():
    target = Path("outputs/platform_reports/test_platform_report_overwrite")
    if target.exists():
        shutil.rmtree(target)
    config = _config(str(target).replace("\\", "/"))
    generate_report(config, write=True)

    with pytest.raises(FileExistsError):
        generate_report(config, write=True)


def test_report_config_rejects_unsafe_output_paths():
    for output_dir in ["C:/tmp/report", "../outputs/platform_reports/bad", "outputs/not_reports/bad"]:
        config = _config(output_dir)
        with pytest.raises(ValueError):
            validate_report_config(config)


def test_report_config_rejects_unknown_case_study():
    config = _config("outputs/platform_reports/test_unknown_case")
    config["selected_case_studies"] = ["missing_case"]

    with pytest.raises(KeyError):
        generate_report(config, write=False)


def test_generated_report_contains_no_local_only_source_artifacts():
    target = Path("outputs/platform_reports/test_platform_report_sources")
    if target.exists():
        shutil.rmtree(target)
    result = generate_report(_config(str(target).replace("\\", "/")), write=True)
    source_artifacts = result.manifest["source_artifacts"]

    joined = json.dumps(source_artifacts)
    assert "analysis_ready" not in joined
    assert "classification_predictions" not in joined
    assert "data/raw" not in joined


def test_report_can_include_stored_scientific_trust_without_recomputing():
    registry_path = "outputs/platform_registry/test_report_scientific_trust.sqlite3"
    request = ScientificExecutionRequest.from_config(
        {
            "execution_id": "report_trust_bragg",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
            ],
            "requested_claim_ids": ["dimensionally_consistent"],
            "persist_findings": True,
        }
    )
    result = execute_scientific_request(request)
    persist_scientific_execution(request, result, registry_path=registry_path)
    execution = get_scientific_execution("report_trust_bragg", registry_path=registry_path)
    store_scientific_trust_evaluation(evaluate_scientific_trust(execution).to_dict(), registry_path=registry_path)

    config = _config("outputs/platform_reports/test_scientific_trust_report")
    config["include_scientific_trust"] = True
    config["registry_path"] = registry_path
    report = generate_report(config, write=False).report

    assert report.scientific_recomputation_performed is False
    assert report.scientific_trust_summary["status"] == "available"
    assert report.scientific_trust_summary["evaluation_count"] >= 1
