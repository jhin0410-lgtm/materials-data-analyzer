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


def test_workflow_verifies_annotated_tag_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '"release_title": (' in text
    assert 'git cat-file -t "refs/tags/${TAG}"' in text
    assert 'git rev-parse "${TAG}^{commit}"' in text
    assert "git for-each-ref --format='%(contents)'" in text
    assert 'test "${EXISTING_ANNOTATION}" = "${TITLE}"' in text
    assert 'assert tag_object_type == "tag"' in text
    assert 'assert tag_annotation == request["release_title"]' in text


def test_workflow_verifies_published_body_and_latest_release() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "--json tagName,name,isDraft,isPrerelease,url,body" in text
    assert 'gh api "repos/${GITHUB_REPOSITORY}/releases/latest"' in text
    assert 'published_notes = release["body"]' in text
    assert "assert normalized(published_notes) == normalized(expected_notes)" in text
    assert 'assert latest_tag == request["tag_name"]' in text
    assert '"release_body_verified": True' in text
    assert '"latest_status_verified": True' in text


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
