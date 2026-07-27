from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-v2-7-0.yml"
REQUEST = PROJECT_ROOT / "release" / "v2.7.0-publish-request.json"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


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


def test_workflow_verifies_annotated_tag_contract() -> None:
    text = _workflow_text()

    required_tokens = (
        "release_title",
        "v2.7.0 - Evidence-Line Closeout and Cross-Repository Integration",
        "git cat-file -t",
        "refs/tags/${TAG}",
        "git rev-parse",
        "${TAG}^{commit}",
        "git for-each-ref",
        "%(contents)",
        "EXISTING_ANNOTATION",
        "tag_object_type",
        'tag_annotation == request["release_title"]',
    )
    for token in required_tokens:
        assert token in text


def test_workflow_verifies_published_body_and_latest_release() -> None:
    text = _workflow_text()

    required_tokens = (
        "isDraft,isPrerelease,url,body",
        "releases/latest",
        'published_notes = release["body"]',
        "normalized(published_notes) == normalized(expected_notes)",
        'latest_tag == request["tag_name"]',
        '"release_body_verified": True',
        '"latest_status_verified": True',
        '"published_body_sha256"',
    )
    for token in required_tokens:
        assert token in text


def test_workflow_limits_write_permission_to_main_publication_job() -> None:
    text = _workflow_text()

    assert "permissions:\n  contents: read" in text
    assert "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'" in text
    assert "permissions:\n      contents: write" in text


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
