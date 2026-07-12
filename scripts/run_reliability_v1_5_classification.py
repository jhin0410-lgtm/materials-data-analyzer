"""Run Reliability v1.5.4 Backblaze 7d/7d classification baselines.

This script uses local-only Backblaze-derived inputs, creates a local-only
7-day horizon / 7-day lookback feature dataset when needed, runs fixed
classical baselines under asset/time-aware validation, and writes compact
tracked summaries.

It does not train survival models, fit RUL regressors, perform hyperparameter
search, use SHAP, call external systems, or create production alert claims.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.asset_temporal_classification import (  # noqa: E402
    AssetTemporalClassificationConfig,
    AssetTemporalModelConfig,
    FeatureSetConfig,
    ResourceBudget,
    default_asset_temporal_model_configs,
    evaluate_asset_temporal_classification,
)
from analyzers.temporal_classification_validation import calculate_file_sha256  # noqa: E402
from features.temporal_asset_features import (  # noqa: E402
    TemporalAssetFeatureConfig,
    feature_columns_for_safe_metadata,
    feature_columns_for_smart_only,
    write_temporal_asset_feature_dataset_from_csv,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run fixed Backblaze v1.5.4 7d/7d reliability baselines."
    )
    parser.add_argument(
        "--spec",
        default="data/case_studies/reliability/classification_spec_v1_5.json",
        help="v1.5.4 classification specification.",
    )
    parser.add_argument(
        "--rebuild-feature-dataset",
        action="store_true",
        help="Rebuild the local 7d/7d feature dataset even if it already exists.",
    )
    return parser.parse_args()


def main() -> None:
    """Run classification and print a JSON summary."""
    args = parse_args()
    summary = run_classification(args)
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_classification(args: argparse.Namespace) -> dict[str, Any]:
    """Run the v1.5.4 workflow."""
    spec = load_json(args.spec)
    paths = output_paths(spec)
    preflight = run_preflight(spec)
    analysis_sha_before = calculate_file_sha256(spec["source_inputs"]["analysis_ready_csv"])
    feature_dataset_summary = ensure_feature_dataset(
        spec,
        analysis_sha_before,
        rebuild=args.rebuild_feature_dataset,
    )
    dataset_df = load_feature_dataset_for_modeling(spec)
    config = build_classification_config(spec, analysis_sha_before)
    started = time.perf_counter()
    outputs = evaluate_asset_temporal_classification(dataset_df, config)
    runtime_seconds = round(time.perf_counter() - started, 3)
    write_outputs(outputs, paths)
    validate_tracked_outputs(paths)
    parse_outputs(paths)
    analysis_sha_after = calculate_file_sha256(spec["source_inputs"]["analysis_ready_csv"])
    if analysis_sha_before != analysis_sha_after:
        raise RuntimeError("Analysis-ready source changed during classification.")
    summary = build_console_summary(
        spec=spec,
        preflight=preflight,
        feature_dataset_summary=feature_dataset_summary,
        outputs=outputs,
        paths=paths,
        analysis_sha=analysis_sha_after,
        runtime_seconds=runtime_seconds,
    )
    return summary


def run_preflight(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate local inputs and v1.5.3 readiness artifacts before modeling."""
    analysis_ready = Path(spec["source_inputs"]["analysis_ready_csv"])
    manifest_path = Path(spec["source_inputs"]["full_year_manifest"])
    horizon_path = Path(spec["source_inputs"]["horizon_feasibility"])
    lookback_path = Path(spec["source_inputs"]["lookback_feasibility"])
    split_path = Path(spec["source_inputs"]["split_feasibility"])
    smart_path = Path(spec["source_inputs"]["smart_feature_inventory"])
    for path in [analysis_ready, manifest_path, horizon_path, lookback_path, split_path, smart_path]:
        if not path.exists():
            raise FileNotFoundError(f"Required v1.5 input is missing: {path}")
    manifest = load_json(manifest_path)
    raw_archive = Path(spec["source_inputs"]["raw_archive"])
    if not raw_archive.exists():
        raise FileNotFoundError(f"Raw archive is missing: {raw_archive}")
    raw_sha = calculate_file_sha256(raw_archive)
    expected_raw_sha = spec["source_sha_policy"]["archive_sha256"]
    if raw_sha != expected_raw_sha:
        raise RuntimeError("Backblaze source archive SHA mismatch.")
    if raw_sha != manifest["source_archive_sha256_after"]:
        raise RuntimeError("Source archive SHA does not match full-year manifest.")
    if analysis_ready.stat().st_size != int(spec["source_inputs"]["analysis_ready_size_bytes"]):
        raise RuntimeError("Analysis-ready local file size does not match v1.5.3 manifest.")
    horizon = pd.read_csv(horizon_path)
    lookback = pd.read_csv(lookback_path)
    split = pd.read_csv(split_path)
    smart = pd.read_csv(smart_path)
    if not (horizon["horizon_days"].eq(spec["task"]["horizon_days"]).any()):
        raise RuntimeError("7-day horizon feasibility row is missing.")
    if not (
        lookback["lookback_window_days"].astype(str).eq(str(spec["task"]["lookback_days"])).any()
    ):
        raise RuntimeError("7-day lookback feasibility row is missing.")
    usable = smart[smart["prediction_feature_candidate"].astype(str).str.lower().eq("true")]
    expected_features = set(spec["feature_policy"]["smart_feature_candidates"])
    if set(usable["feature_name"].astype(str)) != expected_features:
        raise RuntimeError("SMART candidate inventory does not match classification spec.")
    return {
        "raw_sha": raw_sha,
        "analysis_ready_exists": analysis_ready.exists(),
        "analysis_ready_size_bytes": analysis_ready.stat().st_size,
        "full_year_rows": manifest["total_rows"],
        "full_year_assets": manifest["total_assets"],
        "full_year_event_count": manifest["event_count"],
        "feasible_split_rows": int(len(split)),
        "smart_candidate_count": int(len(usable)),
    }


def ensure_feature_dataset(
    spec: dict[str, Any],
    source_sha: str,
    *,
    rebuild: bool,
) -> dict[str, Any]:
    """Build or reuse the local-only 7d/7d feature dataset."""
    output = Path(spec["local_outputs"]["feature_dataset"])
    if output.exists() and not rebuild:
        row_count, positive_rows, positive_assets = summarize_feature_dataset(output)
        return {
            "status": "reused_existing",
            "path": str(output).replace("\\", "/"),
            "row_count": row_count,
            "positive_rows": positive_rows,
            "positive_assets": positive_assets,
            "size_bytes": output.stat().st_size,
        }
    tmp_output = output.with_suffix(output.suffix + ".tmp")
    if tmp_output.exists():
        tmp_output.unlink()
    config = TemporalAssetFeatureConfig(
        feature_columns=tuple(spec["feature_policy"]["smart_feature_candidates"]),
        horizon_days=int(spec["task"]["horizon_days"]),
        lookback_days=int(spec["task"]["lookback_days"]),
        case_study_version=spec["case_study_version"],
        source_sha256=source_sha,
    )
    result = write_temporal_asset_feature_dataset_from_csv(
        input_path=spec["source_inputs"]["analysis_ready_csv"],
        output_path=tmp_output,
        config=config,
        chunksize=int(spec["resource_budget"]["feature_construction_chunksize"]),
    )
    tmp_output.replace(output)
    result["status"] = "rebuilt"
    result["size_bytes"] = output.stat().st_size
    result["path"] = str(output).replace("\\", "/")
    return result


def summarize_feature_dataset(path: Path) -> tuple[int, int, int]:
    """Count rows, positives, and positive assets in a local feature dataset."""
    row_count = 0
    positive_rows = 0
    positive_assets: set[str] = set()
    for chunk in pd.read_csv(
        path,
        usecols=["serial_number", "target_failure_within_7d"],
        chunksize=250_000,
    ):
        target = pd.to_numeric(chunk["target_failure_within_7d"], errors="raise").astype(int)
        row_count += len(chunk)
        positive_rows += int(target.sum())
        positive_assets.update(chunk.loc[target.eq(1), "serial_number"].astype(str))
    return row_count, positive_rows, len(positive_assets)


def load_feature_dataset_for_modeling(spec: dict[str, Any]) -> pd.DataFrame:
    """Load only columns required for baseline modeling and diagnostics."""
    smart_cols = feature_columns_for_smart_only(spec["feature_policy"]["smart_feature_candidates"])
    metadata_cols = feature_columns_for_safe_metadata()
    usecols = [
        "serial_number",
        "asset_id_hash",
        "prediction_origin",
        "target_failure_within_7d",
        "model",
    ]
    usecols.extend(smart_cols)
    usecols.extend(metadata_cols)
    frame = pd.read_csv(spec["local_outputs"]["feature_dataset"], usecols=list(dict.fromkeys(usecols)))
    frame["prediction_origin"] = pd.to_datetime(frame["prediction_origin"], errors="raise")
    target = pd.to_numeric(frame["target_failure_within_7d"], errors="raise").astype(int)
    if set(target.unique()) - {0, 1}:
        raise ValueError("target_failure_within_7d must contain only 0 and 1")
    return frame


def build_classification_config(
    spec: dict[str, Any],
    source_sha: str,
) -> AssetTemporalClassificationConfig:
    """Convert JSON spec into classification dataclasses."""
    smart_features = spec["feature_policy"]["smart_feature_candidates"]
    smart_only = tuple(feature_columns_for_smart_only(smart_features))
    safe_metadata = tuple(feature_columns_for_safe_metadata())
    feature_sets = (
        FeatureSetConfig(
            name="smart_only_conservative",
            numeric_features=smart_only,
            categorical_features=(),
        ),
        FeatureSetConfig(
            name="smart_plus_safe_operational_metadata",
            numeric_features=smart_only + safe_metadata,
            categorical_features=("model",),
        ),
    )
    model_configs = tuple(
        AssetTemporalModelConfig(
            name=item["name"],
            estimator_type=item["estimator_type"],
            random_state=int(spec["random_state"]),
            max_training_rows=item.get("max_training_rows"),
        )
        for item in spec["model_configurations"]
    )
    if not model_configs:
        model_configs = default_asset_temporal_model_configs(int(spec["random_state"]))
    return AssetTemporalClassificationConfig(
        case_study_version=spec["case_study_version"],
        source_artifact=spec["local_outputs"]["feature_dataset"],
        source_sha256=source_sha,
        asset_column="serial_number",
        timestamp_column="prediction_origin",
        target_column="target_failure_within_7d",
        feature_sets=feature_sets,
        model_configs=model_configs,
        final_holdout_start=spec["validation_hierarchy"]["final_holdout_start"],
        random_state=int(spec["random_state"]),
        missing_rate_threshold=float(spec["preprocessing"]["missing_rate_threshold"]),
        near_constant_top_value_rate=float(spec["preprocessing"]["near_constant_top_value_rate"]),
        asset_test_size=float(spec["validation_hierarchy"]["asset_test_size"]),
        random_test_size=float(spec["validation_hierarchy"]["random_test_size"]),
        primary_weighting_policy=spec["repeated_origin_policy"]["primary_weighting"],
        weighting_policies=tuple(spec["repeated_origin_policy"]["weighting_policies"]),
        resource_budget=ResourceBudget(
            max_training_rows=int(spec["resource_budget"]["default_max_training_rows"]),
            random_state=int(spec["random_state"]),
            prediction_sample_max_rows=int(spec["resource_budget"]["prediction_sample_max_rows"]),
        ),
    )


def write_outputs(outputs: dict[str, pd.DataFrame], paths: dict[str, Path]) -> None:
    """Write compact tracked outputs and local prediction diagnostics."""
    name_map = {
        "metrics": "metrics",
        "split_diagnostics": "split_diagnostics",
        "model_summary": "model_summary",
        "asset_time_gap_summary": "asset_time_gap",
        "top_risk_summary": "top_risk",
        "threshold_summary": "threshold",
        "error_structure_summary": "error_structure",
        "classification_conclusion": "conclusion",
        "prediction_sample": "predictions",
    }
    for output_name, path_key in name_map.items():
        path = paths[path_key]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        outputs[output_name].to_csv(tmp, index=False)
        tmp.replace(path)


def output_paths(spec: dict[str, Any]) -> dict[str, Path]:
    """Return named output paths from the spec."""
    tracked = spec["tracked_outputs"]
    local = spec["local_outputs"]
    return {
        "predictions": Path(local["predictions"]),
        "metrics": Path(tracked["metrics"]),
        "split_diagnostics": Path(tracked["split_diagnostics"]),
        "model_summary": Path(tracked["model_summary"]),
        "asset_time_gap": Path(tracked["asset_time_gap_summary"]),
        "top_risk": Path(tracked["top_risk_summary"]),
        "threshold": Path(tracked["threshold_summary"]),
        "error_structure": Path(tracked["error_structure_summary"]),
        "conclusion": Path(tracked["classification_conclusion"]),
    }


def validate_tracked_outputs(paths: dict[str, Path]) -> None:
    """Ensure tracked compact outputs do not contain raw serials, paths, or secrets."""
    for name, path in paths.items():
        if name == "predictions":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"[A-Za-z]:\\\\", text) or "/Users/" in text or "/home/" in text:
            raise RuntimeError(f"Absolute local path found in {path}")
        lowered = text.lower()
        for token in ["kaggle_key", "kaggle_username", "password=", "secret=", "token="]:
            if token in lowered:
                raise RuntimeError(f"Credential-like token found in {path}")
        if "serial_number" in lowered:
            raise RuntimeError(f"Raw serial number field leaked into tracked output: {path}")


def parse_outputs(paths: dict[str, Path]) -> None:
    """Parse all generated CSV outputs and verify non-empty compact tables."""
    for name, path in paths.items():
        df = pd.read_csv(path)
        if name != "predictions" and df.empty:
            raise RuntimeError(f"Tracked output is empty: {path}")
        if any(str(column).startswith("Unnamed:") for column in df.columns):
            raise RuntimeError(f"Duplicate/index-like header found in {path}")


def build_console_summary(
    *,
    spec: dict[str, Any],
    preflight: dict[str, Any],
    feature_dataset_summary: dict[str, Any],
    outputs: dict[str, pd.DataFrame],
    paths: dict[str, Path],
    analysis_sha: str,
    runtime_seconds: float,
) -> dict[str, Any]:
    """Build a compact console summary for audit logs."""
    metrics = outputs["metrics"]
    model_summary = outputs["model_summary"]
    valid = metrics[metrics["status"].eq("valid")]
    combined = valid[valid["validation_type"].eq("primary_combined_asset_time")]
    return {
        "case_study_version": spec["case_study_version"],
        "preflight": preflight,
        "analysis_ready_sha256": analysis_sha,
        "feature_dataset": feature_dataset_summary,
        "valid_metric_rows": int(len(valid)),
        "combined_metric_rows": int(len(combined)),
        "best_primary_pr_auc": _safe_max(model_summary, "primary_median_pr_auc"),
        "best_combined_pr_auc": _safe_max(model_summary, "combined_pr_auc"),
        "model_status_counts": model_summary["model_status"].value_counts().to_dict()
        if not model_summary.empty
        else {},
        "runtime_seconds": runtime_seconds,
        "tracked_outputs": {key: str(value).replace("\\", "/") for key, value in paths.items() if key != "predictions"},
        "local_prediction_output": str(paths["predictions"]).replace("\\", "/"),
        "output_sizes": {key: value.stat().st_size for key, value in paths.items()},
    }


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe_max(df: pd.DataFrame, column: str) -> float | str:
    if df.empty or column not in df:
        return "unavailable"
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.max()) if not values.empty else "unavailable"


if __name__ == "__main__":
    main()
