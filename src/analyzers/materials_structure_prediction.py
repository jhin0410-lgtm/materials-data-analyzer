"""Known-structure Materials predictive comparison utilities.

This module evaluates whether already-known relaxed structure descriptors add
incremental predictive value for the existing Materials Project validation
cohort. It never calls the network, never overwrites the original v1.3 target,
and never uses graph artifacts as model inputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .grouped_regression_validation import (
    ModelConfig,
    SplitConfig,
    default_model_configs,
    default_split_configs,
    generate_splits,
)
from .materials_physics_features import CONTROL_FEATURE_COLUMNS, PHYSICS_FEATURE_COLUMNS


SCHEMA_VERSION = "2.2.5"
DEFAULT_OUTPUT_DIR = Path("outputs/materials_structure_prediction_v2_2")
DEFAULT_ANALYSIS_READY_PATH = Path("data/processed/materials_project_v1_3_analysis_ready.csv")
DEFAULT_VALIDATION_SPEC_PATH = Path("data/case_studies/materials_project/validation_spec_v1_3.json")
DEFAULT_PHYSICS_FEATURE_MATRIX_PATH = Path("outputs/materials_physics_v2_2/materials_physics_v2_2_feature_matrix.csv")
DEFAULT_STRUCTURE_DESCRIPTOR_PATH = Path("outputs/materials_project_structure_v2_2/descriptors/structure_descriptors.csv")
DEFAULT_SNAPSHOT_ALIGNMENT_PATH = Path("outputs/materials_project_structure_v2_2/validation/snapshot_alignment.csv")
DEFAULT_V2_2_4_SUMMARY_PATH = Path("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json")
TARGET_COLUMN = "energy_above_hull"
IDENTIFIER_COLUMN = "material_id"
PRIMARY_GROUP_SPLITS = ("reduced_formula_group", "chemical_system_group")
FORBIDDEN_FEATURE_TOKENS = (
    "material_id",
    "energy_above_hull",
    "target",
    "current_target",
    "target_difference",
    "alignment",
    "formation_energy",
    "energy_per_atom",
    "total_energy",
    "is_stable",
    "decomposition",
    "equilibrium_reaction",
    "prediction",
    "residual",
    "graph_checksum",
    "entity_id",
)
STRUCTURE_NUMERIC_FEATURES = (
    "structure_volume_per_atom",
    "structure_density",
    "ordered_structure_flag",
    "nearest_neighbor_distance_mean",
    "nearest_neighbor_distance_std",
    "nearest_neighbor_distance_cv",
    "coordination_number_mean",
    "coordination_number_std",
)
STRUCTURE_CATEGORICAL_FEATURES = (
    "crystal_system_category",
    "space_group_number_category",
)
STRUCTURE_EXCLUDED_DESCRIPTORS = (
    "packing_fraction_candidate",
    "site_count",
    "raw_lattice_primary_feature",
    "target_accessed",
)
COMPARISON_PAIRS = (
    ("A_vs_B", "known_structure_composition_baseline_v1", "known_structure_composition_physics_v1"),
    ("A_vs_D", "known_structure_composition_baseline_v1", "known_structure_baseline_plus_structure_v1"),
    ("B_vs_E", "known_structure_composition_physics_v1", "known_structure_full_combined_v1"),
    ("C_vs_D", "known_structure_structure_only_v1", "known_structure_baseline_plus_structure_v1"),
    ("D_vs_E", "known_structure_baseline_plus_structure_v1", "known_structure_full_combined_v1"),
)


@dataclass(frozen=True)
class KnownStructurePredictionRequest:
    analysis_ready_path: Path = DEFAULT_ANALYSIS_READY_PATH
    validation_spec_path: Path = DEFAULT_VALIDATION_SPEC_PATH
    physics_feature_matrix_path: Path = DEFAULT_PHYSICS_FEATURE_MATRIX_PATH
    structure_descriptor_path: Path = DEFAULT_STRUCTURE_DESCRIPTOR_PATH
    snapshot_alignment_path: Path = DEFAULT_SNAPSHOT_ALIGNMENT_PATH
    v2_2_4_summary_path: Path = DEFAULT_V2_2_4_SUMMARY_PATH
    output_dir: Path = DEFAULT_OUTPUT_DIR
    confidence_level: float = 0.90
    random_state: int = 42
    exact_match_sensitivity: bool = True
    overwrite: bool = True
    tracked_cohort_summary_path: Path = Path("data/processed/materials_v2_2_5_known_structure_cohort_summary.json")
    tracked_feature_set_snapshot_path: Path = Path("data/processed/materials_v2_2_5_feature_set_snapshot.csv")
    tracked_comparison_summary_path: Path = Path("data/processed/materials_v2_2_5_predictive_comparison_summary.csv")
    tracked_paired_summary_path: Path = Path("data/processed/materials_v2_2_5_paired_metric_summary.csv")
    tracked_uncertainty_summary_path: Path = Path("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv")
    tracked_decision_path: Path = Path("data/processed/materials_v2_2_5_predictive_value_decision.json")
    tracked_feature_use_evidence_path: Path = Path("data/processed/materials_v2_2_5_feature_use_evidence.json")
    tracked_report_summary_path: Path = Path("data/processed/materials_v2_2_5_report_summary.md")


def request_from_config(config: Mapping[str, Any]) -> KnownStructurePredictionRequest:
    """Build a request from a small JSON config."""
    return KnownStructurePredictionRequest(
        analysis_ready_path=Path(config.get("analysis_ready_path", DEFAULT_ANALYSIS_READY_PATH.as_posix())),
        validation_spec_path=Path(config.get("validation_spec_path", DEFAULT_VALIDATION_SPEC_PATH.as_posix())),
        physics_feature_matrix_path=Path(config.get("physics_feature_matrix_path", DEFAULT_PHYSICS_FEATURE_MATRIX_PATH.as_posix())),
        structure_descriptor_path=Path(config.get("structure_descriptor_path", DEFAULT_STRUCTURE_DESCRIPTOR_PATH.as_posix())),
        snapshot_alignment_path=Path(config.get("snapshot_alignment_path", DEFAULT_SNAPSHOT_ALIGNMENT_PATH.as_posix())),
        v2_2_4_summary_path=Path(config.get("v2_2_4_summary_path", DEFAULT_V2_2_4_SUMMARY_PATH.as_posix())),
        output_dir=Path(config.get("output_dir", DEFAULT_OUTPUT_DIR.as_posix())),
        confidence_level=float(config.get("confidence_level", 0.90)),
        random_state=int(config.get("random_state", 42)),
        exact_match_sensitivity=bool(config.get("exact_match_sensitivity", True)),
        overwrite=bool(config.get("overwrite", True)),
    )


def calculate_file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object expected: {path}")
    return payload


def preview_known_structure_comparison(request: KnownStructurePredictionRequest) -> dict[str, Any]:
    """Preview expected inputs without building outputs or fitting models."""
    missing = [path.as_posix() for path in _required_input_paths(request) if not path.exists()]
    spec = load_json(request.validation_spec_path) if request.validation_spec_path.exists() else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked_missing_artifact" if missing else "ready_for_local_comparison",
        "prediction_context": "known_structure_post_relaxation",
        "network_required": False,
        "model_training_required": True,
        "graph_model_used": False,
        "missing_inputs": missing,
        "feature_sets": list(_feature_set_ids()),
        "split_strategies": [item.get("name") for item in spec.get("split_strategies", [])] or [cfg.name for cfg in default_split_configs()],
        "target_source": "original_v1_3_energy_above_hull",
    }


def build_known_structure_cohort(request: KnownStructurePredictionRequest) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build matched known-structure cohort without mutating source artifacts."""
    _assert_required_inputs(request)
    analysis = pd.read_csv(request.analysis_ready_path)
    physics = pd.read_csv(request.physics_feature_matrix_path)
    structure = pd.read_csv(request.structure_descriptor_path)
    alignment = pd.read_csv(request.snapshot_alignment_path)
    spec = load_json(request.validation_spec_path)
    v2_2_4 = load_json(request.v2_2_4_summary_path)
    baseline_features = _baseline_features(spec)
    physics_features = list(PHYSICS_FEATURE_COLUMNS + CONTROL_FEATURE_COLUMNS)
    missing_baseline = sorted(set(baseline_features) - set(analysis.columns))
    if missing_baseline:
        raise ValueError("baseline feature(s) missing from analysis-ready data: " + ", ".join(missing_baseline))
    _require_unique_material_id(analysis, "analysis_ready")
    _require_unique_material_id(physics, "physics_feature_matrix")
    _require_unique_material_id(structure, "structure_descriptors")
    _require_unique_material_id(alignment, "snapshot_alignment")
    if TARGET_COLUMN not in analysis.columns:
        raise ValueError("original target missing from analysis-ready data")
    aligned = alignment[
        alignment["comparison_status"].isin(["target_exact_match", "target_within_numeric_tolerance"])
    ][["material_id", "comparison_status"]].copy()
    physics_valid = physics[physics["feature_build_status"].eq("generated")].copy()
    physics_renamed = physics_valid[["material_id", *physics_features]].rename(
        columns={column: _physics_column_name(column, analysis) for column in physics_features}
    )
    selected_structure_columns = [*STRUCTURE_NUMERIC_FEATURES, *STRUCTURE_CATEGORICAL_FEATURES]
    missing_structure = sorted(set(selected_structure_columns) - set(structure.columns))
    if missing_structure:
        raise ValueError("structure descriptor column(s) missing: " + ", ".join(missing_structure))
    structure_valid = structure[["material_id", *selected_structure_columns, "target_accessed"]].copy()
    structure_valid = structure_valid[~structure_valid["target_accessed"].astype(str).str.lower().eq("true")]
    structure_valid = structure_valid.drop(columns=["target_accessed"])
    cohort = (
        analysis.merge(aligned, on="material_id", how="inner", validate="one_to_one")
        .merge(physics_renamed, on="material_id", how="inner", validate="one_to_one")
        .merge(structure_valid, on="material_id", how="inner", validate="one_to_one")
    )
    if cohort[TARGET_COLUMN].isna().any():
        raise ValueError("cohort target contains missing values")
    forbidden = forbidden_feature_audit(cohort.columns)
    if forbidden["forbidden_feature_columns"]:
        raise ValueError("forbidden feature-like columns present in cohort: " + ", ".join(forbidden["forbidden_feature_columns"]))
    structure_numeric = [column for column in STRUCTURE_NUMERIC_FEATURES if column in cohort.columns]
    structure_categorical = [column for column in STRUCTURE_CATEGORICAL_FEATURES if column in cohort.columns]
    physics_columns = [_physics_column_name(column, analysis) for column in physics_features]
    feature_sets = build_feature_sets(
        baseline_features=baseline_features,
        physics_features=physics_columns,
        structure_numeric=structure_numeric,
        structure_categorical=structure_categorical,
    )
    for feature_set in feature_sets.values():
        missing = sorted(set(feature_set["numeric_features"] + feature_set["categorical_features"]) - set(cohort.columns))
        if missing:
            raise ValueError(f"{feature_set['feature_set_id']} missing columns: " + ", ".join(missing))
    summary = {
        "schema_version": SCHEMA_VERSION,
        "prediction_context": "known_structure_post_relaxation",
        "target_source": "original_v1_3_energy_above_hull",
        "analysis_ready_rows": int(len(analysis)),
        "snapshot_aligned_rows": int(len(aligned)),
        "cohort_rows": int(len(cohort)),
        "exact_match_rows": int(cohort["comparison_status"].eq("target_exact_match").sum()),
        "within_tolerance_rows": int(cohort["comparison_status"].eq("target_within_numeric_tolerance").sum()),
        "v2_2_4_decision_status": v2_2_4.get("decision_status"),
        "feature_sets": {key: {"feature_count": len(value["numeric_features"]) + len(value["categorical_features"])} for key, value in feature_sets.items()},
        "forbidden_feature_audit": forbidden,
        "original_target_overwritten": False,
        "current_target_used_as_target": False,
        "graph_artifact_used_as_feature": False,
    }
    return cohort.reset_index(drop=True), summary


def build_feature_sets(
    *,
    baseline_features: list[str],
    physics_features: list[str],
    structure_numeric: list[str],
    structure_categorical: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        "known_structure_composition_baseline_v1": {
            "feature_set_id": "known_structure_composition_baseline_v1",
            "label": "A",
            "numeric_features": list(baseline_features),
            "categorical_features": [],
            "role": "composition_baseline",
        },
        "known_structure_composition_physics_v1": {
            "feature_set_id": "known_structure_composition_physics_v1",
            "label": "B",
            "numeric_features": list(dict.fromkeys([*baseline_features, *physics_features])),
            "categorical_features": [],
            "role": "composition_baseline_plus_composition_physics",
        },
        "known_structure_structure_only_v1": {
            "feature_set_id": "known_structure_structure_only_v1",
            "label": "C",
            "numeric_features": list(structure_numeric),
            "categorical_features": list(structure_categorical),
            "role": "structure_only",
        },
        "known_structure_baseline_plus_structure_v1": {
            "feature_set_id": "known_structure_baseline_plus_structure_v1",
            "label": "D",
            "numeric_features": list(dict.fromkeys([*baseline_features, *structure_numeric])),
            "categorical_features": list(structure_categorical),
            "role": "composition_baseline_plus_structure",
        },
        "known_structure_full_combined_v1": {
            "feature_set_id": "known_structure_full_combined_v1",
            "label": "E",
            "numeric_features": list(dict.fromkeys([*baseline_features, *physics_features, *structure_numeric])),
            "categorical_features": list(structure_categorical),
            "role": "composition_baseline_plus_composition_physics_plus_structure",
        },
    }


def run_known_structure_comparison(request: KnownStructurePredictionRequest) -> dict[str, Any]:
    """Run local known-structure feature-set comparison and write artifacts."""
    input_shas = {path.name: calculate_file_sha256(path) for path in _required_input_paths(request)}
    cohort, cohort_summary = build_known_structure_cohort(request)
    spec = load_json(request.validation_spec_path)
    baseline_features = _baseline_features(spec)
    physics_features = [_resolved_physics_column(column, cohort.columns) for column in PHYSICS_FEATURE_COLUMNS + CONTROL_FEATURE_COLUMNS]
    structure_numeric = [column for column in STRUCTURE_NUMERIC_FEATURES if column in cohort.columns]
    structure_categorical = [column for column in STRUCTURE_CATEGORICAL_FEATURES if column in cohort.columns]
    feature_sets = build_feature_sets(
        baseline_features=baseline_features,
        physics_features=physics_features,
        structure_numeric=structure_numeric,
        structure_categorical=structure_categorical,
    )
    split_configs = _split_configs_from_spec(spec)
    model_configs = default_model_configs(random_state=int(spec.get("random_state", request.random_state)))
    all_splits = {split_config.name: generate_splits(cohort, split_config) for split_config in split_configs}
    split_assignment_rows = _split_assignment_rows(cohort, all_splits)
    metrics_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    interval_rows: list[dict[str, Any]] = []
    split_diagnostic_rows: list[dict[str, Any]] = []
    for split_config in split_configs:
        for split in all_splits[split_config.name]:
            split_diagnostic_rows.append(_split_diagnostics(cohort, split, split_config))
            if split["status"] != "valid":
                continue
            for feature_set_id, feature_set in feature_sets.items():
                for model_config in model_configs:
                    result = _evaluate_one(
                        cohort,
                        feature_set,
                        split,
                        split_config,
                        model_config,
                        confidence_level=request.confidence_level,
                        random_state=request.random_state,
                    )
                    metrics_rows.append(result["metrics"])
                    prediction_rows.extend(result["predictions"])
                    interval_rows.append(result["interval"])
    metrics = pd.DataFrame(metrics_rows)
    predictions = pd.DataFrame(prediction_rows)
    intervals = pd.DataFrame(interval_rows)
    split_diagnostics = pd.DataFrame(split_diagnostic_rows)
    feature_snapshot = feature_set_snapshot(feature_sets, request)
    paired = paired_metric_summary(metrics)
    comparison_summary = predictive_comparison_summary(metrics)
    uncertainty_summary = prediction_uncertainty_summary(intervals)
    exact_sensitivity = _run_exact_match_sensitivity(
        request,
        cohort,
        feature_sets,
        split_configs,
        model_configs,
        request.confidence_level,
    ) if request.exact_match_sensitivity else pd.DataFrame()
    decision = predictive_value_decision(
        cohort_summary=cohort_summary,
        comparison_summary=comparison_summary,
        paired_summary=paired,
        uncertainty_summary=uncertainty_summary,
        exact_sensitivity=exact_sensitivity,
        input_shas=input_shas,
    )
    paths = _local_paths(request.output_dir)
    _write_csv(cohort, paths["cohort"], request.overwrite)
    _write_csv(pd.DataFrame([{"material_id": "", "exclusion_reason": "none", "row_count": 0}]), paths["exclusion_manifest"], request.overwrite)
    _write_json(cohort_summary, paths["cohort_manifest"], request.overwrite)
    _write_feature_set_files(cohort, feature_sets, paths["features_dir"], request.overwrite)
    _write_json({"schema_version": SCHEMA_VERSION, "feature_sets": feature_sets}, paths["feature_set_manifest"], request.overwrite)
    _write_csv(pd.DataFrame(split_assignment_rows), paths["split_assignments"], request.overwrite)
    _write_json({"schema_version": SCHEMA_VERSION, "split_strategies": [cfg.__dict__ for cfg in split_configs]}, paths["split_manifest"], request.overwrite)
    _write_csv(metrics, paths["fold_metrics"], request.overwrite)
    _write_csv(predictions, paths["predictions"], request.overwrite)
    _write_csv(intervals, paths["prediction_intervals"], request.overwrite)
    _write_csv(paired, paths["paired_deltas"], request.overwrite)
    _write_csv(comparison_summary, paths["aggregate_metrics"], request.overwrite)
    _write_csv(uncertainty_summary, paths["uncertainty_summary"], request.overwrite)
    _write_csv(split_diagnostics, paths["split_diagnostics"], request.overwrite)
    _write_json(decision, paths["local_decision"], request.overwrite)
    _write_text(render_known_structure_report(decision, comparison_summary, paired, uncertainty_summary), paths["local_report"], request.overwrite)
    _write_plots(comparison_summary, paired, uncertainty_summary, request.output_dir / "reports" / "plots")
    _write_json(cohort_summary, request.tracked_cohort_summary_path, request.overwrite)
    _write_csv(feature_snapshot, request.tracked_feature_set_snapshot_path, request.overwrite)
    _write_csv(comparison_summary, request.tracked_comparison_summary_path, request.overwrite)
    _write_csv(paired, request.tracked_paired_summary_path, request.overwrite)
    _write_csv(uncertainty_summary, request.tracked_uncertainty_summary_path, request.overwrite)
    _write_json(decision, request.tracked_decision_path, request.overwrite)
    _write_json(feature_use_evidence(decision), request.tracked_feature_use_evidence_path, request.overwrite)
    _write_text(render_report_summary(decision), request.tracked_report_summary_path, request.overwrite)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "prediction_context": "known_structure_post_relaxation",
        "input_shas": input_shas,
        "cohort_rows": int(len(cohort)),
        "feature_sets": list(feature_sets),
        "local_outputs": {key: value.as_posix() for key, value in paths.items() if isinstance(value, Path)},
        "tracked_outputs": {
            "cohort_summary": request.tracked_cohort_summary_path.as_posix(),
            "feature_set_snapshot": request.tracked_feature_set_snapshot_path.as_posix(),
            "comparison_summary": request.tracked_comparison_summary_path.as_posix(),
            "paired_summary": request.tracked_paired_summary_path.as_posix(),
            "uncertainty_summary": request.tracked_uncertainty_summary_path.as_posix(),
            "decision": request.tracked_decision_path.as_posix(),
            "feature_use_evidence": request.tracked_feature_use_evidence_path.as_posix(),
            "report_summary": request.tracked_report_summary_path.as_posix(),
        },
        "decision_status": decision["structure_predictive_value_status"],
        "representative_model_selected": decision["representative_model_selected"],
    }
    _write_json(manifest, paths["manifest"], request.overwrite)
    for path in [
        request.tracked_cohort_summary_path,
        request.tracked_feature_set_snapshot_path,
        request.tracked_comparison_summary_path,
        request.tracked_paired_summary_path,
        request.tracked_uncertainty_summary_path,
        request.tracked_decision_path,
        request.tracked_feature_use_evidence_path,
        request.tracked_report_summary_path,
    ]:
        _assert_no_sensitive_or_row_level_payload(path)
    return manifest


def feature_set_snapshot(feature_sets: Mapping[str, Mapping[str, Any]], request: KnownStructurePredictionRequest) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature_set_id, feature_set in feature_sets.items():
        for role, columns in [
            ("numeric", feature_set["numeric_features"]),
            ("categorical", feature_set["categorical_features"]),
        ]:
            for column in columns:
                rows.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "feature_set_id": feature_set_id,
                        "feature_set_label": feature_set["label"],
                        "feature_id": column,
                        "feature_role": role,
                        "prediction_context": "known_structure_post_relaxation",
                        "target_source": "original_v1_3_energy_above_hull",
                        "availability_timing": "known_relaxed_structure_required" if column in STRUCTURE_NUMERIC_FEATURES + STRUCTURE_CATEGORICAL_FEATURES else "composition_available",
                        "leakage_status": "allowed_feature",
                        "preprocessing_policy": "train_fold_only",
                    }
                )
    return pd.DataFrame(rows)


def forbidden_feature_audit(columns: Iterable[str]) -> dict[str, Any]:
    allowed_metadata = {
        "material_id",
        TARGET_COLUMN,
        "reduced_formula_group",
        "chemical_system_group",
        "formula_pretty",
        "theoretical",
        "comparison_status",
        "descriptor_quality_status",
        "descriptor_issue_count",
        "descriptor_issues",
    }
    forbidden = []
    for column in columns:
        lowered = str(column).lower()
        if column in allowed_metadata:
            continue
        if any(token in lowered for token in FORBIDDEN_FEATURE_TOKENS):
            forbidden.append(str(column))
    return {
        "forbidden_feature_columns": sorted(set(forbidden)),
        "graph_artifact_loaded_as_feature": False,
        "current_target_used": False,
        "original_target_source_only": True,
    }


def paired_metric_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    key_cols = ["split_strategy", "split_index", "model_variant"]
    for pair_id, baseline_id, candidate_id in COMPARISON_PAIRS:
        base = metrics[metrics["feature_set_id"].eq(baseline_id)].copy()
        cand = metrics[metrics["feature_set_id"].eq(candidate_id)].copy()
        merged = base.merge(cand, on=key_cols, suffixes=("_baseline", "_candidate"))
        for (split_strategy, model_variant), group in merged.groupby(["split_strategy", "model_variant"]):
            mae_delta = group["mae_baseline"] - group["mae_candidate"]
            rmse_delta = group["rmse_baseline"] - group["rmse_candidate"]
            r2_delta = group["r2_candidate"] - group["r2_baseline"]
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "comparison_id": pair_id,
                    "baseline_feature_set": baseline_id,
                    "candidate_feature_set": candidate_id,
                    "split_strategy": split_strategy,
                    "model_variant": model_variant,
                    "valid_fold_count": int(len(group)),
                    "mae_improvement_mean": _float(mae_delta.mean()),
                    "mae_improvement_median": _float(mae_delta.median()),
                    "mae_improvement_std": _float(mae_delta.std(ddof=0)),
                    "mae_improvement_min": _float(mae_delta.min()),
                    "mae_improvement_max": _float(mae_delta.max()),
                    "rmse_improvement_mean": _float(rmse_delta.mean()),
                    "rmse_improvement_median": _float(rmse_delta.median()),
                    "r2_delta_mean": _float(r2_delta.mean()),
                    "r2_delta_median": _float(r2_delta.median()),
                    "improved_fold_fraction_mae": _float((mae_delta > 0).mean()),
                    "improved_fold_fraction_rmse": _float((rmse_delta > 0).mean()),
                    "improvement_sign_convention": "positive_means_candidate_better",
                    "status": "valid",
                }
            )
    return pd.DataFrame(rows)


def predictive_comparison_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if metrics.empty:
        return pd.DataFrame(rows)
    metric_cols = ["mae", "rmse", "r2", "median_absolute_error"]
    for (feature_set_id, split_strategy, model_variant), group in metrics.groupby(["feature_set_id", "split_strategy", "model_variant"]):
        for metric in metric_cols:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "feature_set_metric",
                    "feature_set_id": feature_set_id,
                    "split_strategy": split_strategy,
                    "model_variant": model_variant,
                    "metric": metric,
                    "median": _float(values.median()),
                    "mean": _float(values.mean()),
                    "min": _float(values.min()),
                    "max": _float(values.max()),
                    "valid_split_count": int(len(values)),
                    "status": "valid",
                }
            )
    return pd.DataFrame(rows)


def prediction_uncertainty_summary(intervals: pd.DataFrame) -> pd.DataFrame:
    if intervals.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (feature_set_id, split_strategy, model_variant), group in intervals.groupby(["feature_set_id", "split_strategy", "model_variant"]):
        valid = group[group["uncertainty_status"].eq("valid")]
        if valid.empty:
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "feature_set_id": feature_set_id,
                    "split_strategy": split_strategy,
                    "model_variant": model_variant,
                    "confidence_level": "",
                    "empirical_coverage_mean": "",
                    "mean_interval_width_mean": "",
                    "median_interval_width_median": "",
                    "valid_fold_count": 0,
                    "uncertainty_status": "unavailable_insufficient_calibration",
                }
            )
            continue
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "feature_set_id": feature_set_id,
                "split_strategy": split_strategy,
                "model_variant": model_variant,
                "confidence_level": _float(valid["confidence_level"].iloc[0]),
                "empirical_coverage_mean": _float(valid["empirical_coverage"].mean()),
                "mean_interval_width_mean": _float(valid["mean_interval_width"].mean()),
                "median_interval_width_median": _float(valid["median_interval_width"].median()),
                "valid_fold_count": int(len(valid)),
                "uncertainty_status": "prediction_interval_evaluated",
            }
        )
    return pd.DataFrame(rows)


def predictive_value_decision(
    *,
    cohort_summary: Mapping[str, Any],
    comparison_summary: pd.DataFrame,
    paired_summary: pd.DataFrame,
    uncertainty_summary: pd.DataFrame,
    exact_sensitivity: pd.DataFrame,
    input_shas: Mapping[str, str],
) -> dict[str, Any]:
    primary = paired_summary[paired_summary["split_strategy"].isin(PRIMARY_GROUP_SPLITS)].copy()
    random = paired_summary[paired_summary["split_strategy"].eq("random")].copy()
    structure_pairs = primary[primary["comparison_id"].isin(["A_vs_D", "B_vs_E"])]
    random_structure_pairs = random[random["comparison_id"].isin(["A_vs_D", "B_vs_E"])]
    primary_improved = structure_pairs[
        (pd.to_numeric(structure_pairs["mae_improvement_median"], errors="coerce") > 0)
        & (pd.to_numeric(structure_pairs["rmse_improvement_median"], errors="coerce") > 0)
        & (pd.to_numeric(structure_pairs["improved_fold_fraction_mae"], errors="coerce") >= 0.6)
    ]
    improved_splits = set(primary_improved["split_strategy"])
    random_improved = (
        pd.to_numeric(random_structure_pairs["mae_improvement_median"], errors="coerce") > 0
    ).any()
    if cohort_summary.get("cohort_rows", 0) == 0:
        status = "blocked_artifact_mismatch"
        reason = "no matched known-structure cohort"
    elif improved_splits == set(PRIMARY_GROUP_SPLITS):
        status = "structure_predictive_value_supported"
        reason = "structure descriptors improved both primary group splits"
    elif improved_splits:
        status = "structure_predictive_value_limited"
        reason = "structure descriptors improved one primary group split only"
    elif random_improved:
        status = "random_only_structure_improvement"
        reason = "structure improvement appeared only in random optimistic reference"
    elif not structure_pairs.empty and (
        pd.to_numeric(structure_pairs["mae_improvement_median"], errors="coerce") < 0
    ).all():
        status = "structure_performance_degraded"
        reason = "structure descriptor comparisons degraded median MAE across primary group evidence"
    else:
        status = "no_material_structure_improvement"
        reason = "structure descriptors did not show stable primary group improvement"
    representative = status == "structure_predictive_value_supported"
    return {
        "schema_version": SCHEMA_VERSION,
        "prediction_context": "known_structure_post_relaxation",
        "target_source": "original_v1_3_energy_above_hull",
        "structure_predictive_value_status": status,
        "decision_reason": reason,
        "representative_model_selected": representative,
        "representative_model": "bounded_known_structure_model" if representative else "none",
        "primary_evidence": "reduced_formula_group_and_chemical_system_group",
        "random_split_role": "optimistic_reference_only",
        "cohort_rows": int(cohort_summary.get("cohort_rows", 0)),
        "snapshot_aligned_rows": int(cohort_summary.get("snapshot_aligned_rows", 0)),
        "exact_match_sensitivity_status": _exact_sensitivity_status(exact_sensitivity),
        "input_shas": dict(input_shas),
        "claim_boundary": {
            "structure_informed_feature_available": True,
            "structure_informed_feature_used": True,
            "known_structure_predictive_comparison_completed": True,
            "group_aware_structure_evaluation_completed": True,
            "predictive_interval_evaluated": not uncertainty_summary.empty,
            "composition_only_pre_structure_claim": False,
            "graph_model_used": False,
            "gnn_model": False,
            "physics_constrained_model": False,
            "hybrid_physics_ml": False,
            "DFT_replacement": False,
            "phase_stability_guaranteed": False,
            "synthesizability_predicted": False,
            "causal_structure_mechanism_proven": False,
            "production_scientific_decision": False,
        },
    }


def feature_use_evidence(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "prediction_context": "known_structure_post_relaxation",
        "structure_informed_feature_available": True,
        "structure_informed_feature_used": True,
        "physics_informed_feature_used": True,
        "graph_model_used": False,
        "gnn_model": False,
        "original_target_source_only": True,
        "representative_model_selected": bool(decision["representative_model_selected"]),
        "structure_predictive_value_status": decision["structure_predictive_value_status"],
    }


def validate_known_structure_result(path: str | Path) -> dict[str, Any]:
    payload = load_json(path)
    errors = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if payload.get("target_source") != "original_v1_3_energy_above_hull":
        errors.append("target_source")
    claims = payload.get("claim_boundary", {})
    for claim in ["graph_model_used", "gnn_model", "DFT_replacement", "hybrid_physics_ml"]:
        if claims.get(claim) is not False:
            errors.append(claim)
    return {"schema_version": SCHEMA_VERSION, "valid": not errors, "errors": errors}


def validate_known_structure_cohort(path: str | Path) -> dict[str, Any]:
    cohort = pd.read_csv(path)
    errors = []
    for column in [IDENTIFIER_COLUMN, TARGET_COLUMN, "comparison_status"]:
        if column not in cohort.columns:
            errors.append(f"missing_{column}")
    if IDENTIFIER_COLUMN in cohort.columns and cohort[IDENTIFIER_COLUMN].isna().any():
        errors.append("missing_material_id")
    if TARGET_COLUMN in cohort.columns and cohort[TARGET_COLUMN].isna().any():
        errors.append("missing_original_target")
    if "current_energy_above_hull" in cohort.columns:
        errors.append("current_target_present")
    forbidden = forbidden_feature_audit(cohort.columns)
    if forbidden["forbidden_feature_columns"]:
        errors.append("forbidden_feature_columns")
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "row_count": int(len(cohort)),
        "target_source": "original_v1_3_energy_above_hull",
        "forbidden_feature_audit": forbidden,
    }


def _evaluate_one(
    df: pd.DataFrame,
    feature_set: Mapping[str, Any],
    split: Mapping[str, Any],
    split_config: SplitConfig,
    model_config: ModelConfig,
    *,
    confidence_level: float,
    random_state: int,
) -> dict[str, Any]:
    train_index = np.asarray(split["train_index"], dtype=int)
    test_index = np.asarray(split["test_index"], dtype=int)
    numeric = list(feature_set["numeric_features"])
    categorical = list(feature_set["categorical_features"])
    model = _build_model(model_config, numeric, categorical)
    x_train = df.iloc[train_index][numeric + categorical]
    x_test = df.iloc[test_index][numeric + categorical]
    y_train = pd.to_numeric(df.iloc[train_index][TARGET_COLUMN], errors="raise").to_numpy(dtype=float)
    y_test = pd.to_numeric(df.iloc[test_index][TARGET_COLUMN], errors="raise").to_numpy(dtype=float)
    y_fit = np.log1p(y_train) if model_config.target_treatment == "log1p" else y_train
    model.fit(x_train, y_fit)
    pred = np.asarray(model.predict(x_test), dtype=float)
    if model_config.target_treatment == "log1p":
        pred = np.expm1(pred)
    pred = np.maximum(pred, 0.0)
    ae = np.abs(y_test - pred)
    interval = _prediction_interval_audit(
        df,
        feature_set,
        split,
        split_config,
        model_config,
        confidence_level=confidence_level,
        random_state=random_state,
    )
    predictions = [
        {
            "split_strategy": split_config.name,
            "split_index": int(split["split_index"]),
            "feature_set_id": feature_set["feature_set_id"],
            "model_variant": model_config.name,
            "material_id": row[IDENTIFIER_COLUMN],
            "actual_target": float(y_test[pos]),
            "prediction": float(pred[pos]),
            "absolute_error": float(ae[pos]),
            "prediction_context": "known_structure_post_relaxation",
        }
        for pos, (_, row) in enumerate(df.iloc[test_index].iterrows())
    ]
    metrics = {
        "schema_version": SCHEMA_VERSION,
        "split_strategy": split_config.name,
        "split_index": int(split["split_index"]),
        "feature_set_id": feature_set["feature_set_id"],
        "feature_set_label": feature_set["label"],
        "model_variant": model_config.name,
        "mae": _float(np.mean(ae)),
        "median_absolute_error": _float(np.median(ae)),
        "rmse": _float(math.sqrt(np.mean((y_test - pred) ** 2))),
        "r2": _safe_r2(y_test, pred),
        "train_row_count": int(len(train_index)),
        "test_row_count": int(len(test_index)),
        "target_test_mean": _float(np.mean(y_test)),
        "target_test_std": _float(np.std(y_test)),
        "prediction_mean": _float(np.mean(pred)),
        "prediction_std": _float(np.std(pred)),
        "nonfinite_prediction_count": int(np.sum(~np.isfinite(pred))),
        "status": "valid",
    }
    return {"metrics": metrics, "predictions": predictions, "interval": interval}


def _prediction_interval_audit(
    df: pd.DataFrame,
    feature_set: Mapping[str, Any],
    split: Mapping[str, Any],
    split_config: SplitConfig,
    model_config: ModelConfig,
    *,
    confidence_level: float,
    random_state: int,
) -> dict[str, Any]:
    train_index = np.asarray(split["train_index"], dtype=int)
    test_index = np.asarray(split["test_index"], dtype=int)
    if len(train_index) < 40 or len(test_index) < 2:
        return _interval_unavailable(feature_set, split_config, split, model_config, "unavailable_insufficient_calibration")
    fit_idx, cal_idx = _calibration_split(df, train_index, split_config, random_state)
    if len(cal_idx) < 20 or len(fit_idx) < 20:
        return _interval_unavailable(feature_set, split_config, split, model_config, "unavailable_insufficient_calibration")
    numeric = list(feature_set["numeric_features"])
    categorical = list(feature_set["categorical_features"])
    model = _build_model(model_config, numeric, categorical)
    x_fit = df.iloc[fit_idx][numeric + categorical]
    x_cal = df.iloc[cal_idx][numeric + categorical]
    x_test = df.iloc[test_index][numeric + categorical]
    y_fit_raw = pd.to_numeric(df.iloc[fit_idx][TARGET_COLUMN], errors="raise").to_numpy(dtype=float)
    y_cal = pd.to_numeric(df.iloc[cal_idx][TARGET_COLUMN], errors="raise").to_numpy(dtype=float)
    y_test = pd.to_numeric(df.iloc[test_index][TARGET_COLUMN], errors="raise").to_numpy(dtype=float)
    y_fit = np.log1p(y_fit_raw) if model_config.target_treatment == "log1p" else y_fit_raw
    model.fit(x_fit, y_fit)
    cal_pred = np.asarray(model.predict(x_cal), dtype=float)
    test_pred = np.asarray(model.predict(x_test), dtype=float)
    if model_config.target_treatment == "log1p":
        cal_pred = np.expm1(cal_pred)
        test_pred = np.expm1(test_pred)
    cal_pred = np.maximum(cal_pred, 0.0)
    test_pred = np.maximum(test_pred, 0.0)
    residuals = np.abs(y_cal - cal_pred)
    if len(residuals) == 0:
        return _interval_unavailable(feature_set, split_config, split, model_config, "unavailable_insufficient_calibration")
    q = _conformal_quantile(residuals, confidence_level)
    lower = test_pred - q
    upper = test_pred + q
    covered = (y_test >= lower) & (y_test <= upper)
    width = upper - lower
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_set_id": feature_set["feature_set_id"],
        "split_strategy": split_config.name,
        "split_index": int(split["split_index"]),
        "model_variant": model_config.name,
        "confidence_level": confidence_level,
        "calibration_row_count": int(len(cal_idx)),
        "test_row_count": int(len(test_idx := test_index)),
        "empirical_coverage": _float(np.mean(covered)),
        "mean_interval_width": _float(np.mean(width)),
        "median_interval_width": _float(np.median(width)),
        "interval_failure_count": int(np.sum(~np.isfinite(width))),
        "uncertainty_status": "valid",
        "interpretation": "split_conformal_prediction_interval_not_dft_uncertainty",
    }


def _interval_unavailable(feature_set: Mapping[str, Any], split_config: SplitConfig, split: Mapping[str, Any], model_config: ModelConfig, status: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_set_id": feature_set["feature_set_id"],
        "split_strategy": split_config.name,
        "split_index": int(split.get("split_index", -1)),
        "model_variant": model_config.name,
        "confidence_level": "",
        "calibration_row_count": 0,
        "test_row_count": 0,
        "empirical_coverage": "",
        "mean_interval_width": "",
        "median_interval_width": "",
        "interval_failure_count": 0,
        "uncertainty_status": status,
        "interpretation": "prediction_interval_unavailable_not_replaced_by_fake_confidence",
    }


def _build_model(model_config: ModelConfig, numeric_features: list[str], categorical_features: list[str]) -> Any:
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric_features:
        numeric_pipeline = Pipeline([("imputer", SimpleImputer(strategy="median"))])
        if model_config.estimator_type == "ridge":
            numeric_pipeline.steps.append(("scaler", StandardScaler()))
        transformers.append(("numeric", numeric_pipeline, numeric_features))
    if categorical_features:
        try:
            encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        except TypeError:  # pragma: no cover - older sklearn
            encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
        transformers.append(("categorical", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("encoder", encoder)]), categorical_features))
    preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")
    if model_config.estimator_type == "dummy_median":
        estimator = DummyRegressor(strategy="median")
    elif model_config.estimator_type == "ridge":
        estimator = Ridge(alpha=model_config.alpha)
    elif model_config.estimator_type == "histogram_gradient_boosting":
        estimator = HistGradientBoostingRegressor(
            random_state=model_config.random_state,
            max_iter=60,
            learning_rate=0.1,
            max_leaf_nodes=31,
        )
    else:
        raise ValueError(f"unsupported model type: {model_config.estimator_type}")
    return Pipeline([("preprocess", preprocessor), ("model", estimator)])


def _calibration_split(df: pd.DataFrame, train_index: np.ndarray, split_config: SplitConfig, random_state: int) -> tuple[np.ndarray, np.ndarray]:
    from sklearn.model_selection import GroupShuffleSplit, ShuffleSplit

    if split_config.group_column and split_config.group_column in df.columns and df.iloc[train_index][split_config.group_column].nunique() >= 3:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
        local = np.arange(len(train_index))
        groups = df.iloc[train_index][split_config.group_column]
        fit_local, cal_local = next(splitter.split(local, groups=groups))
    else:
        splitter = ShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
        fit_local, cal_local = next(splitter.split(np.arange(len(train_index))))
    return train_index[fit_local], train_index[cal_local]


def _conformal_quantile(residuals: np.ndarray, confidence_level: float) -> float:
    residuals = np.sort(np.asarray(residuals, dtype=float))
    n = len(residuals)
    rank = int(math.ceil((n + 1) * confidence_level))
    rank = min(max(rank, 1), n)
    return float(residuals[rank - 1])


def _run_exact_match_sensitivity(
    request: KnownStructurePredictionRequest,
    cohort: pd.DataFrame,
    feature_sets: Mapping[str, Mapping[str, Any]],
    split_configs: list[SplitConfig],
    model_configs: list[ModelConfig],
    confidence_level: float,
) -> pd.DataFrame:
    exact = cohort[cohort["comparison_status"].eq("target_exact_match")].reset_index(drop=True)
    if len(exact) < 120:
        return pd.DataFrame([{"schema_version": SCHEMA_VERSION, "sensitivity_cohort": "exact_match_only", "row_count": len(exact), "status": "insufficient_sample"}])
    rows: list[dict[str, Any]] = []
    for split_config in split_configs:
        splits = generate_splits(exact, split_config)
        for split in splits[:3]:
            if split["status"] != "valid":
                continue
            for feature_set_id in ["known_structure_composition_baseline_v1", "known_structure_baseline_plus_structure_v1"]:
                for model_config in model_configs[:2]:
                    result = _evaluate_one(
                        exact,
                        feature_sets[feature_set_id],
                        split,
                        split_config,
                        model_config,
                        confidence_level=confidence_level,
                        random_state=request.random_state,
                    )
                    rows.append({**result["metrics"], "sensitivity_cohort": "exact_match_only"})
    if not rows:
        return pd.DataFrame([{"schema_version": SCHEMA_VERSION, "sensitivity_cohort": "exact_match_only", "row_count": len(exact), "status": "not_run"}])
    return predictive_comparison_summary(pd.DataFrame(rows)).assign(sensitivity_cohort="exact_match_only")


def _split_diagnostics(df: pd.DataFrame, split: Mapping[str, Any], split_config: SplitConfig) -> dict[str, Any]:
    row = {
        "schema_version": SCHEMA_VERSION,
        "split_strategy": split_config.name,
        "split_index": int(split.get("split_index", -1)),
        "split_status": split.get("status", "invalid"),
        "claim_scope": "optimistic_reference_only" if split_config.name == "random" else "primary_group_generalization",
    }
    if split.get("status") != "valid":
        row.update({"invalid_reason": split.get("invalid_reason", ""), "train_row_count": 0, "test_row_count": 0})
        return row
    train = df.iloc[split["train_index"]]
    test = df.iloc[split["test_index"]]
    row.update(
        {
            "invalid_reason": "",
            "train_row_count": int(len(train)),
            "test_row_count": int(len(test)),
            "material_id_overlap_count": int(len(set(train[IDENTIFIER_COLUMN]).intersection(set(test[IDENTIFIER_COLUMN])))),
            "reduced_formula_overlap_count": int(len(set(train["reduced_formula_group"]).intersection(set(test["reduced_formula_group"])))),
            "chemical_system_overlap_count": int(len(set(train["chemical_system_group"]).intersection(set(test["chemical_system_group"])))),
            "target_train_mean": _float(pd.to_numeric(train[TARGET_COLUMN]).mean()),
            "target_test_mean": _float(pd.to_numeric(test[TARGET_COLUMN]).mean()),
        }
    )
    return row


def _split_assignment_rows(df: pd.DataFrame, split_map: Mapping[str, list[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split_strategy, splits in split_map.items():
        for split in splits:
            if split["status"] != "valid":
                continue
            for assignment, indices in [("train", split["train_index"]), ("test", split["test_index"])]:
                for index in indices:
                    rows.append(
                        {
                            "split_strategy": split_strategy,
                            "split_index": int(split["split_index"]),
                            "assignment": assignment,
                            "material_id": df.iloc[int(index)][IDENTIFIER_COLUMN],
                        }
                    )
    return rows


def _local_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "cohort": output_dir / "cohort" / "matched_cohort.csv",
        "exclusion_manifest": output_dir / "cohort" / "exclusion_manifest.csv",
        "cohort_manifest": output_dir / "cohort" / "cohort_manifest.json",
        "features_dir": output_dir / "features",
        "feature_set_manifest": output_dir / "features" / "feature_set_manifest.json",
        "split_assignments": output_dir / "splits" / "split_assignments.csv",
        "split_manifest": output_dir / "splits" / "split_manifest.json",
        "fold_metrics": output_dir / "comparison" / "fold_metrics.csv",
        "predictions": output_dir / "comparison" / "predictions.csv",
        "prediction_intervals": output_dir / "comparison" / "prediction_intervals.csv",
        "paired_deltas": output_dir / "comparison" / "paired_deltas.csv",
        "aggregate_metrics": output_dir / "comparison" / "aggregate_metrics.csv",
        "uncertainty_summary": output_dir / "comparison" / "uncertainty_summary.csv",
        "split_diagnostics": output_dir / "comparison" / "split_diagnostics.csv",
        "local_decision": output_dir / "comparison" / "predictive_value_decision.json",
        "manifest": output_dir / "comparison" / "comparison_manifest.json",
        "local_report": output_dir / "reports" / "known_structure_prediction_report.md",
    }


def _write_feature_set_files(df: pd.DataFrame, feature_sets: Mapping[str, Mapping[str, Any]], output_dir: Path, overwrite: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for feature_set_id, feature_set in feature_sets.items():
        columns = [IDENTIFIER_COLUMN, *feature_set["numeric_features"], *feature_set["categorical_features"]]
        _write_csv(df[columns], output_dir / f"{feature_set_id}.csv", overwrite)


def _write_plots(comparison_summary: pd.DataFrame, paired: pd.DataFrame, uncertainty: pd.DataFrame, plot_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover
        return
    plot_dir.mkdir(parents=True, exist_ok=True)
    mae = comparison_summary[comparison_summary["metric"].eq("mae")]
    if not mae.empty:
        pivot = mae.pivot_table(index="feature_set_id", columns="split_strategy", values="median", aggfunc="mean")
        pivot.plot(kind="bar", figsize=(10, 5), title="Known-structure feature-set median MAE by split")
        plt.ylabel("MAE (eV/atom)")
        plt.tight_layout()
        plt.savefig(plot_dir / "feature_set_metric_comparison.png")
        plt.close()
    for comparison_id, filename in [("A_vs_D", "paired_mae_delta.png"), ("B_vs_E", "paired_rmse_delta.png")]:
        subset = paired[paired["comparison_id"].eq(comparison_id)]
        if subset.empty:
            continue
        y = "mae_improvement_median" if comparison_id == "A_vs_D" else "rmse_improvement_median"
        subset.pivot_table(index="model_variant", columns="split_strategy", values=y, aggfunc="mean").plot(kind="bar", figsize=(10, 5), title=f"{comparison_id} paired improvement")
        plt.axhline(0, color="black", linewidth=1)
        plt.tight_layout()
        plt.savefig(plot_dir / filename)
        plt.close()
    if not uncertainty.empty:
        valid = uncertainty[pd.to_numeric(uncertainty["mean_interval_width_mean"], errors="coerce").notna()]
        if not valid.empty:
            plt.figure(figsize=(8, 5))
            plt.scatter(pd.to_numeric(valid["mean_interval_width_mean"]), pd.to_numeric(valid["empirical_coverage_mean"]))
            plt.xlabel("Mean interval width")
            plt.ylabel("Empirical coverage")
            plt.title("Prediction interval coverage vs width")
            plt.tight_layout()
            plt.savefig(plot_dir / "interval_coverage_width.png")
            plt.close()


def render_known_structure_report(decision: Mapping[str, Any], comparison_summary: pd.DataFrame, paired: pd.DataFrame, uncertainty: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# Known-Structure Prediction Report",
            "",
            f"Status: `{decision['structure_predictive_value_status']}`",
            "",
            "Prediction context: `known_structure_post_relaxation`.",
            "Target source: original v1.3 `energy_above_hull` in eV/atom.",
            "Random split is an optimistic reference; group splits are primary evidence.",
            "Graph artifacts are not model inputs.",
            "Prediction intervals are residual uncertainty diagnostics, not DFT uncertainty.",
            "",
        ]
    )


def render_report_summary(decision: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Materials v2.2.5 Known-Structure Summary",
            "",
            f"- decision: `{decision['structure_predictive_value_status']}`",
            f"- representative model selected: `{str(decision['representative_model_selected']).lower()}`",
            "- prediction context: `known_structure_post_relaxation`",
            "- target source: original v1.3 `energy_above_hull`",
            "- graph/GNN/DFT replacement claims: false",
            "",
        ]
    )


def _required_input_paths(request: KnownStructurePredictionRequest) -> list[Path]:
    return [
        request.analysis_ready_path,
        request.validation_spec_path,
        request.physics_feature_matrix_path,
        request.structure_descriptor_path,
        request.snapshot_alignment_path,
        request.v2_2_4_summary_path,
    ]


def _assert_required_inputs(request: KnownStructurePredictionRequest) -> None:
    missing = [path.as_posix() for path in _required_input_paths(request) if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required known-structure artifact(s): " + ", ".join(missing))


def _require_unique_material_id(df: pd.DataFrame, label: str) -> None:
    if IDENTIFIER_COLUMN not in df.columns:
        raise ValueError(f"{label} missing material_id")
    if df[IDENTIFIER_COLUMN].isna().any():
        raise ValueError(f"{label} contains missing material_id")
    duplicated = df[IDENTIFIER_COLUMN].astype(str).duplicated()
    if duplicated.any():
        raise ValueError(f"{label} contains duplicated material_id")


def _baseline_features(spec: Mapping[str, Any]) -> list[str]:
    features = [str(column) for column in spec.get("feature_columns", [])]
    if not features:
        raise ValueError("validation spec has no baseline feature_columns")
    return features


def _physics_column_name(column: str, analysis: pd.DataFrame | Mapping[str, Any]) -> str:
    columns = set(analysis.columns) if hasattr(analysis, "columns") else set(analysis)
    return f"{column}__physics" if column in columns else column


def _resolved_physics_column(column: str, columns: Iterable[str]) -> str:
    column_set = set(columns)
    suffixed = f"{column}__physics"
    if suffixed in column_set:
        return suffixed
    if column in column_set:
        return column
    return suffixed


def _feature_set_ids() -> tuple[str, ...]:
    return (
        "known_structure_composition_baseline_v1",
        "known_structure_composition_physics_v1",
        "known_structure_structure_only_v1",
        "known_structure_baseline_plus_structure_v1",
        "known_structure_full_combined_v1",
    )


def _split_configs_from_spec(spec: Mapping[str, Any]) -> list[SplitConfig]:
    return [
        SplitConfig("random", "shuffle", None, int(spec.get("n_splits", 10)), float(spec.get("test_size", 0.2)), int(spec.get("random_state", 42))),
        SplitConfig("reduced_formula_group", "group_shuffle", "reduced_formula_group", int(spec.get("n_splits", 10)), float(spec.get("test_size", 0.2)), int(spec.get("random_state", 42))),
        SplitConfig("chemical_system_group", "group_shuffle", "chemical_system_group", int(spec.get("n_splits", 10)), float(spec.get("test_size", 0.2)), int(spec.get("random_state", 42))),
    ]


def _safe_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    from sklearn.metrics import r2_score

    if len(y_true) < 2 or np.isclose(np.var(y_true), 0.0):
        return float("nan")
    return _float(r2_score(y_true, y_pred))


def _float(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return numeric if math.isfinite(numeric) else float("nan")


def _write_csv(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")


def _write_json(payload: Mapping[str, Any], path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(text: str, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _assert_no_sensitive_or_row_level_payload(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    forbidden = ["MP_API_KEY=", "KAGGLE_KEY=", "C:/", "C:\\", "/Users/", "mp-aaaa", "fractional_coordinates", '"sites": [']
    hits = [item for item in forbidden if item in text]
    if hits:
        raise ValueError(f"sensitive or row-level payload detected in {path}: {hits}")


def _exact_sensitivity_status(exact_sensitivity: pd.DataFrame) -> str:
    if exact_sensitivity.empty:
        return "not_run"
    if "status" in exact_sensitivity.columns and exact_sensitivity["status"].notna().any():
        return str(exact_sensitivity["status"].dropna().iloc[0])
    return "completed"
