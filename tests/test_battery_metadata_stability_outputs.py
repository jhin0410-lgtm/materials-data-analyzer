import csv
import hashlib
import json
from pathlib import Path


TRACKED = sorted(Path("data/processed").glob("battery_v2_3_5_*"))


def _canonical_json_sha256(path: str) -> str:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


PRESERVED = {
    "data/processed/materials_physics_v2_2_predictive_value_decision.json": "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0",
    "data/processed/materials_v2_2_5_predictive_value_decision.json": "dbbfffdee4117eb3609fbe40779e605487c6668a9867ecdfe17b165832f19ad4",
    "data/processed/materials_v2_2_closeout_decision.json": "ae52eb9607b8167ddca6fe79b528ca36dd4bfc900217dd20cb0f8f6b095dd79c",
    "data/platform/pgir_concept_registry_v1.json": "1a1fa3dd4b9f0df13976440fe222145902a0ded271eafcb865571f3033a6f70e",
    "data/platform/pgir_representation_governance_v1.json": "3b4e90a6f338bf0d6ac72aef120aa9601bc808e0a65fe55a6e701332bea8fc7a",
    "data/processed/battery_v2_3_data_audit_summary.json": "9efe4050ae1ca110a33e3104a3a717e45d80a29ed29fb53f799da167a2ba2008",
    "data/processed/battery_v2_3_pgir_readiness_decision.json": "6f0f91e4268c8aba4a82cd0d27e40d70247349eb310f85ea5d06ddd43fecbbb5",
    "data/processed/battery_v2_3_3_operator_selection_decision.json": "685cdfbcccc2ed5e317df2ec6368d960ce35a0542d35a791da1bb2892807a9e9",
    "data/processed/battery_v2_3_4_evaluator_decision.json": "07078145a0f0826ad7d73bcce14bd0fd65070fa61ff75286e5ff43932f93744f",
    "data/processed/battery_v2_3_4_evaluator_execution_summary.json": "a95bb1adc2cc5b0cdcfd58c2b36e02be3f9ce543b625bd20eb35aca74e337ae3",
    "data/processed/battery_v2_3_4_claim_evidence.json": "67cbd4590e0b36df0fdcd02eef01ee65ff8b5423a84317bea55d921cddb86825",
}
PRESERVED_AT_COLLECTION = {path: _canonical_json_sha256(path) for path in PRESERVED}


def test_v2_3_5_compact_outputs_are_parseable_aggregate_and_identity_free():
    assert len(TRACKED) == 8
    combined = "\n".join(path.read_text(encoding="utf-8") for path in TRACKED)
    for path in TRACKED:
        if path.suffix == ".json":
            assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "2.3.5"
        elif path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            assert len(header) == len(set(header))

    assert "battery_trajectory_B" not in combined
    assert "battery_state_B" not in combined
    assert "B0005" not in combined
    assert "C:/" not in combined
    assert "C:\\" not in combined
    assert "API_KEY=" not in combined
    event_rows = list(
        csv.DictReader(
            Path("data/processed/battery_v2_3_5_event_stability_summary.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    assert event_rows
    assert all(row["mechanism_interpretation"] == "prohibited" for row in event_rows)


def test_actual_source_recovery_counts_distinguish_impedance_rows_from_complete_pairs():
    lineage = json.loads(
        Path("data/processed/battery_v2_3_5_source_lineage_summary.json").read_text(encoding="utf-8")
    )
    recovery = {
        row["metadata_field"]: row
        for row in csv.DictReader(
            Path("data/processed/battery_v2_3_5_metadata_recovery_summary.csv").open(
                encoding="utf-8", newline=""
            )
        )
    }

    assert lineage["exact_lineage_cell_count"] == 34
    assert lineage["analysis_ready_rows"] == 2495
    assert lineage["exact_source_key_match_rows"] == 2495
    assert lineage["full_source_key_match_rows"] == 2794
    assert lineage["archive_metadata_matches_extracted"] is True
    assert lineage["archive_metadata_member_sha256"] == lineage["metadata_sha256"]
    assert lineage["protocol_document_count"] == 9
    assert lineage["impedance_rows"] == 1956
    assert lineage["impedance_complete_re_rct_rows"] == 1947
    assert recovery["impedance_re_rct"]["expected_records"] == "1956"
    assert recovery["impedance_re_rct"]["supported_records"] == "1947"
    assert recovery["measurement_uncertainty"]["supported_records"] == "0"


def test_actual_stability_decision_matches_policy_and_event_summaries():
    decision = json.loads(Path("data/processed/battery_v2_3_5_decision.json").read_text(encoding="utf-8"))
    policies = list(
        csv.DictReader(
            Path("data/processed/battery_v2_3_5_evaluator_stability_summary.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    events = list(
        csv.DictReader(
            Path("data/processed/battery_v2_3_5_event_stability_summary.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )

    assert len(policies) == 9
    assert all(row["evaluated_trajectories"] == "33" for row in policies)
    assert all(row["blocked_trajectories"] == "1" for row in policies)
    counts = {
        status: sum(int(row["event_count"]) for row in events if row["stability_status"] == status)
        for status in decision["event_stability_counts"]
    }
    assert counts == decision["event_stability_counts"]
    assert sum(counts.values()) == decision["bounded_event_count"] == 489
    assert decision["status"] == "descriptive_evaluator_stable_with_policy_restrictions"
    assert decision["representative_mechanism"] == "none"
    assert decision["threshold_optimization_performed"] is False
    assert decision["prediction_performed"] is False


def test_v2_2_and_v2_3_1_through_v2_3_4_decisions_remain_unchanged():
    assert PRESERVED_AT_COLLECTION == PRESERVED
