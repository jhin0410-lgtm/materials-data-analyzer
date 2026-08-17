"""End-to-end acceptance for the provenance-aware autonomous research architecture.

The acceptance intentionally distinguishes architectural success from scientific
resolution. It uses the repository's tracked NIST IN625 case for Phases B-E and accepts
Phase A only when deterministic trust/discovery replay acquires bytes without promoting
them to scientific evidence. Missing independent evidence or characterization review is
reported as an empirical gap, never converted into a positive scientific conclusion.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from materials_data_analyzer.characterization_use_contract import (
    CharacterizationUsePolicyError,
    evaluate_characterization_use,
)

from .cross_source_scientific_reasoning import (
    AnalysisTraits,
    ComparabilityContext,
    assess_comparability,
    select_next_analysis,
)
from .epistemic_graph import validate_epistemic_graph
from .scientific_evidence_normalization import (
    MaterialIdentity,
    NormalizedMeasurement,
    ProvenanceLocator,
    build_epistemic_evidence_node,
)
from .scientific_simulation_registry import (
    SimulationPlanningRequest,
    SolverContractRegistry,
    StructuralDesignCandidate,
    compile_simulation_action_candidate,
    repository_design_simulation_contract,
    select_structural_design_candidate,
    structural_design_sensitivity,
)

SCHEMA_VERSION = "1.0"
FINAL_STATUS = "architecture_acceptance_passed_with_empirical_gaps"
UNRESOLVED_ISSUES = (76, 156)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV contains no records: {path}")
    return rows


def _process_signature(row: Mapping[str, str]) -> str:
    return (
        f"system={row['system']};actual_laser_power_w={row['actual_laser_power_w']};"
        f"scan_speed_mm_s={row['scan_speed_mm_s']}"
    )


def _phase_a_acceptance(result: Mapping[str, Any]) -> dict[str, Any]:
    history = result.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("Phase A replay result must contain non-empty history")
    first = history[0]
    if not isinstance(first, Mapping):
        raise ValueError("Phase A replay history is malformed")
    accepted = int(first.get("accepted_intake_count", -1))
    scientific_changed = first.get("scientific_status_changed")
    physical_authorized = result.get("physical_experiment_execution_authorized")
    terminal = str(result.get("terminal_status", ""))
    passed = (
        accepted == 0
        and scientific_changed is False
        and physical_authorized is False
        and terminal == "Insufficient evidence"
    )
    if not passed:
        raise ValueError(
            "Phase A acceptance requires trusted acquisition without scientific promotion"
        )
    return {
        "phase": "A",
        "status": "passed_trusted_replay_without_scientific_promotion",
        "terminal_status": terminal,
        "accepted_scientific_intakes": accepted,
        "scientific_status_changed": False,
        "physical_experiment_execution_authorized": False,
        "replay_scope": "trust_discovery_metadata_and_acquired_bytes_only",
        "synthetic_scientific_measurement_used": False,
    }


def _build_phase_b(
    *,
    process_rows: list[dict[str, str]],
    measurement_rows: list[dict[str, str]],
    measurement_source: Path,
    source_id: str,
    artifact_root: Path,
) -> tuple[dict[str, Any], NormalizedMeasurement, dict[str, Any]]:
    process_by_sample = {row["sample_id"]: row for row in process_rows}
    measurement = measurement_rows[0]
    sample_id = measurement["sample_id"]
    process = process_by_sample[sample_id]
    source_sha = _sha256_file(measurement_source)
    material = MaterialIdentity(
        material_name=process["material"],
        declared_identifier=process["material"],
        identity_basis="source_declared_label",
    )
    normalized = NormalizedMeasurement(
        material=material,
        sample_id=sample_id,
        property_name="melt_pool_width_mean",
        value=float(measurement["melt_pool_width_mean_um"]),
        unit="um",
        method="nist_microscope_control_metrology_mode_reported_table",
        instrument_model="model_not_declared_in_tracked_source_table",
        calibration_id=None,
        process_signature=_process_signature(process),
        standard_uncertainty=None,
        provenance=ProvenanceLocator(
            source_id=source_id,
            artifact_sha256=source_sha,
            record_locator=(
                f"sample_id={sample_id};column=melt_pool_width_mean_um"
            ),
        ),
    )
    evidence = build_epistemic_evidence_node(
        normalized,
        workstream_id="phase-a-e-in625",
        evidence_role="tracked_measurement_source",
        evidence_quality="diagnostic",
    )
    claim = {
        "node_id": "claim:current-design-gate",
        "node_type": "claim",
        "statement": (
            "The current three-condition IN625 design is insufficient for predictive, "
            "causal, or optimization claims."
        ),
    }
    graph = {
        "schema_version": "1.0",
        "graph_id": "phase-a-e-in625-acceptance",
        "research_scope": "NIST IN625 autonomous research architecture acceptance",
        "nodes": [evidence, claim],
        "edges": [],
    }
    program_state = {
        "workstreams": [
            {
                "workstream_id": "phase-a-e-in625",
                "planning_state": {
                    "evidence_bindings": [
                        {
                            "role": "tracked_measurement_source",
                            "sha256": source_sha,
                        }
                    ]
                },
            }
        ]
    }
    validated = validate_epistemic_graph(
        graph,
        program_state=program_state,
        artifact_root=artifact_root,
    )
    metadata = validated["nodes"][0]["metadata"]
    if metadata["material_composition_known"] is not False:
        raise ValueError("Phase B acceptance must not fabricate IN625 composition")
    if metadata["composition_inferred"] is not False:
        raise ValueError("Phase B acceptance inferred a material composition")
    phase = {
        "phase": "B",
        "status": "passed_canonical_identity_and_measurement_normalization",
        "sample_id": sample_id,
        "measurement_id": normalized.measurement_id,
        "material_id": material.material_id,
        "material_identity_kind": metadata["material_identity_kind"],
        "material_composition_known": False,
        "composition_inferred": False,
        "measurement_source_sha256": source_sha,
        "record_locator": normalized.provenance.record_locator,
        "epistemic_graph_validated": True,
        "semantic_inference_performed": False,
    }
    return phase, normalized, graph


def _phase_c_acceptance(
    *,
    normalized: NormalizedMeasurement,
    process_rows: list[dict[str, str]],
    representative_summary: Mapping[str, Any],
) -> dict[str, Any]:
    same_condition = [
        row
        for row in process_rows
        if row["case_id"] == process_rows[0]["case_id"]
    ]
    if len(same_condition) < 2:
        raise ValueError("Phase C acceptance needs two replicated traces")
    left = ComparabilityContext(
        material_id=normalized.material.material_id,
        property_name=normalized.property_name,
        unit=normalized.unit,
        process_signature=_process_signature(same_condition[0]),
        instrument_model=normalized.instrument_model,
        calibration_id=None,
        source_id=normalized.provenance.source_id,
        independence_group=None,
    )
    right = ComparabilityContext(
        material_id=normalized.material.material_id,
        property_name=normalized.property_name,
        unit=normalized.unit,
        process_signature=_process_signature(same_condition[1]),
        instrument_model=normalized.instrument_model,
        calibration_id=None,
        source_id=normalized.provenance.source_id,
        independence_group=None,
    )
    independence = assess_comparability(
        left,
        right,
        require_independence=True,
    )
    if independence.comparable:
        raise ValueError("Same-source NIST traces must not be treated as independent sources")

    audit = representative_summary["components"]["process_design_audit"]
    if audit["readiness"] != "not_ready_for_predictive_or_causal_modeling":
        raise ValueError("Representative design readiness gate changed unexpectedly")
    recommendation = select_next_analysis(
        AnalysisTraits(
            n_samples=10,
            n_numeric_predictors=2,
            target_kind="continuous",
            group_count=int(audit["unique_condition_count"]),
            design_identifiable=False,
        )
    )
    if recommendation.analysis_type != "design_identifiability_audit":
        raise ValueError("Phase C must audit identifiability before regression")
    return {
        "phase": "C",
        "status": "passed_fail_closed_reasoning_and_identifiability_gate",
        "unique_process_conditions": int(audit["unique_condition_count"]),
        "modeling_readiness": audit["readiness"],
        "same_source_independence_accepted": False,
        "independence_block_reasons": list(independence.reasons),
        "selected_analysis": recommendation.analysis_type,
        "bounded_regression_authorized": False,
        "verified_directional_contradiction_eligible": False,
    }


def _phase_d_acceptance(case_manifest: Path) -> dict[str, Any]:
    try:
        eligibility = evaluate_characterization_use(
            case_manifest,
            requested_use="descriptive",
        )
    except CharacterizationUsePolicyError as exc:
        return {
            "phase": "D",
            "status": "passed_fail_closed_missing_downstream_use_contract",
            "characterization_normalized_into_scientific_evidence": False,
            "reviewed_status_claimed": False,
            "block_reason": str(exc),
            "empirical_gap": (
                "The tracked NIST case predates the explicit characterization "
                "downstream-use contract required for Phase D scientific promotion."
            ),
        }
    if eligibility.review_status != "reviewed":
        return {
            "phase": "D",
            "status": "passed_fail_closed_review_required",
            "characterization_normalized_into_scientific_evidence": False,
            "reviewed_status_claimed": False,
            "policy_source": eligibility.policy_source,
            "review_status": eligibility.review_status,
            "evidence_level": eligibility.evidence_level,
            "block_reason": "characterization evidence requires reviewed status",
        }
    raise ValueError(
        "Phase D acceptance unexpectedly found reviewed characterization authorization"
    )


def _design_config(
    *,
    observed_cells: list[dict[str, Any]],
    proposed_cells: list[dict[str, Any]],
    simulation_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "simulation_id": simulation_id,
        "research_question": (
            "Which source-derived NIST IN625 design augmentation improves structural "
            "estimability without using response values?"
        ),
        "factors": [
            {"name": "actual_laser_power_w", "unit": "W"},
            {"name": "scan_speed_mm_s", "unit": "mm/s"},
        ],
        "observed_cells": observed_cells,
        "proposed_cells": proposed_cells,
        "models": ["main_effects", "interaction", "quadratic"],
        "scientific_boundary": {
            "response_values_allowed": False,
            "coefficient_estimation_allowed": False,
            "effect_size_estimation_allowed": False,
            "predictive_modeling_allowed": False,
            "causal_inference_allowed": False,
            "optimization_allowed": False,
            "engineering_decision_allowed": False,
        },
    }


def _observed_cells(process_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    coordinates = Counter(
        (
            float(row["actual_laser_power_w"]),
            float(row["scan_speed_mm_s"]),
        )
        for row in process_rows
    )
    return [
        {
            "cell_id": f"observed-{index:02d}",
            "factor_values": {
                "actual_laser_power_w": power,
                "scan_speed_mm_s": speed,
            },
            "replicates": count,
        }
        for index, ((power, speed), count) in enumerate(
            sorted(coordinates.items()),
            start=1,
        )
    ]


def _proposed_cells(
    conditions: list[Mapping[str, Any]],
    *,
    prefix: str,
    replicates: int,
) -> list[dict[str, Any]]:
    return [
        {
            "cell_id": f"{prefix}-{index:02d}",
            "factor_values": {
                "actual_laser_power_w": float(row["actual_laser_power_w"]),
                "scan_speed_mm_s": float(row["scan_speed_mm_s"]),
            },
            "replicates": replicates,
        }
        for index, row in enumerate(conditions, start=1)
    ]


def _phase_e_acceptance(
    *,
    process_rows: list[dict[str, str]],
    plan: Mapping[str, Any],
    graph: Mapping[str, Any],
) -> dict[str, Any]:
    observed = _observed_cells(process_rows)
    replication = int(
        plan["replication_policy"][
            "recommended_minimum_trace_replicates_per_new_condition"
        ]
    )
    stage_1 = plan["stages"]["stage_1_complete_observed_grid"]
    stage_2 = plan["stages"]["stage_2_add_midpoint_power"]
    stage_1_cells = _proposed_cells(
        stage_1["conditions"],
        prefix="stage1",
        replicates=replication,
    )
    stage_2_cells = _proposed_cells(
        stage_2["conditions"],
        prefix="stage2",
        replicates=replication,
    )
    stage_1_cost = float(stage_1["planned_new_trace_count"])
    cumulative_cost = stage_1_cost + float(stage_2["planned_new_trace_count"])
    candidates = (
        StructuralDesignCandidate(
            "stage_1_complete_observed_grid",
            _design_config(
                observed_cells=observed,
                proposed_cells=stage_1_cells,
                simulation_id="phase-a-e-stage-1",
            ),
            stage_1_cost,
        ),
        StructuralDesignCandidate(
            "stage_1_plus_stage_2",
            _design_config(
                observed_cells=observed,
                proposed_cells=stage_1_cells + stage_2_cells,
                simulation_id="phase-a-e-stage-1-plus-2",
            ),
            cumulative_cost,
        ),
    )
    assessments = structural_design_sensitivity(candidates)
    priority = select_structural_design_candidate(
        candidates,
        remaining_budget=stage_1_cost,
    )
    if priority["selected_candidate_id"] != "stage_1_complete_observed_grid":
        raise ValueError("Phase E structural priority no longer matches bounded Stage 1")
    if priority["expected_information_gain"] != {
        "status": "not_quantified",
        "value": None,
    }:
        raise ValueError("Phase E fabricated probabilistic expected information gain")

    registry = SolverContractRegistry()
    contract = repository_design_simulation_contract()
    from .design_simulation import simulate_design_structure

    registry.register_attested(
        contract,
        implementation=simulate_design_structure,
    )
    evidence_node_id = str(graph["nodes"][0]["node_id"])
    action = compile_simulation_action_candidate(
        registry,
        SimulationPlanningRequest(
            request_id="phase-a-e-stage-1-plan",
            solver_id=contract.solver_id,
            upstream_evidence_node_ids=(evidence_node_id,),
            target_node_id="claim:current-design-gate",
        ),
        graph,
    )
    if action["execution_performed"] is not False:
        raise ValueError("Phase E planner unexpectedly executed a simulation action")
    if action["second_executor_introduced"] is not False:
        raise ValueError("Phase E introduced a second executor")
    return {
        "phase": "E",
        "status": "passed_response_free_structural_prioritization",
        "existing_solver_contract_attested": True,
        "structural_assessments": [
            {
                "candidate_id": item.candidate_id,
                "rank_gain": item.rank_gain,
                "residual_df_gain": item.residual_df_gain,
                "new_unique_cell_count": item.new_unique_cell_count,
                "structural_utility": item.structural_utility,
                "cost_units": item.cost_units,
                "expected_information_gain_status": (
                    item.expected_information_gain_status
                ),
            }
            for item in assessments
        ],
        "selected_candidate_id": priority["selected_candidate_id"],
        "immediate_budget_proxy": {
            "unit": "planned_new_trace_count",
            "value": stage_1_cost,
        },
        "expected_information_gain": priority["expected_information_gain"],
        "execution_route": action["execution_route"],
        "execution_performed": False,
        "second_executor_introduced": False,
        "physical_experiment_execution_authorized": False,
        "scientific_status_upgrade_authorized": False,
        "response_values_used_for_structural_priority": False,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Phase A-E Autonomous Research Acceptance",
        "",
        f"**Status:** `{summary['status']}`",
        "",
        "This is an architecture acceptance, not a verified materials-science conclusion.",
        "",
        "## Phase results",
        "",
    ]
    for key in ("A", "B", "C", "D", "E"):
        phase = summary["phases"][key]
        lines.append(f"- **Phase {key}:** `{phase['status']}`")
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "- No material composition was inferred for source-declared IN625.",
            "- Same-source replicated traces were not promoted to independent evidence.",
            "- Regression remains blocked until design identifiability is verified.",
            "- Characterization promotion remains blocked without the required reviewed policy contract.",
            "- Structural simulation used no response values and did not quantify EIG.",
            "- No second executor or physical instrument execution path was introduced.",
            "",
            "## Unresolved empirical gaps",
            "",
            "- #76: exact independent NIST AMMT cross-process IN625 evidence remains incomplete.",
            "- #156: actual NIST MDS2-2923 semantic/review-gated characterization binding remains incomplete.",
            "",
            "The acceptance therefore does not close either issue and does not mark the scientific hypothesis verified.",
            "",
        ]
    )
    return "\n".join(lines)


def build_phase_a_e_acceptance(
    *,
    phase_a_result: Mapping[str, Any],
    representative_root: str | Path,
    repository_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Evaluate all architecture phases against one provenance-bound NIST IN625 run."""
    repository = Path(repository_root).expanduser().resolve(strict=True)
    representative = Path(representative_root).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    representative_summary_path = representative / "representative_workflow_summary.json"
    representative_summary = _read_json(representative_summary_path)
    process_source = (
        repository
        / "data"
        / "case_studies"
        / "nist_ambench_2018_02"
        / "source_process_conditions.csv"
    )
    measurement_source = (
        repository
        / "data"
        / "case_studies"
        / "nist_ambench_2018_02"
        / "source_melt_pool_measurements.csv"
    )
    case_manifest = representative / "01_verified_case" / "ambench_case_study_manifest.json"
    plan_relative = representative_summary["components"]["minimum_design_plan"]["plan"]
    plan_path = representative / str(plan_relative)
    plan = _read_json(plan_path)
    case = _read_json(case_manifest)
    process_rows = _read_csv(process_source)
    measurement_rows = _read_csv(measurement_source)
    source_id = str(case["source"]["dataset_doi"])

    phase_a = _phase_a_acceptance(phase_a_result)
    phase_b, normalized, graph = _build_phase_b(
        process_rows=process_rows,
        measurement_rows=measurement_rows,
        measurement_source=measurement_source,
        source_id=source_id,
        artifact_root=output,
    )
    phase_c = _phase_c_acceptance(
        normalized=normalized,
        process_rows=process_rows,
        representative_summary=representative_summary,
    )
    phase_d = _phase_d_acceptance(case_manifest)
    phase_e = _phase_e_acceptance(
        process_rows=process_rows,
        plan=plan,
        graph=graph,
    )

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": FINAL_STATUS,
        "architecture_acceptance_passed": True,
        "scientific_hypothesis_verified": False,
        "phases": {
            "A": phase_a,
            "B": phase_b,
            "C": phase_c,
            "D": phase_d,
            "E": phase_e,
        },
        "source_bindings": {
            "process_source": {
                "path": process_source.relative_to(repository).as_posix(),
                "sha256": _sha256_file(process_source),
            },
            "measurement_source": {
                "path": measurement_source.relative_to(repository).as_posix(),
                "sha256": _sha256_file(measurement_source),
            },
            "representative_workflow_summary": {
                "path": representative_summary_path.name,
                "sha256": _sha256_file(representative_summary_path),
            },
            "design_plan": {
                "path": str(plan_relative),
                "sha256": _sha256_file(plan_path),
            },
        },
        "unresolved_github_issues": list(UNRESOLVED_ISSUES),
        "scientific_boundary": {
            "network_required_for_acceptance": False,
            "synthetic_scientific_measurements_used": False,
            "missing_material_composition_inferred": False,
            "same_source_replication_treated_as_independent": False,
            "response_model_fitted": False,
            "causal_inference_performed": False,
            "optimization_performed": False,
            "expected_information_gain_quantified": False,
            "second_executor_introduced": False,
            "physical_experiment_execution_authorized": False,
            "characterization_review_fabricated": False,
        },
    }
    summary_path = output / "phase_a_e_acceptance_summary.json"
    report_path = output / "phase_a_e_acceptance_report.md"
    manifest_path = output / "phase_a_e_acceptance_manifest.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_build_report(summary), encoding="utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workflow": "phase_a_e_autonomous_research_acceptance",
        "status": FINAL_STATUS,
        "summary": summary_path.name,
        "summary_sha256": _sha256_file(summary_path),
        "report": report_path.name,
        "report_sha256": _sha256_file(report_path),
        "network_access_performed": False,
        "scientific_hypothesis_verified": False,
        "unresolved_github_issues": list(UNRESOLVED_ISSUES),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "summary": summary_path,
        "report": report_path,
        "manifest": manifest_path,
    }


__all__ = [
    "FINAL_STATUS",
    "SCHEMA_VERSION",
    "UNRESOLVED_ISSUES",
    "build_phase_a_e_acceptance",
]
