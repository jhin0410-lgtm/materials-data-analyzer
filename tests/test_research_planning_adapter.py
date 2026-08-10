from __future__ import annotations

import csv
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


def _rewrite_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise AssertionError("test helper requires at least one row")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _mock_nasa_state(sha256: str = "a" * 64) -> dict[str, str]:
    return {"ledger_sha256": sha256}


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


def test_tm_fe_si_fails_closed_if_producer_maximum_use_is_downgraded(
    tmp_path: Path,
) -> None:
    readiness_path = _prepare_tm_repo(tmp_path)
    payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    payload["producer"]["real_source_replay"]["maximum_allowed_use"] = "display"
    readiness_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="producer maximum allowed use"):
        planning.plan_research_next_action(
            "tm-fe-si-descriptive",
            repository_root=tmp_path,
        )


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


def test_nist_ambench_fails_closed_if_actual_trace_row_is_removed(
    tmp_path: Path,
) -> None:
    _prepare_nist_repo(tmp_path)
    process_path = (
        tmp_path
        / "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    )
    rows = _read_csv(process_path)
    _rewrite_csv(process_path, rows[:-1])

    with pytest.raises(planning.PlanningAdapterError, match="actual table row counts"):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_nist_ambench_fails_closed_if_actual_process_condition_drifts(
    tmp_path: Path,
) -> None:
    _prepare_nist_repo(tmp_path)
    process_path = (
        tmp_path
        / "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    )
    rows = _read_csv(process_path)
    rows[0]["actual_laser_power_w"] = "200.0"
    _rewrite_csv(process_path, rows)

    with pytest.raises(planning.PlanningAdapterError, match="frozen process condition drifted"):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_nist_ambench_fails_closed_if_process_value_is_non_numeric(
    tmp_path: Path,
) -> None:
    _prepare_nist_repo(tmp_path)
    process_path = (
        tmp_path
        / "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    )
    rows = _read_csv(process_path)
    rows[0]["actual_laser_power_w"] = "not-a-number"
    _rewrite_csv(process_path, rows)

    with pytest.raises(planning.PlanningAdapterError, match="must be numeric"):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_nist_ambench_fails_closed_if_measurement_value_is_non_finite(
    tmp_path: Path,
) -> None:
    _prepare_nist_repo(tmp_path)
    measurement_path = (
        tmp_path
        / "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
    )
    rows = _read_csv(measurement_path)
    rows[0]["melt_pool_width_mean_um"] = "nan"
    _rewrite_csv(measurement_path, rows)

    with pytest.raises(planning.PlanningAdapterError, match="must be finite"):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_nist_ambench_fails_closed_if_trace_identity_is_reassigned(
    tmp_path: Path,
) -> None:
    _prepare_nist_repo(tmp_path)
    process_path = (
        tmp_path
        / "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    )
    rows = _read_csv(process_path)
    rows[0]["case_id"] = "amb2018-02-A"
    _rewrite_csv(process_path, rows)

    with pytest.raises(
        planning.PlanningAdapterError,
        match="frozen trace/case/sample identity drifted",
    ):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_nist_ambench_fails_closed_if_sample_join_is_not_one_to_one(
    tmp_path: Path,
) -> None:
    _prepare_nist_repo(tmp_path)
    measurement_path = (
        tmp_path
        / "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
    )
    rows = _read_csv(measurement_path)
    rows[0]["sample_id"] = "amb2018_02_ammt_trace_missing"
    _rewrite_csv(measurement_path, rows)

    with pytest.raises(planning.PlanningAdapterError, match="join one-to-one"):
        planning.plan_research_next_action(
            "nist-ambench-process-characterization",
            repository_root=tmp_path,
        )


def test_nist_ambench_fails_closed_if_blocker_summary_is_missing(
    tmp_path: Path,
) -> None:
    readiness_path = _prepare_nist_repo(tmp_path)
    payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    payload["current_blocker"].pop("summary")
    readiness_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="current_blocker.summary"):
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
    assert "tracked high-priority candidates" in decision["reason"]
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


def test_materials_project_fails_closed_if_candidate_id_is_duplicated(
    tmp_path: Path,
) -> None:
    _prepare_mp_repo(tmp_path)
    registry_path = (
        tmp_path
        / "configs/research/materials_project_external_source_candidates.v1.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["candidates"][1]["candidate_id"] = registry["candidates"][0]["candidate_id"]
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="candidate_id is duplicated"):
        planning.plan_research_next_action(
            "materials-project-external-source",
            repository_root=tmp_path,
        )


def test_materials_project_fails_closed_if_evidence_level_drifts(
    tmp_path: Path,
) -> None:
    _prepare_mp_repo(tmp_path)
    closeout_path = (
        tmp_path
        / "configs/research/materials_project_external_source_search_planning_closeout.v1.json"
    )
    closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    closeout["evidence_level"] = "Validated"
    closeout_path.write_text(json.dumps(closeout), encoding="utf-8")

    with pytest.raises(planning.PlanningAdapterError, match="evidence level drifted"):
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
    monkeypatch.setattr(
        planning,
        "load_research_state",
        lambda path: _mock_nasa_state(),
    )
    decision = planning.plan_research_next_action(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=registry,
    )

    assert captured["args"] == (run.resolve(), registry, tmp_path.resolve())
    assert decision["selection_status"] == "no_positive_value_action"
    assert decision["delegated_policy_version"] == "1.0"
    assert decision["evidence_level"] is None
    assert decision["action_executed"] is False


def test_nasa_adapter_preserves_verified_latest_evidence_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        planning,
        "plan_nasa_next_action",
        lambda *args: {
            "policy_version": "1.0",
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "existing NASA policy stopped",
            "latest_evidence_level": "Diagnostic",
        },
    )
    monkeypatch.setattr(
        planning,
        "load_research_state",
        lambda path: _mock_nasa_state(),
    )

    decision = planning.plan_research_next_action(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=registry,
    )

    assert decision["evidence_level"] == "Diagnostic"


def test_nasa_adapter_rejects_unknown_evidence_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        planning,
        "plan_nasa_next_action",
        lambda *args: {
            "policy_version": "1.0",
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "existing NASA policy stopped",
            "latest_evidence_level": "Validated",
        },
    )
    monkeypatch.setattr(
        planning,
        "load_research_state",
        lambda path: _mock_nasa_state(),
    )

    with pytest.raises(planning.PlanningAdapterError, match="unsupported evidence level"):
        planning.plan_research_next_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=registry,
        )


def test_nasa_adapter_rejects_ledger_change_during_planning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    states = iter([_mock_nasa_state("a" * 64), _mock_nasa_state("b" * 64)])

    monkeypatch.setattr(planning, "load_research_state", lambda path: next(states))
    monkeypatch.setattr(
        planning,
        "plan_nasa_next_action",
        lambda *args: {
            "policy_version": "1.0",
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "existing NASA policy stopped",
        },
    )

    with pytest.raises(planning.PlanningAdapterError, match="ledger changed"):
        planning.plan_research_next_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=registry,
        )


def test_nasa_ledger_binding_uses_verified_preplanning_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "research_ledger.jsonl").write_text("mutable path bytes\n", encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    verified_sha = "a" * 64

    monkeypatch.setattr(
        planning,
        "load_research_state",
        lambda path: _mock_nasa_state(verified_sha),
    )
    monkeypatch.setattr(
        planning,
        "plan_nasa_next_action",
        lambda *args: {
            "policy_version": "1.0",
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "existing NASA policy stopped",
        },
    )

    decision = planning.plan_research_next_action(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=registry,
    )

    ledger_binding = next(
        item
        for item in decision["evidence_bindings"]
        if item["role"] == "research_ledger"
    )
    assert ledger_binding["sha256"] == verified_sha


def test_unknown_adapter_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(planning.PlanningAdapterError, match="unknown planning adapter"):
        planning.plan_research_next_action(
            "unknown-domain",
            repository_root=tmp_path,
        )
