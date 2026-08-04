from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RWGS_WORKFLOW = ROOT / ".github" / "workflows" / "cross-repository-public-rwgs.yml"
READINESS_WORKFLOW = (
    ROOT / ".github" / "workflows" / "cross-repository-release-readiness.yml"
)
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _workflow_contract(path: Path) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8")
    commit_match = re.search(r"^  MCA_COMMIT: ([0-9a-f]{40})$", text, re.MULTILINE)
    version_match = re.search(r"^  MCA_VERSION: ([0-9]+\.[0-9]+\.[0-9]+)$", text, re.MULTILINE)
    assert commit_match is not None
    assert version_match is not None
    return text, commit_match.group(1), version_match.group(1)


def test_rwgs_and_release_readiness_pin_one_current_characterization_contract() -> None:
    rwgs, rwgs_commit, rwgs_version = _workflow_contract(RWGS_WORKFLOW)
    readiness, readiness_commit, readiness_version = _workflow_contract(
        READINESS_WORKFLOW
    )

    assert rwgs_commit == readiness_commit
    assert rwgs_version == readiness_version == "0.11.0"
    assert "ref: ${{ env.MCA_COMMIT }}" in rwgs
    assert "ref: ${{ env.MCA_COMMIT }}" in readiness
    assert 'test "$(git rev-parse HEAD)" = "${MCA_COMMIT}"' in rwgs
    assert 'test "$(git rev-parse HEAD)" = "${MCA_COMMIT}"' in readiness


def test_rwgs_runs_producer_validation_and_installed_consumer() -> None:
    text = RWGS_WORKFLOW.read_text(encoding="utf-8")

    assert "mca validate-handoff" in text
    assert "--bundle materials-characterization-analyzer/outputs/public-rwgs-case/result/handoff_bundle" in text
    assert "mda-characterization-import" in text
    assert "python materials-data-analyzer/scripts/consume_characterization_handoff_bundle.py" not in text
    assert 'summary["producer"]["software_versions"] == ["0.11.0"]' in text
    assert "handoff_bundle_validation_summary.json" in text
    assert "handoff_bundle_validation_report.md" in text
    assert "handoff_bundle_validation_artifact_manifest.json" in text
    assert "sem_quantitative_segmentation_status" in text
    assert "blocked_method_mismatch" in text
    assert "eds_unexpected_elements" in text
    assert '== "Ni"' in text


def test_packaged_characterization_import_entry_point_is_stable() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["scripts"]["mda-characterization-import"] == (
        "materials_data_analyzer.characterization_import_cli:main"
    )


def test_installed_package_ci_or_real_workflow_executes_new_command() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    rwgs = RWGS_WORKFLOW.read_text(encoding="utf-8")

    assert "mda-characterization-import" in ci or "mda-characterization-import" in rwgs
