from __future__ import annotations

import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.planning_adapter as planning


ROOT = Path(__file__).resolve().parents[1]


def _copy_tracked(tmp_path: Path, relative: str) -> Path:
    source = ROOT / relative
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


def _prepare_mp_repo(tmp_path: Path) -> None:
    for relative in (
        "configs/research/materials_project_external_evidence_requirement.v1.json",
        "configs/research/materials_project_external_source_candidates.v1.json",
        "configs/research/materials_project_external_source_search_planning_closeout.v1.json",
    ):
        _copy_tracked(tmp_path, relative)


def _prepare_tm_repo(tmp_path: Path) -> Path:
    return _copy_tracked(
        tmp_path,
        "configs/research/tm_fe_si_characterization_consumer_readiness.v1.json",
    )


def _prepare_nist_repo(tmp_path: Path) -> Path:
    readiness = _copy_tracked(
        tmp_path,
        "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
    )
    for relative in (
        "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
        "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
        "data/case_studies/nist_ambench_2018_02/README.md",
    ):
        _copy_tracked(tmp_path, relative)
    return readiness


def test_available_planning_adapters_are_stable() -> None:
    assert planning.available_planning_adapters() == (
        "nasa-battery",
        "materials-project-external-source",
        "tm-fe-si-descriptive",
        "nist-ambench-process-characterization",
    )


def test_tm_fe_si_correctly_stops_at_descriptive_closeout(tmp_path: Path) -> None:
    readiness = _prepare_tm_repo(tmp_path)
    before = readiness.read_bytes()

    decision = planning.plan_research_next_action(
        "tm-fe-si-descriptive",
        repository_root=tmp_path,
    )

    assert decision["selection_status"] == "no_positive_value_action"
    assert decision["selected_action"] is None
    assert decision["candidates"] == []
    assert decision["evidence_level"] == "Diagnostic"
    assert decision["maximum_allowed_use"] == "descriptive"
    assert decision["network_access_performed"] is False
    assert decision["action_executed"] is False
    assert decision["model_fit_performed"] is False
    assert readiness.read_bytes() == before


def test_nist_ambench_correctly_stops_before_predictive_promotion(
    tmp_path: Path,
) -> None:
    readiness = _prepare_nist_repo(tmp_path)
    before = readiness.read_bytes()

    decision = planning.plan_research_next_action(
        "nist-ambench-process-characterization",
        repository_root=tmp_path,
    )

    assert decision["selection_status"] == "no_positive_value_action"
    assert decision["selected_action"] is None
    assert decision["candidates"] == []
    assert decision["evidence_level"] == "Diagnostic"
    assert decision["maximum_allowed_use"] == "descriptive"
    assert decision["network_access_performed"] is False
    assert decision["action_executed"] is False
    assert decision["model_fit_performed"] is False
    assert len(decision["evidence_bindings"]) == 4
    assert readiness.read_bytes() == before


def test_nist_ambench_fails_closed_if_predictive_use_is_promoted(
    tmp_path: Path,
) -> None:
    readiness_path = _prepare_nist_repo(tmp_path)
    payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    payload["current_scope"]["predictive_use_authorized"] = True
    readiness_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="stronger-use boundary"):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_materials_project_correctly_preserves_closed_source_search(tmp_path: Path) -> None:
    _prepare_mp_repo(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    decision = planning.plan_research_next_action(
        "materials-project-external-source",
        repository_root=tmp_path,
    )

    assert decision["selection_status"] == "no_positive_value_action"
    assert decision["selected_action"] is None
    assert decision["candidates"] == []
    assert decision["evidence_level"] == "Diagnostic"
    assert decision["network_access_performed"] is False
    assert decision["action_executed"] is False
    assert decision["model_fit_performed"] is False
    assert "four tracked high-priority candidates" in decision["reason"]
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before


def test_materials_project_fails_closed_if_candidate_disposition_drifts(
    tmp_path: Path,
) -> None:
    _prepare_mp_repo(tmp_path)
    registry_path = (
        tmp_path
        / "configs/research/materials_project_external_source_candidates.v1.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["candidates"][0]["semantic_checks"]["thermodynamic_reference_state"] = (
        "confirmed_match"
    )
    registry["candidates"][0]["semantic_checks"]["energy_correction_semantics"] = (
        "confirmed_match"
    )
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="dispositions drifted"):
        planning.plan_research_next_action(
            "materials-project-external-source",
            repository_root=tmp_path,
        )


def test_tm_fe_si_fails_closed_if_stronger_use_is_promoted(tmp_path: Path) -> None:
    readiness_path = _prepare_tm_repo(tmp_path)
    payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    payload["readiness"]["predictive_case_ready"] = True
    readiness_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="stronger-use boundary"):
        planning.plan_research_next_action(
            "tm-fe-si-descriptive",
            repository_root=tmp_path,
        )


def test_nasa_adapter_delegates_without_reimplementing_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_plan(run_arg: Path, registry_arg: Path, root_arg: Path) -> dict[str, object]:
        captured["args"] = (run_arg, registry_arg, root_arg)
        return {
            "policy_version": "1.0",
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "existing NASA policy stopped",
        }

    monkeypatch.setattr(planning, "plan_nasa_next_action", fake_plan)
    decision = planning.plan_research_next_action(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=registry,
    )

    assert captured["args"] == (run, registry, tmp_path.resolve())
    assert decision["selection_status"] == "no_positive_value_action"
    assert decision["delegated_policy_version"] == "1.0"
    assert decision["action_executed"] is False


def test_unknown_adapter_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(planning.PlanningAdapterError, match="unknown planning adapter"):
        planning.plan_research_next_action(
            "unknown-domain",
            repository_root=tmp_path,
        )
