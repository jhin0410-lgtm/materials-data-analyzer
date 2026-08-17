from __future__ import annotations

import hashlib

from materials_data_analyzer.research_loop.public_data_acquisition import (
    AUTO,
    REVIEW_REQUIRED,
    plan_public_acquisition_queue,
)


def _candidate(candidate_id: str, artifact_size: int) -> dict[str, object]:
    metadata = candidate_id.encode("utf-8")
    artifact = bytes([len(candidate_id) % 251]) * artifact_size
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "evidence_role": "source_artifact",
        "source_system": "Example Public Repository",
        "source_version": "1.0",
        "metadata_endpoint": "https://data.example.org/metadata.json",
        "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
        "artifact_path": f"raw/{candidate_id}.bin",
        "retrieval_endpoint": f"https://data.example.org/{candidate_id}.bin",
        "expected_sha256": hashlib.sha256(artifact).hexdigest(),
        "expected_size_bytes": artifact_size,
        "allowed_hosts": ["data.example.org"],
        "access": {
            "publicly_accessible": True,
            "authentication_required": False,
            "interactive_acceptance_required": False,
            "known_automation_prohibited": False,
            "rights_status": "public_repository",
        },
        "limitations": ["Scientific validity requires downstream intake."],
    }


def test_total_download_budget_routes_later_safe_files_to_review() -> None:
    candidates = [
        _candidate("first", 6),
        _candidate("second", 6),
        _candidate("third", 3),
    ]

    queue = plan_public_acquisition_queue(
        candidates,
        max_auto_bytes=10,
        max_total_auto_bytes=10,
    )

    assert queue["auto_bytes"] == 9
    assert [item["candidate_id"] for item in queue["auto"]] == ["first", "third"]
    assert queue["auto"][0]["decision"] == AUTO
    assert queue["review_required"] == [
        {
            "candidate_id": "second",
            "decision": REVIEW_REQUIRED,
            "reason_codes": ["automatic_batch_budget_exceeded"],
        }
    ]
