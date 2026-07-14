import json

import pytest

from src.platform_core.report_generator import generate_report, load_report_manifest, validate_report_manifest


def _config(output_dir="outputs/platform_reports/test_platform_report_security"):
    return {
        "schema_version": "2.0",
        "report_id": "test_platform_report_security",
        "formats": ["json", "markdown"],
        "selected_case_studies": ["materials_project"],
        "output_dir": output_dir,
        "overwrite": True,
        "credential_policy": {"store_credentials": False},
    }


def test_report_manifest_has_no_absolute_paths_or_credentials():
    result = generate_report(_config(), write=True)
    manifest = load_report_manifest("outputs/platform_reports/test_platform_report_security")
    text = json.dumps(manifest, sort_keys=True)

    assert manifest["local_only"] is True
    assert manifest["scientific_recomputation_performed"] is False
    assert "C:/" not in text
    assert "C:\\" not in text
    assert "password" not in text.lower()
    assert "credential" not in text.lower()
    assert all(path.startswith("outputs/platform_reports/") for path in result.written_files)


def test_report_manifest_validation_rejects_recomputation_claim():
    manifest = load_report_manifest("outputs/platform_reports/test_platform_report_security")
    manifest["scientific_recomputation_performed"] = True

    with pytest.raises(ValueError):
        validate_report_manifest(manifest)


def test_report_source_files_exclude_raw_and_local_only_artifacts():
    result = generate_report(_config("outputs/platform_reports/test_platform_report_security_sources"), write=True)

    assert all("data/raw/" not in artifact for artifact in result.manifest["source_artifacts"])
    assert all("classification_predictions" not in artifact for artifact in result.manifest["source_artifacts"])
    assert all("analysis_ready.csv" not in artifact for artifact in result.manifest["source_artifacts"])
