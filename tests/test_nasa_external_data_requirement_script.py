from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_nasa_external_data_requirement_action.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_nasa_external_data_requirement_action",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_execute_routes_through_common_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    captured: dict[str, object] = {}

    def fake_execute(
        action_domain: str,
        *,
        repository_root: str,
        research_run: str,
        action_registry_path: str,
        request_path: str,
    ) -> dict[str, object]:
        captured.update(
            {
                "action_domain": action_domain,
                "repository_root": repository_root,
                "research_run": research_run,
                "action_registry_path": action_registry_path,
                "request_path": request_path,
            }
        )
        return {"execution_status": "completed", "action_id": "NASA-EXTERNAL-001"}

    monkeypatch.setattr(script, "execute_authorized_action", fake_execute)

    assert (
        script.main(
            [
                "execute",
                "--repository-root",
                "repo",
                "--run",
                "research",
                "--registry",
                "registry.json",
                "--request",
                "request.json",
            ]
        )
        == 0
    )
    assert captured == {
        "action_domain": "nasa-battery",
        "repository_root": "repo",
        "research_run": "research",
        "action_registry_path": "registry.json",
        "request_path": "request.json",
    }
    assert json.loads(capsys.readouterr().out)["execution_status"] == "completed"


def test_execute_requires_full_authorization_context() -> None:
    script = _load_script()

    with pytest.raises(SystemExit) as exc_info:
        script.main(["execute", "--request", "request.json"])

    assert exc_info.value.code == 2


def test_verify_does_not_execute_an_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()

    def fail_execute(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("verification must not execute an action")

    monkeypatch.setattr(script, "execute_authorized_action", fail_execute)
    monkeypatch.setattr(
        script,
        "verify_nasa_external_data_requirement_report",
        lambda report: {"valid": True, "report": report},
    )

    assert script.main(["verify", "--report", "action_result.json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "report": "action_result.json",
        "valid": True,
    }


def test_script_does_not_import_raw_executor() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "execute_nasa_external_data_requirement_action" not in source
    assert "execute_authorized_action" in source
