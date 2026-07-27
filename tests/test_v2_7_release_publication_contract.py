from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-v2-7-0.yml"
REQUEST = PROJECT_ROOT / "release" / "v2.7.0-publish-request.json"


def test_publish_request_pins_public_release_identity() -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    assert request["schema_version"] == "1.0"
    assert request["release_version"] == "2.7.0"
    assert request["tag_name"] == "v2.7.0"
    assert request["target_commit"] == "2d003aecede89aacc25cdb246bf9cc6adec19bf9"
    assert request["release_title"] == (
        "v2.7.0 - Evidence-Line Closeout and Cross-Repository Integration"
    )
    assert request["release_notes_path"] == "docs/releases/V2_7_0.md"
    assert request["draft"] is False
    assert request["prerelease"] is False
    assert request["mark_latest"] is True
    assert request["package_publication_authorized"] is False


def test_workflow_contains_fail_closed_publication_guards() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for token in (
        "contents: read",
        "contents: write",
        "refs/heads/main",
        "git cat-file -t",
        "git rev-parse",
        "git for-each-ref",
        "releases/latest",
        "release_body_verified",
        "latest_status_verified",
        "published_body_sha256",
    ):
        assert token in text


def test_workflow_preserves_scientific_boundaries() -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    assert request["scientific_boundary"] == {
        "ridge_generalization": "unsupported",
        "predictive_validation_readiness": "not_ready",
        "battery_evidence_line_status": "inconclusive",
        "process_characterization_status": "diagnostic",
        "model_training_authorized": False,
        "optimization_authorized": False,
        "engineering_release_claim_authorized": False,
    }
