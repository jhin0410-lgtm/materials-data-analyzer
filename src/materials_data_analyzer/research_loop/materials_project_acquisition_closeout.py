"""Post-hoc closeout for the frozen Materials Project Stage 4 acquisition suite.

This module audits already-completed benchmark-v1 artifacts. It may summarize the
locked evaluation that has already been exposed, but it must not redefine, retune,
or rerun benchmark-v1 acquisition strategies from locked-test results.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STRATEGIES = ("fixed_catalog", "random", "diversity", "uncertainty")
CLOSEOUT_SCHEMA_VERSION = "1.0"


class MaterialsProjectAcquisitionCloseoutError(ValueError):
    """Raised when a suite artifact or closeout boundary is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterialsProjectAcquisitionCloseoutError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise MaterialsProjectAcquisitionCloseoutError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MaterialsProjectAcquisitionCloseoutError(f"JSON root must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_child(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MaterialsProjectAcquisitionCloseoutError(f"unsafe {label} path")
    path = root / candidate
    if not path.is_file():
        raise MaterialsProjectAcquisitionCloseoutError(f"missing {label}: {path}")
    return path


def _finite_or_none(value: Any) -> float | None:
    result = float(value)
    return result if math.isfinite(result) else None


def _quantiles(values: pd.Series) -> dict[str, float | None]:
    numeric = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if numeric.empty:
        return {"mean": None, "median": None, "q10": None, "q90": None}
    return {
        "mean": float(numeric.mean()),
        "median": float(numeric.median()),
        "q10": float(numeric.quantile(0.10)),
        "q90": float(numeric.quantile(0.90)),
    }


def _load_benchmark_contract(
    benchmark_root: Path,
    benchmark_config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    manifest = _load_json(benchmark_root / "benchmark_manifest.json")
    config = _load_json(benchmark_config_path)
    if manifest.get("benchmark_id") != config.get("benchmark_id"):
        raise MaterialsProjectAcquisitionCloseoutError("benchmark manifest/config id mismatch")
    outputs = manifest.get("outputs")
    hashes = manifest.get("output_sha256")
    if not isinstance(outputs, dict) or not isinstance(hashes, dict):
        raise MaterialsProjectAcquisitionCloseoutError("benchmark output inventory is invalid")
    seed_path = _safe_child(benchmark_root, str(outputs.get("seed_evidence", "")), "seed evidence")
    if hashes.get("seed_evidence") != _sha256_file(seed_path):
        raise MaterialsProjectAcquisitionCloseoutError("seed evidence checksum mismatch")
    seed = pd.read_csv(seed_path)
    identifier = str(config.get("identifier_column", ""))
    target = str(config.get("target_column", ""))
    if not identifier or not target or identifier not in seed.columns or target not in seed.columns:
        raise MaterialsProjectAcquisitionCloseoutError("benchmark identifier/target contract is invalid")
    return manifest, config, seed


def _load_sequence(
    suite_root: Path,
    strategy: str,
    *,
    seed_ids: set[str],
    identifier: str,
    target: str,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    root = suite_root / "sequences" / strategy
    manifest = _load_json(root / "sequence_manifest.json")
    if manifest.get("execution_status") != "completed" or manifest.get("strategy") != strategy:
        raise MaterialsProjectAcquisitionCloseoutError(f"invalid completed sequence: {strategy}")
    boundary = manifest.get("planner_boundary")
    if not isinstance(boundary, dict) or boundary.get("locked_test_content_read") is not False:
        raise MaterialsProjectAcquisitionCloseoutError(f"locked boundary invalid for {strategy}")
    outputs = manifest.get("outputs")
    hashes = manifest.get("output_sha256")
    if not isinstance(outputs, dict) or not isinstance(hashes, dict):
        raise MaterialsProjectAcquisitionCloseoutError(f"sequence output inventory invalid: {strategy}")
    frames: dict[str, pd.DataFrame] = {}
    for key in ("training_evidence", "acquisition_history"):
        path = _safe_child(root, str(outputs.get(key, "")), f"{strategy} {key}")
        if hashes.get(key) != _sha256_file(path):
            raise MaterialsProjectAcquisitionCloseoutError(
                f"sequence output checksum mismatch: {strategy}/{key}"
            )
        frames[key] = pd.read_csv(path)
    training = frames["training_evidence"]
    history = frames["acquisition_history"]
    if identifier not in training.columns or target not in training.columns:
        raise MaterialsProjectAcquisitionCloseoutError(f"training evidence schema invalid: {strategy}")
    training_ids = training[identifier].astype(str)
    if training_ids.duplicated().any() or not seed_ids.issubset(set(training_ids)):
        raise MaterialsProjectAcquisitionCloseoutError(f"training identifiers invalid: {strategy}")
    acquired = training[~training_ids.isin(seed_ids)].copy()
    expected_acquired = int(manifest["counts"]["acquired_rows"])
    if len(acquired) != expected_acquired:
        raise MaterialsProjectAcquisitionCloseoutError(f"acquired row count mismatch: {strategy}")
    if int(history["step_cost"].sum()) != int(manifest["counts"]["cost_used"]):
        raise MaterialsProjectAcquisitionCloseoutError(f"history cost mismatch: {strategy}")
    selected_groups = [str(value) for value in history["selected_group"].tolist()]
    if len(selected_groups) != len(set(selected_groups)):
        raise MaterialsProjectAcquisitionCloseoutError(f"duplicate selected group: {strategy}")
    diagnostics = {
        "strategy": strategy,
        "acquisition_steps": int(len(history)),
        "acquired_rows": int(len(acquired)),
        "cost_used": int(manifest["counts"]["cost_used"]),
        "selected_group_count": int(len(selected_groups)),
        "selected_groups": selected_groups,
        "fallback_step_count": int(
            history["selection_reason"].astype(str).str.contains("fallback", case=False).sum()
        ),
        "selection_score_nonnull_count": int(history["selection_score"].notna().sum()),
        "selection_score_summary": _quantiles(history["selection_score"]),
        "acquired_target_summary": _quantiles(acquired[target]),
        "sequence_manifest_sha256": _sha256_file(root / "sequence_manifest.json"),
    }
    return manifest, training, history, diagnostics


def _load_locked_metrics(
    suite_root: Path,
    strategy: str,
) -> tuple[dict[str, Any], pd.DataFrame, list[dict[str, Any]]]:
    root = suite_root / "evaluations" / strategy
    manifest = _load_json(root / "evaluation_manifest.json")
    if manifest.get("evaluation_status") != "completed" or manifest.get("strategy") != strategy:
        raise MaterialsProjectAcquisitionCloseoutError(f"invalid completed evaluation: {strategy}")
    boundary = manifest.get("locked_boundary")
    if not isinstance(boundary, dict) or any(
        boundary.get(key) is not True
        for key in (
            "sequence_completed_before_locked_read",
            "locked_metrics_not_available_to_sequence",
            "primary_model_predeclared",
        )
    ):
        raise MaterialsProjectAcquisitionCloseoutError(f"locked evaluation boundary invalid: {strategy}")
    outputs = manifest.get("outputs")
    hashes = manifest.get("output_sha256")
    if not isinstance(outputs, dict) or not isinstance(hashes, dict):
        raise MaterialsProjectAcquisitionCloseoutError(f"evaluation outputs invalid: {strategy}")
    metrics_path = _safe_child(root, str(outputs.get("locked_metrics", "")), f"{strategy} locked metrics")
    if hashes.get("locked_metrics") != _sha256_file(metrics_path):
        raise MaterialsProjectAcquisitionCloseoutError(f"locked metrics checksum mismatch: {strategy}")
    metrics = pd.read_csv(metrics_path)
    required_columns = {"training_scope", "model_variant", "mae", "r2", "spearman"}
    if not required_columns.issubset(metrics.columns):
        raise MaterialsProjectAcquisitionCloseoutError(f"locked metrics schema invalid: {strategy}")
    rows: list[dict[str, Any]] = []
    final = metrics[metrics["training_scope"].eq("final_sequence")]
    for _, row in final.iterrows():
        rows.append(
            {
                "strategy": strategy,
                "model_variant": str(row["model_variant"]),
                "mae": float(row["mae"]),
                "r2": float(row["r2"]),
                "spearman": _finite_or_none(row["spearman"]),
            }
        )
    primary = str(manifest["primary_model_result"]["model_variant"])
    primary_rows = [row for row in rows if row["model_variant"] == primary]
    dummy_rows = [row for row in rows if row["model_variant"] == "dummy_median"]
    if len(primary_rows) != 1 or len(dummy_rows) != 1:
        raise MaterialsProjectAcquisitionCloseoutError(
            f"primary/dummy locked metric missing or duplicated: {strategy}"
        )
    primary_row = primary_rows[0]
    dummy_row = dummy_rows[0]
    primary_row["dummy_median_mae"] = float(dummy_row["mae"])
    primary_row["primary_beats_dummy_median_mae"] = bool(
        float(primary_row["mae"]) < float(dummy_row["mae"])
    )
    return manifest, metrics, rows


def _pairwise_overlap(strategy_groups: dict[str, set[str]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for left in STRATEGIES:
        for right in STRATEGIES:
            a = strategy_groups[left]
            b = strategy_groups[right]
            union = a | b
            rows.append(
                {
                    "left_strategy": left,
                    "right_strategy": right,
                    "shared_groups": int(len(a & b)),
                    "union_groups": int(len(union)),
                    "jaccard": float(len(a & b) / len(union)) if union else 1.0,
                }
            )
    return pd.DataFrame(rows)


def audit_materials_project_acquisition_suite(
    *,
    suite_root: str | Path,
    benchmark_dir: str | Path,
    benchmark_config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Audit frozen benchmark-v1 results and emit a non-tuning scientific closeout."""
    suite = Path(suite_root).expanduser().resolve(strict=True)
    benchmark = Path(benchmark_dir).expanduser().resolve(strict=True)
    benchmark_config = Path(benchmark_config_path).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().resolve(strict=False)
    if output == suite or suite in output.parents:
        raise MaterialsProjectAcquisitionCloseoutError(
            "closeout output must not mutate the frozen suite directory"
        )

    comparison_path = suite / "strategy_comparison.json"
    comparison = _load_json(comparison_path)
    comparison_rows = comparison.get("strategies")
    if not isinstance(comparison_rows, list) or len(comparison_rows) != len(STRATEGIES):
        raise MaterialsProjectAcquisitionCloseoutError("strategy comparison inventory is invalid")
    comparison_by_strategy = {str(row.get("strategy")): row for row in comparison_rows if isinstance(row, dict)}
    if set(comparison_by_strategy) != set(STRATEGIES):
        raise MaterialsProjectAcquisitionCloseoutError("strategy comparison does not cover frozen inventory")

    benchmark_manifest, benchmark_cfg, seed = _load_benchmark_contract(benchmark, benchmark_config)
    if comparison.get("benchmark_id") != benchmark_manifest.get("benchmark_id"):
        raise MaterialsProjectAcquisitionCloseoutError("suite/benchmark id mismatch")
    identifier = str(benchmark_cfg["identifier_column"])
    target = str(benchmark_cfg["target_column"])
    seed_ids = set(seed[identifier].astype(str))

    planner_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    strategy_groups: dict[str, set[str]] = {}
    locked_hashes: set[str] = set()
    for strategy in STRATEGIES:
        sequence_manifest, _, _, planner = _load_sequence(
            suite,
            strategy,
            seed_ids=seed_ids,
            identifier=identifier,
            target=target,
        )
        evaluation_manifest, _, models = _load_locked_metrics(suite, strategy)
        if evaluation_manifest.get("sequence_manifest_sha256") != planner["sequence_manifest_sha256"]:
            raise MaterialsProjectAcquisitionCloseoutError(
                f"evaluation is not bound to sequence manifest: {strategy}"
            )
        if int(evaluation_manifest["cost_used"]) != int(sequence_manifest["counts"]["cost_used"]):
            raise MaterialsProjectAcquisitionCloseoutError(f"sequence/evaluation cost mismatch: {strategy}")
        locked_hashes.add(str(evaluation_manifest.get("locked_test_sha256")))
        planner_rows.append(planner)
        model_rows.extend(models)
        strategy_groups[strategy] = set(planner["selected_groups"])

    if len(locked_hashes) != 1:
        raise MaterialsProjectAcquisitionCloseoutError("strategies were not evaluated on one locked test")

    comparison_frame = pd.DataFrame(comparison_rows)
    comparison_frame["final_sequence_mae"] = pd.to_numeric(
        comparison_frame["final_sequence_mae"], errors="raise"
    )
    comparison_frame["relative_mae_improvement_fraction"] = pd.to_numeric(
        comparison_frame["relative_mae_improvement_fraction"], errors="raise"
    )
    comparison_frame["final_sequence_r2"] = pd.to_numeric(
        comparison_frame["final_sequence_r2"], errors="raise"
    )
    comparison_frame["final_sequence_spearman"] = pd.to_numeric(
        comparison_frame["final_sequence_spearman"], errors="raise"
    )
    comparison_frame["cost_used"] = pd.to_numeric(comparison_frame["cost_used"], errors="raise")

    same_cost = bool(comparison_frame["cost_used"].nunique() == 1)
    all_improved = bool(comparison_frame["improved"].astype(bool).all())
    uncertainty_mae = float(
        comparison_frame.loc[comparison_frame["strategy"].eq("uncertainty"), "final_sequence_mae"].iloc[0]
    )
    nonadaptive_mae = float(
        comparison_frame.loc[
            comparison_frame["strategy"].isin(["fixed_catalog", "random"]),
            "final_sequence_mae",
        ].min()
    )
    adaptive_superiority = uncertainty_mae < nonadaptive_mae
    uncertainty_penalty_fraction = (
        float((uncertainty_mae - nonadaptive_mae) / nonadaptive_mae)
        if nonadaptive_mae > 0
        else float("nan")
    )

    model_frame = pd.DataFrame(model_rows)
    primary_model = str(comparison["primary_model"])
    primary_rows = model_frame[model_frame["model_variant"].eq(primary_model)].copy()
    primary_beats_dummy_all = bool(primary_rows["primary_beats_dummy_median_mae"].all())

    overlap = _pairwise_overlap(strategy_groups)
    planner_frame = pd.DataFrame(planner_rows)
    output.mkdir(parents=True, exist_ok=True)
    planner_path = output / "planner_strategy_diagnostics.csv"
    model_path = output / "locked_model_diagnostics.csv"
    overlap_path = output / "selected_group_overlap.csv"
    planner_frame.drop(columns=["selected_groups"]).to_csv(planner_path, index=False)
    model_frame.to_csv(model_path, index=False)
    overlap.to_csv(overlap_path, index=False)

    result = {
        "schema_version": CLOSEOUT_SCHEMA_VERSION,
        "benchmark_id": comparison["benchmark_id"],
        "execution_status": "benchmark_v1_closed_out",
        "suite_binding": {
            "strategy_comparison_sha256": _sha256_file(comparison_path),
            "locked_test_sha256": next(iter(locked_hashes)),
            "benchmark_manifest_sha256": _sha256_file(benchmark / "benchmark_manifest.json"),
            "benchmark_config_sha256": _sha256_file(benchmark_config),
        },
        "primary_model": primary_model,
        "observed_result": {
            "same_label_cost_across_strategies": same_cost,
            "all_strategies_improved_primary_mae_vs_seed": all_improved,
            "lowest_locked_mae_strategy": comparison["lowest_locked_mae_strategy"],
            "uncertainty_final_mae": uncertainty_mae,
            "best_fixed_or_random_mae": nonadaptive_mae,
            "uncertainty_mae_penalty_vs_best_fixed_or_random_fraction": uncertainty_penalty_fraction,
            "uncertainty_outperformed_fixed_and_random_on_primary_mae": adaptive_superiority,
            "primary_model_beats_dummy_median_mae_for_all_strategies": primary_beats_dummy_all,
            "primary_final_r2_range": [
                float(comparison_frame["final_sequence_r2"].min()),
                float(comparison_frame["final_sequence_r2"].max()),
            ],
            "primary_final_spearman_range": [
                float(comparison_frame["final_sequence_spearman"].min()),
                float(comparison_frame["final_sequence_spearman"].max()),
            ],
        },
        "scientific_closeout": {
            "additional_label_evidence_benefit": "Diagnostic" if same_cost and all_improved else "Inconclusive",
            "adaptive_uncertainty_policy_superiority": (
                "Diagnostic" if same_cost and adaptive_superiority else "Unsupported"
            ),
            "predictive_interpretation_readiness": "Inconclusive",
            "autonomous_discovery_claim": "Unsupported",
            "result_statement": (
                "Additional labels improved primary locked MAE under every frozen strategy, but "
                "the benchmark-v1 uncertainty policy did not outperform the fixed/random baselines."
                if same_cost and all_improved and not adaptive_superiority
                else "Benchmark-v1 results require conservative interpretation under the frozen contract."
            ),
        },
        "policy_boundary": {
            "benchmark_v1_locked_results_are_now_exposed": True,
            "benchmark_v1_strategy_retuning_authorized": False,
            "locked_test_may_be_reused_for_policy_selection": False,
            "planner_side_sequence_diagnostics_authorized_for_failure_analysis": True,
            "new_policy_requires_predeclared_development_protocol": True,
            "new_policy_requires_independent_evaluation_evidence": True,
        },
        "next_stage": {
            "now": (
                "Use planner-side histories and acquired-label diagnostics to characterize why "
                "fixed/random/diversity/uncertainty selected different chemical-system groups."
            ),
            "next": (
                "Predeclare a separate policy-development replay using data not serving as the "
                "benchmark-v1 locked test; freeze any policy-v2 rule before new evaluation."
            ),
            "later": (
                "Only after independent policy evidence, connect the generic action layer to "
                "requirement-conditioned external-source acquisition and characterization evidence."
            ),
        },
        "outputs": {
            "planner_strategy_diagnostics": planner_path.name,
            "locked_model_diagnostics": model_path.name,
            "selected_group_overlap": overlap_path.name,
        },
        "scientific_boundary": (
            "This closeout summarizes already-exposed benchmark-v1 evidence. It must not be used "
            "to tune or redefine benchmark-v1 strategies, and it creates no causal, synthesizability, "
            "DFT-replacement, production-screening, or autonomous-discovery claim."
        ),
    }
    closeout_path = output / "benchmark_closeout.json"
    closeout_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result
