from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_transport_recovery as recovery,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_weaver_extension as weaver,
)


def _kwargs(root: Path, *, max_cycles: int) -> dict[str, Any]:
    return {
        "repository_root": root,
        "mission_path": root / "mission.json",
        "expected_mission_sha256": "a" * 64,
        "output_root": root,
        "max_cycles": max_cycles,
    }


def test_twelve_cycle_path_preserves_reviewed_reference_chain_seam(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}

    def fake_reference(**kwargs: Any) -> dict[str, Any]:
        observed.update(kwargs)
        return {"runner": "reference", "max_cycles": kwargs["max_cycles"]}

    monkeypatch.setattr(recovery, "run_reference_chain_production", fake_reference)
    result = recovery.run_autonomous_production(**_kwargs(tmp_path, max_cycles=12))
    assert result == {"runner": "reference", "max_cycles": 12}
    assert observed["repository_root"] == tmp_path.resolve()


def test_cycles_thirteen_and_fourteen_route_to_weaver_without_replacing_base_seam(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    weaver_calls = 0

    def forbidden_reference(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("max_cycles > 12 must route through Weaver extension")

    def fake_weaver(**kwargs: Any) -> dict[str, Any]:
        nonlocal weaver_calls
        weaver_calls += 1
        return {"runner": "weaver", "max_cycles": kwargs["max_cycles"]}

    monkeypatch.setattr(recovery, "run_reference_chain_production", forbidden_reference)
    monkeypatch.setattr(weaver, "run_autonomous_production", fake_weaver)
    result = recovery.run_autonomous_production(**_kwargs(tmp_path, max_cycles=14))
    assert result == {"runner": "weaver", "max_cycles": 14}
    assert weaver_calls == 1


def test_boolean_cycle_bound_does_not_accidentally_select_weaver(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_reference(**kwargs: Any) -> dict[str, Any]:
        return {"runner": "reference", "max_cycles": kwargs["max_cycles"]}

    def forbidden_weaver(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("bool max_cycles must not widen routing authority")

    monkeypatch.setattr(recovery, "run_reference_chain_production", fake_reference)
    monkeypatch.setattr(weaver, "run_autonomous_production", forbidden_weaver)
    result = recovery.run_autonomous_production(**_kwargs(tmp_path, max_cycles=True))
    assert result["runner"] == "reference"
