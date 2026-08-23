from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer import research_program_cli
from materials_data_analyzer.research_loop import authenticated_request_compiler
from materials_data_analyzer.research_loop import autonomous_production_driver
from materials_data_analyzer.research_loop import in625_network_policy


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPOSITORY_ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
NETWORK_POLICY = REPOSITORY_ROOT / "configs/research/in625_zenodo_network_acquisition_policy.v1.json"
DELEGATION_POLICY = (
    REPOSITORY_ROOT
    / "configs/research/in625_external_evidence_request_delegation_policy.v1.json"
)
SOURCE_CONFIG = (
    REPOSITORY_ROOT
    / "configs/research/in625_zenodo_20503603_verified_source.v1.json"
)
IN625_REGISTRY = (
    REPOSITORY_ROOT
    / "configs/research/in625_external_evidence_action_registry.v1.json"
)
EXPECTED_MISSION_SHA256 = (
    "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
)


def test_public_cli_production_pin_matches_exact_mission_bytes() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == EXPECTED_MISSION_SHA256
    assert (
        research_program_cli._AUTONOMOUS_PRODUCTION_MISSION_SHA256
        == EXPECTED_MISSION_SHA256
    )


def test_run_autonomous_parser_needs_no_pre_authored_request_queue() -> None:
    args = research_program_cli.build_parser().parse_args(["run-autonomous"])
    assert args.command == "run-autonomous"
    assert args.repository_root == Path(".")
    assert args.max_cycles == 12
    assert not hasattr(args, "request_queue")


@pytest.mark.parametrize("flag", ["--request-queue", "--result", "--success"])
def test_run_autonomous_rejects_caller_authored_control_inputs(flag: str) -> None:
    with pytest.raises(SystemExit):
        research_program_cli.build_parser().parse_args(
            ["run-autonomous", flag, "forged.json"]
        )


def test_run_autonomous_uses_independent_production_pin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_autonomous_production(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "bounded-test"}

    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.setattr(
        research_program_cli,
        "run_autonomous_production",
        fake_run_autonomous_production,
    )
    args = research_program_cli.build_parser().parse_args(
        ["run-autonomous", "--output", str(tmp_path.name)]
    )
    result = research_program_cli._run(args)

    assert result == {"status": "bounded-test"}
    assert captured["repository_root"] == REPOSITORY_ROOT.resolve()
    assert captured["mission_path"] == MISSION.resolve()
    assert captured["expected_mission_sha256"] == EXPECTED_MISSION_SHA256
    assert captured["max_cycles"] == 12


def test_driver_rejects_untrusted_mission_root_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_called = False

    def forbidden_network(*args: object, **kwargs: object) -> bytes:
        nonlocal network_called
        network_called = True
        raise AssertionError("network must not be reached under a bad mission root")

    monkeypatch.setattr(
        autonomous_production_driver,
        "_exact_zenodo_get",
        forbidden_network,
    )
    with pytest.raises(
        autonomous_production_driver.AutonomousProductionDriverError,
        match="mission bytes do not match externally supplied expected mission SHA-256",
    ):
        autonomous_production_driver.run_autonomous_production(
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256="0" * 64,
            output_root=Path("outputs") / "must-not-be-created-bad-mission",
        )
    assert network_called is False


@pytest.mark.parametrize("max_cycles", [0, 9, True])
def test_driver_rejects_cycle_budget_outside_finite_range_before_network(
    monkeypatch: pytest.MonkeyPatch,
    max_cycles: object,
) -> None:
    network_called = False

    def forbidden_network(*args: object, **kwargs: object) -> bytes:
        nonlocal network_called
        network_called = True
        raise AssertionError("network must not be reached under invalid cycle budget")

    monkeypatch.setattr(
        autonomous_production_driver,
        "_exact_zenodo_get",
        forbidden_network,
    )
    with pytest.raises(
        autonomous_production_driver.AutonomousProductionDriverError,
        match="max_cycles must be an integer from 1 to 8",
    ):
        autonomous_production_driver.run_autonomous_production(
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256=EXPECTED_MISSION_SHA256,
            output_root=Path("outputs") / "must-not-be-created-cycle-budget",
            max_cycles=max_cycles,  # type: ignore[arg-type]
        )
    assert network_called is False


def test_driver_rejects_non_zenodo_target_before_urlopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urlopen_called = False

    def forbidden_urlopen(*args: object, **kwargs: object) -> object:
        nonlocal urlopen_called
        urlopen_called = True
        raise AssertionError("urlopen must not be called")

    monkeypatch.setattr(
        autonomous_production_driver.urllib.request,
        "urlopen",
        forbidden_urlopen,
    )
    with pytest.raises(
        autonomous_production_driver.AutonomousProductionDriverError,
        match="network target left exact Zenodo HTTPS authority",
    ):
        autonomous_production_driver._exact_zenodo_get(
            "https://example.com/api/records/20503603"
        )
    assert urlopen_called is False


def test_comparability_is_registered_but_geometry_acquisition_is_new_frontier() -> None:
    assert (
        "reviewed_physical_comparability_assessment"
        in autonomous_production_driver._PRODUCTION_CAPABILITIES
    )
    assert (
        "nist_mds2_2923_geometry_evidence_acquisition"
        not in autonomous_production_driver._PRODUCTION_CAPABILITIES
    )


def test_bounded_successor_stop_never_claims_global_evidence_absence() -> None:
    stop = autonomous_production_driver._bounded_successor_stop(
        {
            "next_action": {
                "action_class": "nist_mds2_2923_geometry_evidence_acquisition"
            }
        }
    )
    assert (
        stop["reason_code"]
        == "registered_capability_unavailable_for_current_next_action"
    )
    assert stop["requested_action_class"] == (
        "nist_mds2_2923_geometry_evidence_acquisition"
    )
    assert stop["global_evidence_unavailability_claimed"] is False
    assert stop["positive_scientific_closeout"] is False
    assert stop["scientific_status_changed"] is False


def test_bounded_stop_rejects_an_action_that_has_a_registered_handler() -> None:
    with pytest.raises(
        autonomous_production_driver.AutonomousProductionDriverError,
        match="implemented production capability",
    ):
        autonomous_production_driver._bounded_successor_stop(
            {
                "next_action": {
                    "action_class": "reviewed_physical_comparability_assessment"
                }
            }
        )


def _write_reauthorized_network_fixture(
    tmp_path: Path,
    *,
    mutate_policy: Callable[[dict[str, Any]], None],
    mutate_source: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Path, Path, Path, Path, str]:
    root = tmp_path / "repo"
    config_dir = root / "configs/research"
    config_dir.mkdir(parents=True)

    source = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    if mutate_source is not None:
        mutate_source(source)
    source_bytes = (
        json.dumps(source, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")
    source_path = config_dir / SOURCE_CONFIG.name
    source_path.write_bytes(source_bytes)

    policy_value = json.loads(NETWORK_POLICY.read_text(encoding="utf-8"))
    policy_value["source_binding"]["source_config_sha256"] = hashlib.sha256(
        source_bytes
    ).hexdigest()
    mutate_policy(policy_value)
    policy_bytes = (
        json.dumps(policy_value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")
    policy_path = config_dir / NETWORK_POLICY.name
    policy_path.write_bytes(policy_bytes)

    mission = json.loads(MISSION.read_text(encoding="utf-8"))
    mission["source_trust_policy_pins"][0]["sha256"] = hashlib.sha256(
        policy_bytes
    ).hexdigest()
    mission_bytes = (
        json.dumps(mission, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")
    mission_path = config_dir / MISSION.name
    mission_path.write_bytes(mission_bytes)
    mission_sha = hashlib.sha256(mission_bytes).hexdigest()
    return root, mission_path, policy_path, source_path, mission_sha


def test_network_policy_rejects_widened_host_even_under_new_mission_root(
    tmp_path: Path,
) -> None:
    root, mission_path, policy_path, source_path, mission_sha = (
        _write_reauthorized_network_fixture(
            tmp_path,
            mutate_policy=lambda value: value["transport"].__setitem__(
                "host", "example.com"
            ),
        )
    )
    with pytest.raises(
        in625_network_policy.In625NetworkPolicyError,
        match="network transport authority widened or drifted",
    ):
        in625_network_policy.authenticate_in625_network_policy(
            repository_root=root,
            mission_path=mission_path,
            expected_mission_sha256=mission_sha,
            policy_path=policy_path,
            source_config_path=source_path,
        )


def test_network_policy_rejects_source_identity_substitution_even_if_repinned(
    tmp_path: Path,
) -> None:
    root, mission_path, policy_path, source_path, mission_sha = (
        _write_reauthorized_network_fixture(
            tmp_path,
            mutate_policy=lambda value: None,
            mutate_source=lambda source: source.__setitem__(
                "source_id", "attacker-controlled-source"
            ),
        )
    )
    with pytest.raises(
        in625_network_policy.In625NetworkPolicyError,
        match="source config identity drifted",
    ):
        in625_network_policy.authenticate_in625_network_policy(
            repository_root=root,
            mission_path=mission_path,
            expected_mission_sha256=mission_sha,
            policy_path=policy_path,
            source_config_path=source_path,
        )


def test_request_compiler_rejects_bad_mission_root_before_authorship(
    tmp_path: Path,
) -> None:
    research_run = tmp_path / "research-run"
    research_run.mkdir()
    with pytest.raises(
        authenticated_request_compiler.AuthenticatedRequestCompilerError,
        match="mission bytes do not match supplied expected mission SHA",
    ):
        authenticated_request_compiler.compile_authenticated_machine_request(
            "in625-external-evidence",
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256="0" * 64,
            policy_id="in625-external-evidence-request-delegation-v1",
            request_delegation_policy_path=DELEGATION_POLICY,
            research_run=research_run,
            planning_registry_path=IN625_REGISTRY,
            output_dir=tmp_path / "compiled-request",
            action_inputs={
                "source_config": SOURCE_CONFIG,
                "archive_path": SOURCE_CONFIG,
            },
        )
