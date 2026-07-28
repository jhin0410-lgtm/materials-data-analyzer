from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "verify-v2-7-0-publication.yml"
PUBLICATION = PROJECT_ROOT / "release" / "v2.7.0-publication.json"


def test_publication_record_pins_existing_release() -> None:
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))

    assert publication["publication_status"] == "published_and_verified"
    assert publication["tag_name"] == "v2.7.0"
    assert publication["target_commit"] == (
        "2d003aecede89aacc25cdb246bf9cc6adec19bf9"
    )
    assert publication["release_title"] == (
        "v2.7.0 - Evidence-Line Closeout and Cross-Repository Integration"
    )
    assert publication["expected_draft"] is False
    assert publication["expected_prerelease"] is False
    assert publication["expected_latest"] is True
    assert publication["release_body_exact_match"] is True


def test_verification_requires_annotated_tag_type_target_and_message() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for token in (
        "git cat-file -t",
        '== "tag"',
        "git rev-parse",
        "^{commit}",
        "git for-each-ref",
        "%(contents)",
        "tag_object_type",
        "tag_target_commit",
        "tag_annotation",
        '"annotated_tag_verified": True',
    ):
        assert token in text


def test_verification_remains_read_only_and_preserves_boundaries() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))

    assert "permissions:\n  contents: read" in text
    assert "git push" not in text
    assert "gh release create" not in text
    assert publication["package_publication_performed"] is False
    assert publication["model_training_performed"] is False
    assert publication["metric_recomputation_performed"] is False
    assert publication["optimization_performed"] is False
    assert publication["scientific_claim_promoted"] is False
