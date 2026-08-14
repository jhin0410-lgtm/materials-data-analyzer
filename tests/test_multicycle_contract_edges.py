from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.multicycle import (
    MultiCycleResearchError,
    load_request_queue,
    run_bounded_multicycle,
)


def test_request_queue_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    request_sha = hashlib.sha256(request.read_bytes()).hexdigest()
    queue = tmp_path / "queue.json"
    queue.write_text(
        "{" 
        '"schema_version":"1.0",'
        '"queue_id":"q1",'
        '"queue_id":"q2",'
        '"adapter_id":"nasa-battery",'
        '"requests":[{'
        '"request_id":"r1",'
        '"path":"request.json",'
        f'"sha256":"{request_sha}",'
        '"expected_action_type":"audit",'
        '"expected_action_version":"1.0"'
        "}]}"
        ,
        encoding="utf-8",
    )

    with pytest.raises(MultiCycleResearchError, match="duplicate JSON key"):
        load_request_queue(queue)


def test_cycle_limit_above_hard_boundary_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(MultiCycleResearchError, match="max_cycles must be an integer from 1 to 32"):
        run_bounded_multicycle(
            "materials-project-external-source",
            repository_root=tmp_path,
            max_cycles=33,
        )


def test_request_queue_adapter_identity_must_match_invocation(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"action_type": "audit"}), encoding="utf-8")
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "queue_id": "q",
                "adapter_id": "nasa-battery",
                "requests": [
                    {
                        "request_id": "r",
                        "path": "request.json",
                        "sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
                        "expected_action_type": "audit",
                        "expected_action_version": "1.0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MultiCycleResearchError, match="adapter_id does not match"):
        run_bounded_multicycle(
            "materials-project-external-source",
            repository_root=tmp_path,
            request_queue_path=queue,
        )
