import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("configs/examples/retrieval_reproducibility_audit.json")
INPUTS = (
    Path("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json"),
    Path("data/processed/battery_v2_3_5_source_lineage_summary.json"),
    Path("data/processed/external_source_compatibility_audit_summary_v1.json"),
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


def _files(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_preview_cli_is_side_effect_free(tmp_path):
    root = _fixture_repo(tmp_path)
    before = _files(root)

    result = _cli(
        root,
        "preview-retrieval-reproducibility-audit",
        CONFIG.as_posix(),
    )
    after = _files(root)
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "ready"
    assert payload["valid_paired_retrieval_available"] is False
    assert payload["writes_performed"] is False
    assert payload["network_called"] is False
    assert before == after


def test_run_cli_requires_execute_and_writes_only_bounded_outputs(tmp_path):
    root = _fixture_repo(tmp_path)
    blocked = _cli(
        root,
        "run-retrieval-reproducibility-audit",
        CONFIG.as_posix(),
    )
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "execution_not_authorized"

    executed = _cli(
        root,
        "run-retrieval-reproducibility-audit",
        CONFIG.as_posix(),
        "--execute",
    )
    payload = json.loads(executed.stdout)

    assert executed.returncode == 0
    assert payload["status"] == "completed"
    assert payload["assessment"] == "insufficient_evidence"
    assert payload["network_called"] is False
    assert set(payload["written"]) == {
        "data/processed/retrieval_reproducibility_audit_summary_v1.json",
        "outputs/v2_5_retrieval_reproducibility/battery_tracked_retrieval_evidence_v1.json",
        "outputs/v2_5_retrieval_reproducibility/materials_project_tracked_retrieval_evidence_v1.json",
    }
    assert all((root / path).is_file() for path in payload["written"])
    assert not (root / "data/raw").exists()


def test_run_is_deterministic_and_validate_accepts_summary_and_local_evidence(tmp_path):
    root = _fixture_repo(tmp_path)
    command = (
        "run-retrieval-reproducibility-audit",
        CONFIG.as_posix(),
        "--execute",
    )
    first = _cli(root, *command)
    first_payload = json.loads(first.stdout)
    first_summary = (
        root / "data/processed/retrieval_reproducibility_audit_summary_v1.json"
    ).read_bytes()
    first_evidence = (
        root
        / "outputs/v2_5_retrieval_reproducibility/battery_tracked_retrieval_evidence_v1.json"
    ).read_bytes()
    second = _cli(root, *command)
    second_payload = json.loads(second.stdout)

    assert first.returncode == second.returncode == 0
    assert first_payload["summary"] == second_payload["summary"]
    assert (
        root / "data/processed/retrieval_reproducibility_audit_summary_v1.json"
    ).read_bytes() == first_summary
    assert (
        root
        / "outputs/v2_5_retrieval_reproducibility/battery_tracked_retrieval_evidence_v1.json"
    ).read_bytes() == first_evidence

    summary = _cli(
        root,
        "validate-retrieval-reproducibility-audit",
        "data/processed/retrieval_reproducibility_audit_summary_v1.json",
    )
    evidence = _cli(
        root,
        "validate-retrieval-reproducibility-audit",
        "outputs/v2_5_retrieval_reproducibility/battery_tracked_retrieval_evidence_v1.json",
    )
    assert summary.returncode == evidence.returncode == 0
    assert json.loads(summary.stdout)["record_type"] == "summary"
    assert json.loads(evidence.stdout)["record_type"] == "evidence"


def test_cli_rejects_invalid_config_and_tampered_result(tmp_path):
    root = _fixture_repo(tmp_path)
    invalid_config = json.loads((root / CONFIG).read_text(encoding="utf-8"))
    invalid_config["module_path"] = "user.module"
    invalid_path = root / "configs/examples/invalid_retrieval.json"
    invalid_path.write_text(json.dumps(invalid_config), encoding="utf-8")
    invalid = _cli(
        root,
        "preview-retrieval-reproducibility-audit",
        invalid_path.relative_to(root).as_posix(),
    )

    assert invalid.returncode != 0
    assert json.loads(invalid.stdout)["status"] == "invalid"

    executed = _cli(root, *(
        "run-retrieval-reproducibility-audit",
        CONFIG.as_posix(),
        "--execute",
    ))
    assert executed.returncode == 0
    result_path = (
        root
        / "outputs/v2_5_retrieval_reproducibility/battery_tracked_retrieval_evidence_v1.json"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["record_checksum_sha256"] = "0" * 64
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    validation = _cli(
        root,
        "validate-retrieval-reproducibility-audit",
        result_path.relative_to(root).as_posix(),
    )

    assert validation.returncode != 0
    assert "checksum mismatch" in json.loads(validation.stdout)["error"]
