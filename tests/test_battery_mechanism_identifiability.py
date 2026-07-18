import hashlib
import json
from pathlib import Path

import pandas as pd

from src.platform_core.mechanism_identifiability import (
    audit_battery_evidence_inventory,
    bind_mechanism_requirements,
    build_default_mechanism_candidates,
    build_evidence_gap_registry,
    condition_coverage_summary,
    evidence_gap_registry_payload,
    export_battery_mechanism_audit_summary,
    mechanism_candidate_registry_payload,
    protocol_comparability_summary,
    select_bounded_evaluator,
    assess_identifiability,
)


def _write_battery_source(tmp_path: Path, rows: list[dict]) -> Path:
    source = tmp_path / "data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv"
    source.parent.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(source, index=False)
    return source


def _minimal_rows() -> list[dict]:
    return [
        {
            "battery_id": "B1",
            "cycle_index": 1,
            "ambient_temperature_c": 24,
            "discharge_capacity_ah": 1.8,
            "capacity_retention_percent": 100.0,
            "internal_resistance_ohm": None,
            "discharge_duration_s": 1000.0,
            "voltage_mean_v": 3.7,
            "current_mean_a": -1.0,
            "temperature_mean_c": 25.0,
            "failed": 0,
        },
        {
            "battery_id": "B1",
            "cycle_index": 2,
            "ambient_temperature_c": 24,
            "discharge_capacity_ah": 1.7,
            "capacity_retention_percent": 94.0,
            "internal_resistance_ohm": None,
            "discharge_duration_s": 950.0,
            "voltage_mean_v": 3.6,
            "current_mean_a": -1.0,
            "temperature_mean_c": 26.0,
            "failed": 0,
        },
    ]


def _canonical_json_sha256(path: str) -> str:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_mechanism_candidate_registry_is_deterministic_unique_and_metadata_only():
    candidates = build_default_mechanism_candidates()
    ids = [candidate.mechanism_id for candidate in candidates]
    payload = mechanism_candidate_registry_payload()

    assert ids == sorted(ids)
    assert len(ids) == len(set(ids)) == 10
    assert payload["execution_boundary"]["model_or_solver_executed"] is False
    assert payload["execution_boundary"]["parameter_fitting_performed"] is False
    assert "arrhenius_temperature_dependence" in ids
    assert "diffusion_transport" in ids
    assert "capacity_fade_trajectory" in ids


def test_single_temperature_and_missing_rate_response_block_arrhenius(tmp_path):
    _write_battery_source(tmp_path, _minimal_rows())
    inventory = audit_battery_evidence_inventory(tmp_path)
    candidates = build_default_mechanism_candidates()
    bindings = bind_mechanism_requirements(candidates, inventory, tmp_path)
    arrhenius = [item for item in bindings if item.mechanism_id == "arrhenius_temperature_dependence"]

    statuses = {item.evidence_status for item in arrhenius}
    limitations = " ".join(item.limitation for item in arrhenius)

    assert "missing_condition_variation" in statuses
    assert "missing_response_definition" in statuses
    assert "capacity" in limitations
    assert inventory["ambient_temperature_unique_count"] == 1


def test_diffusion_blocks_missing_state_geometry_boundary_and_time_axis(tmp_path):
    _write_battery_source(tmp_path, _minimal_rows())
    candidates = build_default_mechanism_candidates()
    bindings = bind_mechanism_requirements(candidates, repo_root=tmp_path)
    assessments = assess_identifiability(candidates, bindings, tmp_path)
    diffusion = next(item for item in assessments if item.mechanism_id == "diffusion_transport")

    assert diffusion.structural_status == "missing_state_observation"
    assert diffusion.practical_status == "blocked_missing_geometry"
    assert diffusion.contextual_status == "blocked_missing_boundary_conditions"
    assert diffusion.overall_status == "not_identifiable_from_current_data"
    assert "voltage_is_not_concentration_field" in diffusion.blocking_reasons
    assert "cycle_index_is_not_diffusion_time" in diffusion.blocking_reasons


def test_actual_battery_condition_and_protocol_audits_record_context_limits():
    condition_rows = condition_coverage_summary()
    protocol_rows = protocol_comparability_summary()
    protocol = {row["protocol_field"]: row for row in protocol_rows}

    assert sum(row["cycle_count"] for row in condition_rows) == 2495
    assert len(condition_rows) == 5
    assert all(row["condition_semantics"] == "ambient_metadata_not_confirmed_controlled" for row in condition_rows)
    assert protocol["overall_protocol_comparability"]["status"] == "insufficient_protocol_metadata"
    assert protocol["c_rate"]["status"] == "missing"


def test_selection_returns_one_descriptive_evaluator_and_no_mechanism_claim():
    decision = select_bounded_evaluator()

    assert decision.status == "descriptive_evaluator_only"
    assert decision.selected_evaluator_id == "battery_capacity_trajectory_consistency_evaluator_v1"
    assert decision.selected_operator_role == "Evaluator"
    assert "degradation mechanism identified" in decision.prohibited_claims
    assert "activation energy estimated" in decision.prohibited_claims


def test_evidence_gaps_include_prohibited_workarounds_and_no_credentials():
    gaps = build_evidence_gap_registry()
    payload = json.dumps(evidence_gap_registry_payload(), sort_keys=True)

    assert any(gap.prohibited_workaround == "using cycle index as seconds or hours" for gap in gaps)
    assert any(gap.missing_variable == "internal concentration field" for gap in gaps)
    assert "MP_API_KEY" not in payload
    assert "KAGGLE_KEY" not in payload
    assert ("C:" + "/") not in payload


def test_exported_compact_artifacts_are_row_level_free_and_preserve_existing_decisions():
    result = export_battery_mechanism_audit_summary(write_local=False)

    assert result["status"] == "exported"
    assert result["decision_status"] == "descriptive_evaluator_only"
    tracked_text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in result["tracked_outputs"].values()
        if path.endswith((".json", ".csv", ".md"))
    )
    assert "B0005" not in tracked_text
    assert "battery_obs_" not in tracked_text
    assert "activation_energy" not in tracked_text.lower()

    preserved = {
        "data/processed/materials_physics_v2_2_predictive_value_decision.json": "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0",
        "data/processed/battery_v2_3_data_audit_summary.json": "9efe4050ae1ca110a33e3104a3a717e45d80a29ed29fb53f799da167a2ba2008",
        "data/processed/battery_v2_3_pgir_readiness_decision.json": "6f0f91e4268c8aba4a82cd0d27e40d70247349eb310f85ea5d06ddd43fecbbb5",
    }
    for path, expected in preserved.items():
        assert _canonical_json_sha256(path) == expected
