from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.multicycle as multicycle


ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_queue(
    tmp_path: Path,
    requests: list[tuple[str, str, str]],
) -> Path:
    payload = []
    for index, (filename, action_type, action_version) in enumerate(requests, start=1):
        request = tmp_path / filename
        request.write_text(json.dumps({"request": index}), encoding="utf-8")
        payload.append(
            {
                "request_id": f"request-{index}",
                "path": filename,
                "sha256": _sha(request),
                "expected_action_type": action_type,
                "expected_action_version": action_version,
            }
        )
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "queue_id": "queue-1",
                "adapter_id": "nasa-battery",
                "requests": payload,
            }
        ),
        encoding="utf-8",
    )
    return queue


def _state(action_type: str | None, *, marker: str) -> dict[str, object]:
    selected = None
    if action_type is not None:
        selected = {
            "action_type": action_type,
            "action_version": "1.0",
        }
    return {
        "adapter_id": "nasa-battery",
        "current_blocker": {"code": marker, "summary": marker},
        "evidence_gap": {"status": marker, "requirements": [marker]},
        "selected_action": selected,
        "stop_state": {"status": "continue", "selection_status": marker},
        "budget": {"actions_remaining": 5, "cost_units_remaining": 20},
        "evidence_bindings": [{"role": "research_ledger", "sha256": marker}],
    }


def _probe(action_type: str, *, marker: str) -> dict[str, object]:
    selected = {"action_type": action_type, "action_version": "1.0"}
    return {
        "cycle_status": "explicit_request_required",
        "before_planning_state": _state(action_type, marker=marker),
        "before_transition": {"transition_type": "action_pending_authorization"},
        "authorization": {
            "authorization_status": "ready_for_explicit_execution_request",
            "selected_action": selected,
        },
    }


def _executed(
    action_type: str,
    *,
    before_marker: str,
    after_marker: str,
    after_action: str | None,
    after_transition: str,
) -> dict[str, object]:
    return {
        "cycle_status": "one_action_executed",
        "before_planning_state": _state(action_type, marker=before_marker),
        "execution": {
            "execution_status": "completed",
            "action_type": action_type,
        },
        "after_planning_state": _state(after_action, marker=after_marker),
        "after_transition": {"transition_type": after_transition},
    }


def test_queue_checksum_mismatch_fails_before_any_cycle(tmp_path: Path) -> None:
    queue = _write_queue(tmp_path, [("r1.json", "audit", "1.0")])
    payload = json.loads(queue.read_text(encoding="utf-8"))
    payload["requests"][0]["sha256"] = "f" * 64
    queue.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(multicycle.MultiCycleResearchError, match="checksum mismatch"):
        multicycle.run_bounded_multicycle(
            "nasa-battery",
            repository_root=tmp_path,
            request_queue_path=queue,
        )


def test_request_path_cannot_escape_request_root(tmp_path: Path) -> None:
    root = tmp_path / "requests"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    queue = root / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "queue_id": "q",
                "adapter_id": "nasa-battery",
                "requests": [
                    {
                        "request_id": "r",
                        "path": "../outside.json",
                        "sha256": _sha(outside),
                        "expected_action_type": "audit",
                        "expected_action_version": "1.0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(multicycle.MultiCycleResearchError, match="escapes request_root"):
        multicycle.load_request_queue(queue)


def test_no_queue_never_auto_generates_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        multicycle,
        "run_research_cycle",
        lambda *a, **k: _probe("audit", marker="before"),
    )

    result = multicycle.run_bounded_multicycle(
        "nasa-battery",
        repository_root=tmp_path,
    )

    assert result["program_status"] == "predeclared_request_required"
    assert result["actions_executed"] == 0
    assert result["requests_consumed"] == 0
    assert result["autonomy_boundary"]["automatic_request_generation_available"] is False


def test_two_predeclared_requests_execute_one_per_cycle_then_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = _write_queue(
        tmp_path,
        [
            ("r1.json", "protocol_stratification", "1.0"),
            ("r2.json", "target_reference_sensitivity", "1.0"),
        ],
    )
    calls = iter(
        [
            _probe("protocol_stratification", marker="state-0"),
            _executed(
                "protocol_stratification",
                before_marker="state-0",
                after_marker="state-1",
                after_action="target_reference_sensitivity",
                after_transition="action_pending_authorization",
            ),
            _probe("target_reference_sensitivity", marker="state-1"),
            _executed(
                "target_reference_sensitivity",
                before_marker="state-1",
                after_marker="state-2",
                after_action=None,
                after_transition="stop_current_scope",
            ),
        ]
    )
    monkeypatch.setattr(multicycle, "run_research_cycle", lambda *a, **k: next(calls))

    result = multicycle.run_bounded_multicycle(
        "nasa-battery",
        repository_root=tmp_path,
        request_queue_path=queue,
        max_cycles=5,
    )

    assert result["program_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 2
    assert result["requests_consumed"] == 2
    assert result["requests_remaining"] == 0
    assert len(result["cycles"]) == 2
    assert [item["request"]["request_id"] for item in result["cycles"]] == [
        "request-1",
        "request-2",
    ]


def test_request_queue_action_mismatch_stops_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = _write_queue(tmp_path, [("r1.json", "target_reference_sensitivity", "1.0")])
    calls = 0

    def fake_cycle(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _probe("protocol_stratification", marker="state-0")

    monkeypatch.setattr(multicycle, "run_research_cycle", fake_cycle)

    with pytest.raises(multicycle.MultiCycleResearchError, match="does not match"):
        multicycle.run_bounded_multicycle(
            "nasa-battery",
            repository_root=tmp_path,
            request_queue_path=queue,
        )
    assert calls == 1


def test_no_verified_state_progress_stops_repetition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = _write_queue(tmp_path, [("r1.json", "audit", "1.0")])
    calls = iter(
        [
            _probe("audit", marker="same"),
            _executed(
                "audit",
                before_marker="same",
                after_marker="same",
                after_action="audit",
                after_transition="action_pending_authorization",
            ),
        ]
    )
    monkeypatch.setattr(multicycle, "run_research_cycle", lambda *a, **k: next(calls))

    result = multicycle.run_bounded_multicycle(
        "nasa-battery",
        repository_root=tmp_path,
        request_queue_path=queue,
    )

    assert result["program_status"] == "stopped_no_verified_state_progress"
    assert result["actions_executed"] == 1


def test_terminal_probe_never_consumes_predeclared_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = _write_queue(tmp_path, [("r1.json", "audit", "1.0")])
    terminal = {
        "cycle_status": "stopped_current_scope",
        "before_planning_state": _state(None, marker="terminal"),
        "before_transition": {"transition_type": "stop_current_scope"},
        "authorization": None,
    }
    monkeypatch.setattr(multicycle, "run_research_cycle", lambda *a, **k: terminal)

    result = multicycle.run_bounded_multicycle(
        "nasa-battery",
        repository_root=tmp_path,
        request_queue_path=queue,
    )

    assert result["program_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 0
    assert result["requests_consumed"] == 0
    assert result["requests_remaining"] == 1


def test_max_cycles_is_hard_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = _write_queue(
        tmp_path,
        [
            ("r1.json", "a1", "1.0"),
            ("r2.json", "a2", "1.0"),
        ],
    )
    calls = iter(
        [
            _probe("a1", marker="s0"),
            _executed(
                "a1",
                before_marker="s0",
                after_marker="s1",
                after_action="a2",
                after_transition="action_pending_authorization",
            ),
        ]
    )
    monkeypatch.setattr(multicycle, "run_research_cycle", lambda *a, **k: next(calls))

    result = multicycle.run_bounded_multicycle(
        "nasa-battery",
        repository_root=tmp_path,
        request_queue_path=queue,
        max_cycles=1,
    )

    assert result["program_status"] == "max_cycles_reached"
    assert result["actions_executed"] == 1
    assert result["requests_remaining"] == 1


def test_current_closed_materials_project_scope_stops_without_queue() -> None:
    result = multicycle.run_bounded_multicycle(
        "materials-project-external-source",
        repository_root=ROOT,
    )

    assert result["program_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 0
    assert result["cycles_started"] == 1
