import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("configs/examples/external_source_compatibility_audit.json")
INPUTS = (
    Path("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json"),
    Path("data/processed/battery_v2_3_5_source_lineage_summary.json"),
)


def _fixture_repo(tmp_path: Path) -> Path:
    for source in (*INPUTS, CONFIG):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / source, target)
    return tmp_path


def _cli(cwd: Path, *args: str):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "src.cli", "--json", *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_preview_cli_is_side_effect_free(tmp_path):
    root = _fixture_repo(tmp_path)
    before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())

    result = _cli(root, "preview-external-source-compatibility", CONFIG.as_posix())
    after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "ready"
    assert payload["writes_performed"] is False
    assert payload["network_called"] is False
    assert before == after


def test_execute_cli_requires_flag_then_writes_only_bounded_results(tmp_path):
    root = _fixture_repo(tmp_path)
    blocked = _cli(root, "run-external-source-compatibility-audit", CONFIG.as_posix())
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "execution_not_authorized"

    executed = _cli(
        root,
        "run-external-source-compatibility-audit",
        CONFIG.as_posix(),
        "--execute",
    )
    payload = json.loads(executed.stdout)

    assert executed.returncode == 0
    assert payload["status"] == "completed"
    assert payload["summary"]["status"] == "partial"
    assert payload["network_called"] is False
    written = set(payload["written"])
    assert written == {
        "data/processed/external_source_compatibility_audit_summary_v1.json",
        "outputs/v2_5_external_source_compatibility/battery_source_lineage_to_external_source_v1.json",
        "outputs/v2_5_external_source_compatibility/materials_structure_summary_external_lineage_v1.json",
    }
    assert all((root / path).is_file() for path in written)


def test_validate_cli_accepts_summary_and_adapter_result(tmp_path):
    root = _fixture_repo(tmp_path)
    executed = _cli(
        root,
        "run-external-source-compatibility-audit",
        CONFIG.as_posix(),
        "--execute",
    )
    assert executed.returncode == 0

    summary = _cli(
        root,
        "validate-external-source-compatibility",
        "data/processed/external_source_compatibility_audit_summary_v1.json",
    )
    detail = _cli(
        root,
        "validate-external-source-compatibility",
        "outputs/v2_5_external_source_compatibility/materials_structure_summary_external_lineage_v1.json",
    )

    assert summary.returncode == detail.returncode == 0
    assert json.loads(summary.stdout)["record_type"] == "summary"
    assert json.loads(detail.stdout)["record_type"] == "adapter_result"
