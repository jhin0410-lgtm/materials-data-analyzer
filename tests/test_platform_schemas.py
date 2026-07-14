import json
from pathlib import Path


def test_platform_schema_json_files_parse():
    for path in [
        Path("data/platform/pipeline_config_schema_v2.json"),
        Path("data/platform/run_manifest_schema_v2.json"),
        Path("data/platform/case_study_onboarding_schema_v2.json"),
        Path("data/platform/platform_report_schema_v2.json"),
        Path("data/platform/report_manifest_schema_v2.json"),
    ]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "2.0"
        assert payload["status"] == "scaffold_stage"
    registry_schema = json.loads(Path("data/platform/platform_registry_schema_v2.json").read_text(encoding="utf-8"))
    assert registry_schema["schema_version"] == "2.1"
    assert registry_schema["status"] == "development_stage"


def test_example_configs_have_no_credentials_or_absolute_paths():
    for path in Path("configs/examples").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "C:/" not in text
        assert "C:\\" not in text
        assert "password=" not in text.lower()
        assert "secret=" not in text.lower()
        assert "token=" not in text.lower()
        payload = json.loads(text)
        assert payload["credential_policy"]["store_credentials"] is False
        if "artifact_definitions" in payload:
            assert payload["schema_version"] == "2.0"
            assert payload.get("execution_candidate") is not True
        elif payload.get("report_id"):
            assert payload["schema_version"] == "2.0"
            assert payload["output_dir"].startswith("outputs/platform_reports/")
            assert payload["credential_policy"]["store_credentials"] is False
        elif payload.get("execution_mode"):
            assert payload["execution_mode"] in {"verify", "isolated_run"}
        else:
            assert payload["dry_run"] is True


def test_platform_docs_are_scaffold_stage_not_completed_pipeline():
    text = Path("docs/PLATFORM_V2_PLAN.md").read_text(encoding="utf-8")

    assert "Status: `development_stage`" in text
    assert "does not execute actual acquisition" in text
    assert "Actual `run` execution is intentionally deferred" in text
