import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_preview_report_json_has_no_output_dir():
    result = _run_cli("--json", "preview-report", "--config", "configs/examples/platform_report_all_case_studies.json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["generation_status"] == "preview_only"
    assert payload["output_dir"] is None
    assert payload["scientific_recomputation_performed"] is False
    assert payload["case_study_ids"] == ["battery_archive", "materials_project", "smart_factory", "reliability"]


def test_cli_generate_validate_and_inspect_report(tmp_path):
    config = json.loads(Path("configs/examples/platform_report_reliability_only.json").read_text(encoding="utf-8"))
    config["report_id"] = "test_cli_report"
    config["output_dir"] = "outputs/platform_reports/test_cli_report"
    config["overwrite"] = True
    config_path = tmp_path / "report_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    generated = _run_cli("--json", "generate-report", "--config", str(config_path), "--overwrite")

    assert generated.returncode == 0
    generated_payload = json.loads(generated.stdout)
    assert generated_payload["generation_status"] == "completed"
    assert len(generated_payload["written_files"]) == 3

    validated = _run_cli("--json", "validate-report", "outputs/platform_reports/test_cli_report")
    inspected = _run_cli("--json", "inspect-report", "outputs/platform_reports/test_cli_report")
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["valid"] is True
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["case_study_ids"] == ["reliability"]


def test_cli_list_report_sources_is_deterministic():
    result = _run_cli("list-report-sources")

    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert [line.split("\t")[0] for line in lines] == [
        "battery_archive",
        "materials_project",
        "reliability",
        "smart_factory",
    ]
