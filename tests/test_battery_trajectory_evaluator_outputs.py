import csv
import hashlib
import json
from pathlib import Path


TRACKED = [
    Path("data/processed/battery_v2_3_4_evaluator_execution_summary.json"),
    Path("data/processed/battery_v2_3_4_eligibility_summary.csv"),
    Path("data/processed/battery_v2_3_4_finding_summary.csv"),
    Path("data/processed/battery_v2_3_4_trust_summary.csv"),
    Path("data/processed/battery_v2_3_4_evaluator_decision.json"),
    Path("data/processed/battery_v2_3_4_claim_evidence.json"),
    Path("data/processed/battery_v2_3_4_report_summary.md"),
]


def _canonical_json_sha256(path: str) -> str:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


PRESERVED_DECISION_CHECKSUMS = {
    "data/processed/materials_physics_v2_2_predictive_value_decision.json": "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0",
    "data/processed/materials_v2_2_5_predictive_value_decision.json": "dbbfffdee4117eb3609fbe40779e605487c6668a9867ecdfe17b165832f19ad4",
    "data/processed/materials_v2_2_closeout_decision.json": "ae52eb9607b8167ddca6fe79b528ca36dd4bfc900217dd20cb0f8f6b095dd79c",
    "data/platform/pgir_concept_registry_v1.json": "1a1fa3dd4b9f0df13976440fe222145902a0ded271eafcb865571f3033a6f70e",
    "data/platform/pgir_representation_governance_v1.json": "3b4e90a6f338bf0d6ac72aef120aa9601bc808e0a65fe55a6e701332bea8fc7a",
    "data/processed/battery_v2_3_data_audit_summary.json": "9efe4050ae1ca110a33e3104a3a717e45d80a29ed29fb53f799da167a2ba2008",
    "data/processed/battery_v2_3_pgir_readiness_decision.json": "6f0f91e4268c8aba4a82cd0d27e40d70247349eb310f85ea5d06ddd43fecbbb5",
    "data/processed/battery_v2_3_3_operator_selection_decision.json": "685cdfbcccc2ed5e317df2ec6368d960ce35a0542d35a791da1bb2892807a9e9",
}
PRESERVED_DECISION_CHECKSUMS_AT_COLLECTION = {
    path: _canonical_json_sha256(path) for path in PRESERVED_DECISION_CHECKSUMS
}


def test_tracked_evaluator_outputs_are_compact_parseable_and_identity_free():
    assert all(path.exists() for path in TRACKED)
    combined = "\n".join(path.read_text(encoding="utf-8") for path in TRACKED)

    assert "battery_trajectory_B" not in combined
    assert "battery_state_B" not in combined
    assert "B0005" not in combined
    assert "C:/" not in combined
    assert "C:\\" not in combined
    assert "API_KEY" not in combined
    assert "RUL predicted" in combined
    assert "degradation_mechanism_identified\": false" in combined
    for path in TRACKED:
        if path.suffix == ".json":
            assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "2.3.4"
        elif path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader)
                assert len(header) == len(set(header))


def test_actual_compact_execution_records_34_trajectories_and_deterministic_rerun():
    execution = json.loads(TRACKED[0].read_text(encoding="utf-8"))
    decision = json.loads(TRACKED[4].read_text(encoding="utf-8"))
    eligibility = list(csv.DictReader(TRACKED[1].open(encoding="utf-8", newline="")))

    assert execution["requested_trajectories"] == 34
    assert execution["evaluated_trajectories"] == 33
    assert execution["total_states"] == 2495
    assert execution["valid_capacity_observations"] == 2495
    assert execution["deterministic_rerun_match"] is True
    assert execution["deterministic_result_checksum"] == execution["deterministic_rerun_checksum"]
    assert {row["eligibility_status"]: int(row["trajectory_count"]) for row in eligibility} == {
        "blocked_insufficient_capacity_data": 1,
        "eligible_with_warnings": 33,
    }
    assert decision["status"] == "descriptive_evaluator_executed_with_restrictions"
    assert decision["representative_mechanism"] == "none"
    assert decision["model_or_solver_executed"] is False


def test_prior_scientific_decisions_remain_logically_unchanged():
    assert PRESERVED_DECISION_CHECKSUMS_AT_COLLECTION == PRESERVED_DECISION_CHECKSUMS


def test_blocked_arrhenius_and_diffusion_decisions_are_not_promoted():
    identifiability = list(
        csv.DictReader(
            Path("data/processed/battery_v2_3_3_identifiability_summary.csv").open(encoding="utf-8", newline="")
        )
    )
    by_id = {row["mechanism_id"]: row for row in identifiability}

    assert by_id["arrhenius_temperature_dependence"]["overall_status"] == "not_identifiable_from_current_data"
    assert by_id["diffusion_transport"]["overall_status"] == "not_identifiable_from_current_data"
