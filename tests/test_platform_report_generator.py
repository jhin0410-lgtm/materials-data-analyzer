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
