from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.real_data_episode_acceptance import (
    evaluate_real_data_episode_suite,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be an object: {path}")
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> str:
    body = _json_bytes(value)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def _single_csv_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise RuntimeError(f"expected exactly one CSV row: {path}")
    return rows[0]


def _nist_episode(
    *,
    repository: Path,
    representative: Path,
    output: Path,
) -> dict[str, Any]:
    summary_path = representative / "representative_workflow_summary.json"
    manifest_path = representative / "representative_workflow_manifest.json"
    summary = _json(summary_path)
    manifest = _json(manifest_path)

    if summary.get("status") != "completed":
        raise RuntimeError("representative NIST workflow did not complete")
    if summary.get("evidence_level") != "Diagnostic":
        raise RuntimeError("representative NIST evidence boundary changed")
    verified = summary["components"]["verified_case"]
    audit = summary["components"]["process_design_audit"]
    plan_summary = summary["components"]["minimum_design_plan"]
    if verified["trace_count"] != 10 or verified["model_trained"] is not False:
        raise RuntimeError("representative NIST verified-case contract changed")
    if audit["unique_condition_count"] != 3:
        raise RuntimeError("representative NIST condition count changed")
    if audit["factorial_coverage_fraction"] != 0.5:
        raise RuntimeError("representative NIST design coverage changed")
    if audit["readiness"] != "not_ready_for_predictive_or_causal_modeling":
        raise RuntimeError("representative NIST readiness boundary changed")
    if plan_summary["recommended_next_action"] != "execute_stage_1_only":
        raise RuntimeError("representative NIST next action changed")
    if plan_summary["stage_1_new_conditions"] != 3:
        raise RuntimeError("representative NIST Stage 1 condition count changed")
    if plan_summary["stage_1_new_traces"] != 9:
        raise RuntimeError("representative NIST Stage 1 trace count changed")
    if plan_summary["response_model_fitted"] is not False:
        raise RuntimeError("representative NIST unexpectedly fitted a response model")

    if manifest.get("artifact_count") != len(manifest.get("artifact_sha256", {})):
        raise RuntimeError("representative workflow artifact manifest is inconsistent")
    for relative, expected in manifest["artifact_sha256"].items():
        path = representative / relative
        if not path.is_file() or _sha256(path) != expected:
            raise RuntimeError(f"representative artifact binding failed: {relative}")

    source = (
        repository
        / "data"
        / "case_studies"
        / "nist_ambench_2018_02"
        / "source_melt_pool_measurements.csv"
    )
    if not source.is_file():
        raise RuntimeError("tracked NIST source measurement table is missing")

    plan_relative = Path(plan_summary["plan"])
    plan_path = representative / plan_relative
    plan = _json(plan_path)
    stage_1 = plan["stages"]["stage_1_complete_observed_grid"]
    decision = {
        "schema_version": "1.0",
        "episode_id": "nist-ambench-2018-02-process-design",
        "selected_action": "execute_stage_1_only",
        "stage_1_condition_count": len(stage_1["conditions"]),
        "stage_1_planned_trace_count": stage_1["planned_new_trace_count"],
        "stage_2_conditional": plan_summary["stage_2_is_conditional"],
        "response_model_fitted": False,
        "optimization_performed": False,
        "physical_experiment_execution_authorized": False,
        "reason": (
            "The observed 2 x 3 process grid is only 50% populated; complete the "
            "predeclared Stage 1 cells before any predictive or causal analysis."
        ),
    }
    decision_path = output / "nist_ambench_next_action.json"
    decision_sha = _write_json(decision_path, decision)

    return {
        "episode_id": "nist-ambench-2018-02-process-design",
        "episode_family_id": "lpbf_process_design_identifiability",
        "modality": "lpbf_cross_section_process_characterization",
        "evidence_class": "E1_authoritative_reference_measurements",
        "research_question": (
            "Does the source-bound ten-trace NIST IN625 AMMT dataset support "
            "predictive or causal power-speed analysis, and what evidence should be "
            "acquired next if it does not?"
        ),
        "real_source_binding": {
            "source_kind": "authoritative_reference_transcription",
            "source_locator": "NIST AM-Bench 2018-02 transverse cross-section results",
            "artifact_sha256": _sha256(source),
            "acquisition_receipt_sha256": None,
            "synthetic": False,
        },
        "scientific_intake": {
            "status": "accepted",
            "reason": (
                "Ten source-reported AMMT traces are checksum-bound, joined by explicit "
                "sample_id, and accepted only at Diagnostic evidence level for "
                "descriptive and design-identifiability auditing."
            ),
        },
        "analysis": {
            "performed": True,
            "analysis_type": "process_design_identifiability_audit",
            "trace_count": 10,
            "unique_condition_count": 3,
            "factorial_coverage_fraction": 0.5,
            "modeling_readiness": audit["readiness"],
            "response_model_fitted": False,
        },
        "weaknesses_or_contradictions": [
            "Only three of six observed-level power-speed cells are populated.",
            "The current design is not ready for predictive or causal modeling.",
            "Same-source replicated traces do not create independent external evidence.",
        ],
        "next_action_decision": {
            "decision_report_sha256": decision_sha,
            "action_recorded": True,
            "selected_action": "execute_stage_1_only",
        },
        "reanalysis": {
            "performed": True,
            "basis": "response-free structural design analysis of the three missing cells",
            "result": "Stage 1 grid completion remains the bounded priority",
        },
        "iteration_count": 3,
        "terminal_state": "stopped",
        "terminal_reason": (
            "The software evidence cycle is complete; further scientific progress "
            "requires the nine new physical Stage 1 traces tracked by Issue #76."
        ),
        "scientific_status_changed": False,
        "scientific_promotion_authorized": False,
    }


def _nasa_episode(*, repository: Path, output: Path) -> dict[str, Any]:
    source = (
        repository
        / "data"
        / "processed"
        / "kaggle_nasa_battery_cycle_summary_analysis_ready.csv"
    )
    forecast_path = (
        repository
        / "data"
        / "processed"
        / "battery_v2_6_1_generalization_forecast_summary.json"
    )
    lineage_path = (
        repository
        / "data"
        / "processed"
        / "battery_v2_3_5_source_lineage_summary.json"
    )
    closeout_path = (
        repository
        / "data"
        / "processed"
        / "battery_v2_6_14_external_evidence_line_closeout_summary.json"
    )
    stage11_path = (
        repository
        / "data"
        / "processed"
        / "battery_v2_6_11_external_cohort_next_source_selection_summary.json"
    )

    forecast = _json(forecast_path)
    lineage = _json(lineage_path)
    closeout = _json(closeout_path)
    stage11 = _json(stage11_path)
    source_sha = _sha256(source)
    if forecast["source_sha256"] != source_sha:
        raise RuntimeError("NASA forecast is not bound to the current source CSV bytes")
    if lineage["pgir_source_checksum_sha256"] != source_sha:
        raise RuntimeError("NASA lineage and forecast source bindings disagree")
    if lineage["raw_discharge_files_verified"] != 2495:
        raise RuntimeError("NASA raw-discharge lineage coverage changed")
    if lineage["exact_source_key_match_rows"] != 2495:
        raise RuntimeError("NASA exact source-key coverage changed")
    if lineage["inference_performed"] is not False:
        raise RuntimeError("NASA lineage unexpectedly inferred missing source identity")
    if forecast["leakage_checks"]["status"] != "passed":
        raise RuntimeError("NASA leakage checks are no longer passing")
    if forecast["baseline_comparison"]["mae_improvement_percent"] >= 0:
        raise RuntimeError(
            "NASA registered ridge benchmark no longer underperforms persistence"
        )
    if closeout["verified_stage_count"] != 13 or closeout["stage_checksum_failures"]:
        raise RuntimeError("NASA v2.6 evidence-line checksum closeout changed")
    if closeout["decision"]["overall_status"] != (
        "v2_6_external_evidence_line_closed_predictive_validation_not_ready"
    ):
        raise RuntimeError("NASA v2.6 terminal decision changed")
    if closeout["next_action"]["v2_6_status"] != "closed":
        raise RuntimeError("NASA v2.6 evidence line is not closed")
    if stage11["selection_decision"]["overall_status"] != (
        "next_source_candidate_selected_gate_not_passed"
    ):
        raise RuntimeError("NASA Stage 11 next-source selection changed")

    decision = {
        "schema_version": "1.0",
        "episode_id": "nasa-battery-v2-6-evidence-line",
        "selected_action_artifact": stage11_path.relative_to(repository).as_posix(),
        "selected_action_artifact_sha256": _sha256(stage11_path),
        "selected_candidate": "michigan_formation",
        "selection_scope": "source_binding_only_not_admission",
        "subsequent_reanalysis_stages": [
            "battery_v2_6_12_michigan_formation_provider_package_summary.json",
            "battery_v2_6_13_michigan_formation_deepblue_metadata_summary.json",
        ],
        "terminal_closeout": closeout_path.relative_to(repository).as_posix(),
        "terminal_closeout_sha256": _sha256(closeout_path),
        "scientific_status_changed": False,
    }
    decision_path = output / "nasa_battery_next_action.json"
    decision_sha = _write_json(decision_path, decision)

    ridge = next(
        item for item in forecast["aggregate_metrics"] if item["model"] == "ridge"
    )
    persistence = next(
        item
        for item in forecast["aggregate_metrics"]
        if item["model"] == "persistence"
    )
    return {
        "episode_id": "nasa-battery-v2-6-evidence-line",
        "episode_family_id": "battery_generalization_and_external_evidence",
        "modality": "battery_capacity_trajectory_forecasting",
        "evidence_class": "E1_processed_physical_cycle_measurements",
        "research_question": (
            "Does a leakage-controlled ridge warm-start forecast generalize across "
            "source-bound NASA battery trajectories better than persistence, and can "
            "independent external validation be admitted?"
        ),
        "real_source_binding": {
            "source_kind": "verified_local_public_dataset_snapshot",
            "source_locator": lineage["dataset_slug"],
            "artifact_sha256": source_sha,
            "acquisition_receipt_sha256": None,
            "synthetic": False,
        },
        "scientific_intake": {
            "status": "accepted",
            "reason": (
                "The 2,495-row analysis-ready source is exactly bound through raw-file "
                "lineage for the registered warm-start benchmark; acceptance does not "
                "extend to an independent external cohort."
            ),
        },
        "analysis": {
            "performed": True,
            "analysis_type": "group_disjoint_warm_start_cross_battery_forecast",
            "trajectory_count": forecast["evaluable_trajectory_count"],
            "prediction_count": forecast["eligible_prediction_rows"],
            "ridge_mae": ridge["mae"],
            "persistence_mae": persistence["mae"],
            "ridge_mae_improvement_percent": forecast["baseline_comparison"][
                "mae_improvement_percent"
            ],
            "leakage_checks": forecast["leakage_checks"],
        },
        "weaknesses_or_contradictions": [
            "Ridge MAE is worse than persistence under the registered benchmark.",
            "Only 13 of 33 evaluated batteries improve over persistence.",
            "Independent external predictive-validation comparability is not established.",
            "The local package cannot verify the original NASA source snapshot identity.",
        ],
        "next_action_decision": {
            "decision_report_sha256": decision_sha,
            "action_recorded": True,
            "selected_action": "bind_michigan_formation_provider_evidence",
        },
        "reanalysis": {
            "performed": True,
            "stage_count": 13,
            "result": closeout["scientific_closeout"]["result"],
            "external_cohort_admitted": False,
            "provider_metadata_outcome": (
                "HTTP 403 prevented exact provider file-set metadata recovery"
            ),
        },
        "iteration_count": 13,
        "terminal_state": "stopped",
        "terminal_reason": closeout["scientific_closeout"]["primary_limitation"],
        "scientific_status_changed": False,
        "scientific_promotion_authorized": False,
    }


def _rwgs_episode(
    *,
    consumer_root: Path,
    bundle_manifest_path: Path,
    output: Path,
) -> dict[str, Any]:
    summary_path = consumer_root / "cross_repository_handoff_summary.json"
    manifest_path = consumer_root / "cross_repository_handoff_manifest.json"
    integrated_path = consumer_root / "integrated_sample_table.csv"
    summary = _json(summary_path)
    manifest = _json(manifest_path)
    row = _single_csv_row(integrated_path)

    if summary.get("status") != "verified":
        raise RuntimeError("RWGS consumer handoff is not verified")
    if summary.get("case_id") != "public-rwgs-5cu-al2o3-xrd-sem-eds":
        raise RuntimeError("RWGS case identity changed")
    if summary["scientific_closeout"]["evidence_level"] != "Diagnostic":
        raise RuntimeError("RWGS scientific evidence boundary changed")
    if summary["software_validation"]["model_trained"] is not False:
        raise RuntimeError("RWGS workflow unexpectedly trained a model")
    if row.get("sample_id") != "rwgs-5wt-cu-al2o3":
        raise RuntimeError("RWGS sample identity changed")
    if row.get("eds_unexpected_elements") != "Ni":
        raise RuntimeError("RWGS expected Ni anomaly is no longer present")
    if row.get("sem_quantitative_segmentation_status") != "blocked_method_mismatch":
        raise RuntimeError("RWGS SEM method-mismatch blocker changed")
    if row.get("identical_physical_aliquot_confirmed", "").lower() not in {
        "false",
        "0",
    }:
        raise RuntimeError("RWGS aliquot identity unexpectedly became confirmed")
    if row.get("nominal_composition_confirmed", "").lower() not in {"false", "0"}:
        raise RuntimeError("RWGS nominal composition unexpectedly became confirmed")

    bundle_sha = _sha256(bundle_manifest_path)
    expected_bundle_sha = manifest.get("input_bundle", {}).get("sha256")
    if expected_bundle_sha != bundle_sha:
        raise RuntimeError(
            "RWGS consumer manifest is not bound to exact producer bundle bytes"
        )

    decision = {
        "schema_version": "1.0",
        "episode_id": "public-rwgs-xrd-eds-provenance-cycle",
        "selected_action": "audit_existing_bundle_for_ni_and_sem_provenance",
        "triggering_observations": {
            "unexpected_eds_elements": row["eds_unexpected_elements"],
            "sem_quantitative_segmentation_status": row[
                "sem_quantitative_segmentation_status"
            ],
            "identical_physical_aliquot_confirmed": False,
            "nominal_composition_confirmed": False,
        },
        "prohibited_actions": [
            "process_response_modeling",
            "interpret_Ni_as_contamination_or_active_phase",
            "quantitative_SEM_segmentation_under_method_mismatch",
        ],
        "scientific_status_changed": False,
    }
    decision_path = output / "rwgs_next_action.json"
    decision_sha = _write_json(decision_path, decision)

    reanalysis = {
        "performed": True,
        "existing_bundle_exhausted": True,
        "ni_origin_resolved": False,
        "sem_quantitative_segmentation_released": False,
        "physical_aliquot_identity_resolved": False,
        "nominal_composition_resolved": False,
        "result": (
            "The existing source-bound bundle preserves the Ni observation and SEM "
            "method mismatch but cannot support a mechanistic or compositional "
            "interpretation."
        ),
    }
    return {
        "episode_id": "public-rwgs-xrd-eds-provenance-cycle",
        "episode_family_id": "cross_repository_characterization_anomaly_audit",
        "modality": "xrd_eds_sem_characterization",
        "evidence_class": "E1_public_characterization_bundle",
        "research_question": (
            "Can the public RWGS XRD/EDS/SEM evidence support a composition or "
            "process-response conclusion after the unexpected Ni signal and SEM method "
            "mismatch are audited?"
        ),
        "real_source_binding": {
            "source_kind": "public_characterization_handoff_bundle",
            "source_locator": summary["case_id"],
            "artifact_sha256": bundle_sha,
            "acquisition_receipt_sha256": None,
            "synthetic": False,
        },
        "scientific_intake": {
            "status": "accepted",
            "reason": (
                "The pinned producer bundle passed independent handoff validation and "
                "consumer verification for Diagnostic descriptive use only."
            ),
        },
        "analysis": {
            "performed": True,
            "analysis_type": "cross_repository_characterization_consistency_audit",
            "feature_row_count": summary["feature_summary"]["row_count"],
            "measurement_count": summary["feature_summary"]["measurement_count"],
            "instruments": summary["feature_summary"]["instruments"],
            "unexpected_eds_elements": row["eds_unexpected_elements"],
            "sem_quantitative_segmentation_status": row[
                "sem_quantitative_segmentation_status"
            ],
        },
        "weaknesses_or_contradictions": [
            "EDS reports unexpected Ni for the source-bound RWGS sample.",
            "Quantitative SEM segmentation is blocked by method mismatch.",
            "Identical physical aliquot identity is not confirmed across measurements.",
            "Nominal composition is not independently confirmed in the consumed bundle.",
        ],
        "next_action_decision": {
            "decision_report_sha256": decision_sha,
            "action_recorded": True,
            "selected_action": "audit_existing_bundle_for_ni_and_sem_provenance",
        },
        "reanalysis": reanalysis,
        "iteration_count": 2,
        "terminal_state": "stopped",
        "terminal_reason": (
            "The current public bundle is exhausted for the targeted provenance audit; "
            "source-backed Ni origin, aliquot identity, nominal composition, and a "
            "method-compatible SEM path are required before stronger interpretation."
        ),
        "scientific_status_changed": False,
        "scientific_promotion_authorized": False,
    }


def build_acceptance(
    *,
    repository_root: Path,
    representative_root: Path,
    rwgs_consumer_root: Path,
    rwgs_bundle_manifest: Path,
    output_dir: Path,
) -> dict[str, Path]:
    repository = repository_root.expanduser().resolve(strict=True)
    representative = representative_root.expanduser().resolve(strict=True)
    rwgs_consumer = rwgs_consumer_root.expanduser().resolve(strict=True)
    bundle = rwgs_bundle_manifest.expanduser().resolve(strict=True)
    output = output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    reports = [
        _nist_episode(
            repository=repository,
            representative=representative,
            output=output,
        ),
        _nasa_episode(repository=repository, output=output),
        _rwgs_episode(
            consumer_root=rwgs_consumer,
            bundle_manifest_path=bundle,
            output=output,
        ),
    ]
    episode_paths: list[Path] = []
    for report in reports:
        path = output / f"episode_{report['episode_id']}.json"
        _write_json(path, report)
        episode_paths.append(path)

    suite = evaluate_real_data_episode_suite(reports, required_full_cycles=3)
    if suite["mvp_acceptance_passed"] is not True:
        raise RuntimeError(f"real-data MVP acceptance failed: {suite}")
    if suite["full_cycle_count"] != 3:
        raise RuntimeError(
            "real-data MVP must contain exactly three qualifying full cycles"
        )
    if suite["full_cycle_family_count"] != 3:
        raise RuntimeError("real-data MVP episode families are not materially different")
    if suite["full_cycle_modality_count"] < 2:
        raise RuntimeError("real-data MVP modality diversity is insufficient")
    if suite["full_cycle_evidence_class_count"] < 2:
        raise RuntimeError("real-data MVP evidence-class diversity is insufficient")
    if suite["scientific_status_changed"] is not False:
        raise RuntimeError("MVP evaluator changed scientific status")
    if suite["human_review_synthesized_here"] is not False:
        raise RuntimeError("MVP evaluator synthesized a human review")

    suite_path = output / "real_data_episode_suite_acceptance.json"
    _write_json(suite_path, suite)
    closeout = {
        "schema_version": "1.0",
        "status": "bounded_autonomous_research_scientist_mvp_complete",
        "mvp_completion_issue": 165,
        "mvp_acceptance_passed": True,
        "qualifying_full_cycle_count": suite["full_cycle_count"],
        "episode_families": sorted(
            evaluation["episode_family_id"] for evaluation in suite["evaluations"]
        ),
        "modalities": sorted(
            evaluation["modality"] for evaluation in suite["evaluations"]
        ),
        "evidence_classes": sorted(
            evaluation["evidence_class"] for evaluation in suite["evaluations"]
        ),
        "remaining_empirical_issues": [76],
        "issue_76_satisfied": False,
        "scientific_hypothesis_verified": False,
        "scientific_status_changed": False,
        "unsupported_scientific_promotion_performed": False,
        "physical_experiment_execution_authorized": False,
        "second_executor_introduced": False,
        "human_review_synthesized": False,
        "completion_scope": (
            "software/system MVP completion under Issue #165; exact new physical AMMT "
            "Stage 1 evidence remains external empirical work under Issue #76"
        ),
        "suite_sha256": _sha256(suite_path),
        "episode_artifacts": [
            {"path": path.name, "sha256": _sha256(path)} for path in episode_paths
        ],
    }
    closeout_path = output / "autonomous_research_scientist_mvp_closeout.json"
    _write_json(closeout_path, closeout)

    report_lines = [
        "# Bounded Autonomous Research Scientist MVP Closeout",
        "",
        "**Status:** `bounded_autonomous_research_scientist_mvp_complete`",
        "",
        "Three materially different real-data episodes passed the fail-closed MVP contract:",
        "",
        "1. NIST AM-Bench 2018-02 IN625 process-design identifiability cycle.",
        "2. NASA battery warm-start generalization and 13-stage external-evidence cycle.",
        "3. Public RWGS XRD/EDS/SEM cross-repository anomaly/provenance cycle.",
        "",
        "All three preserve real source bindings, bounded scientific intake, explicit "
        "weaknesses, next-action records, reanalysis, and bounded stop without unsupported "
        "scientific promotion.",
        "",
        "## Remaining empirical boundary",
        "",
        "Issue #76 remains open. The exact nine new calibrated-actual-power AMMT Stage 1 "
        "traces are not present and were not inferred from adjacent evidence. This does not "
        "block the software/system MVP completion criterion in Issue #165.",
        "",
    ]
    report_path = output / "autonomous_research_scientist_mvp_closeout.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    manifest = {
        "schema_version": "1.0",
        "status": closeout["status"],
        "artifacts": {
            path.name: _sha256(path)
            for path in [*episode_paths, suite_path, closeout_path, report_path]
        },
        "scientific_status_changed": False,
        "physical_experiment_execution_authorized": False,
    }
    manifest_path = output / "autonomous_research_scientist_mvp_manifest.json"
    _write_json(manifest_path, manifest)
    return {
        "suite": suite_path,
        "closeout": closeout_path,
        "report": report_path,
        "manifest": manifest_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build provenance-bound three-episode real-data MVP acceptance."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--representative-root", type=Path, required=True)
    parser.add_argument("--rwgs-consumer-root", type=Path, required=True)
    parser.add_argument("--rwgs-bundle-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    outputs = build_acceptance(
        repository_root=args.repository_root,
        representative_root=args.representative_root,
        rwgs_consumer_root=args.rwgs_consumer_root,
        rwgs_bundle_manifest=args.rwgs_bundle_manifest,
        output_dir=args.output,
    )
    closeout = _json(outputs["closeout"])
    print(json.dumps(closeout, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
