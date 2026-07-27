from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-v2-7-0-release.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_publication_workflow_is_exact_and_main_only() -> None:
    text = _workflow_text()

    assert "name: Publish v2.7.0 GitHub Release" in text
    assert "RELEASE_TAG: v2.7.0" in text
    assert "RELEASE_VERSION: 2.7.0" in text
    assert "github.event_name != 'pull_request'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in text
    assert '--target "${GITHUB_SHA}"' in text
    assert "--verify-tag" in text
    assert 'git tag -a "${RELEASE_TAG}" "${GITHUB_SHA}"' in text
    assert 'test "${existing_tag_commit}" = "${GITHUB_SHA}"' in text


def test_release_publication_workflow_validates_metadata_and_evidence() -> None:
    text = _workflow_text()

    required_inputs = (
        "PUBLIC_RELEASE_VERSION",
        "src/platform_core/version.py",
        "CITATION.cff",
        "CHANGELOG.md",
        "docs/releases/V2_7_0.md",
        "audit_v2_7_public_release_candidate.py",
        "battery_v2_6_external_evidence_line_closeout",
        "run_representative_process_characterization_workflow.py",
        "audit_cross_repository_release_readiness.py",
        "consume_characterization_handoff_bundle.py",
        "python -m pytest -q",
    )
    for expected in required_inputs:
        assert expected in text

    assert "7242594f775b8dbe651a6131bb1b39b5f60c62cd" in text
    assert "ca7242331d3aab7d5d4999df297ccc1a8b011934" in text
    assert "not_ready_for_predictive_or_causal_modeling" in text
    assert '"model_trained"]["' not in text
    assert '"model_trained"] is False' in text
    assert '"optimization_performed"] is False' in text


def test_release_assets_and_checksums_are_explicit() -> None:
    text = _workflow_text()

    expected_assets = (
        "materials-data-analyzer-v2.7.0-promotion-evidence.zip",
        "materials-data-analyzer-v2.7.0-release-readiness.zip",
        "materials-data-analyzer-v2.7.0-nist-cross-repository-evidence.zip",
        "materials-data-analyzer-v2.7.0-pytest-log.zip",
        "SHA256SUMS.txt",
    )
    for asset in expected_assets:
        assert asset in text

    assert "sha256sum ./*.zip > SHA256SUMS.txt" in text
    assert "gh release create" in text
    assert "gh release view" in text
    assert "expected_assets <= actual_assets" in text
