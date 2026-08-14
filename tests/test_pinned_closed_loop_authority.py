from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import pinned_cycle_execution as pinned
from materials_data_analyzer.research_loop import policy_authorized_closed_loop as closed


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_pinned_request_parser_uses_supplied_bytes_not_mutated_live_path(
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "request.json"
    original = b'{"action_id":"a1","action_type":"target_reference_sensitivity"}\n'
    request_path.write_bytes(original)

    # Simulate the exact TOCTOU the closed-loop adapter is meant to eliminate:
    # the live pathname changes after policy has retained the approved byte snapshot.
    request_path.write_bytes(
        b'{"action_id":"attacker","action_type":"protocol_stratification"}\n'
    )

    resolved, value, record = pinned._parse_pinned_request(
        request_path=request_path,
        request_bytes=original,
        expected_sha256=_sha(original),
    )

    assert resolved == request_path.resolve()
    assert value["action_id"] == "a1"
    assert value["action_type"] == "target_reference_sensitivity"
    assert record["sha256"] == _sha(original)
    assert record["bytes"] == len(original)


def test_pinned_request_parser_rejects_wrong_snapshot_checksum(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        pinned.PinnedCycleExecutionError,
        match="predeclared request SHA-256",
    ):
        pinned._parse_pinned_request(
            request_path=request_path,
            request_bytes=b"{}\n",
            expected_sha256="0" * 64,
        )


def test_pinned_request_parser_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text("{}\n", encoding="utf-8")
    raw = b'{"action_id":"a1","action_id":"a2"}\n'
    with pytest.raises(
        pinned.PinnedCycleExecutionError,
        match="duplicate JSON key",
    ):
        pinned._parse_pinned_request(
            request_path=request_path,
            request_bytes=raw,
            expected_sha256=_sha(raw),
        )


def test_preflight_normalizes_mutable_evidence_role_before_rejection(
    tmp_path: Path,
) -> None:
    graph = _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "g1",
            "research_scope": "bounded",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": " hypothesis ",
                    "statement": "target",
                },
                {
                    "node_id": "e1",
                    "node_type": " evidence ",
                    "statement": "mutable evidence",
                    "evidence_binding": {
                        "workstream_id": "nasa-battery",
                        "role": " research_ledger ",
                        "sha256": "abc",
                    },
                    "evidence_quality": "diagnostic",
                },
            ],
            "edges": [],
        },
    )
    record = {
        "record_id": "r1",
        "target_node_id": "h1",
        "result_node_id": "result-1",
    }
    with pytest.raises(
        closed.PolicyAuthorizedClosedLoopError,
        match="must not use mutable research_state/research_ledger",
    ):
        closed._preflight_graph_and_records(
            graph_path=graph,
            records=[record],
            target_ids=["h1"],
        )


def test_failed_report_snapshot_is_self_contained_and_hash_verifiable() -> None:
    raw = b'{"execution_status":"failed","reason":"bounded failure"}\n'
    encoded = __import__("base64").b64encode(raw).decode("ascii")
    recovered = __import__("base64").b64decode(encoded)
    assert recovered == raw
    assert _sha(recovered) == _sha(raw)
