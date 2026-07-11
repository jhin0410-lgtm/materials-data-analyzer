"""Run Smart Factory v1.4.4 time-aware classification baselines.

This script performs no network/API calls and does not regenerate source data.
It reads the local-only SECOM analysis-ready table, verifies source SHA values,
runs fixed classical baselines, writes local row-level predictions, and writes
compact tracked summaries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.temporal_classification_validation import (  # noqa: E402
    ClassificationModelConfig,
    ClassificationValidationConfig,
    calculate_file_sha256,
    evaluate_temporal_classification,
    write_classification_outputs,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run v1.4.4 Smart Factory SECOM time-aware classification baselines. "
            "No network calls, hyperparameter tuning, SHAP, SMOTE, or production "
            "readiness claims are performed."
        )
    )
    parser.add_argument(
        "--spec",
        default="data/case_studies/smart_factory/classification_spec_v1_4.json",
        help="v1.4.4 classification specification.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Override analysis-ready local CSV path from the spec.",
    )
    parser.add_argument(
        "--split-feasibility",
        default=None,
        help="Override split feasibility CSV path from the spec.",
    )
    return parser.parse_args()


def main() -> None:
    """Run validation and print compact JSON summary."""
    args = parse_args()
    summary = run_classification(args)
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_classification(args: argparse.Namespace) -> dict[str, Any]:
    """Run the v1.4.4 classification workflow from parsed arguments."""
    spec = load_json(args.spec)
    input_path = Path(args.input or spec["source_artifact"])
    split_path = Path(args.split_feasibility or spec["split_definitions_source"])
    output_paths = _output_paths(spec)

    preflight = run_preflight_checks(spec, input_path, split_path)
    analysis_sha_before = calculate_file_sha256(input_path)
    analysis = pd.read_csv(input_path)
    split_plan = pd.read_csv(split_path)

    feature_columns = [
        column
        for column in analysis.columns
        if str(column).startswith(spec["feature_column_prefix"])
    ]
    model_configs = [
        ClassificationModelConfig(
            name=item["name"],
            estimator_type=item["estimator_type"],
            random_state=int(spec["random_state"]),
        )
        for item in spec["model_configurations"]
    ]
    config = ClassificationValidationConfig(
        case_study_version=spec["case_study_version"],
        source_artifact=str(input_path).replace("\\", "/"),
        source_sha256=analysis_sha_before,
        identifier_column=spec["identifier_column"],
        target_column=spec["target_definition"]["target_column"],
        timestamp_column=spec["timestamp_column"],
        feature_columns=feature_columns,
        chronological_rank_column=spec["chronological_rank_column"],
        source_order_column=spec["source_order_column"],
        random_state=int(spec["random_state"]),
        missing_rate_threshold=float(
            spec["preprocessing_policy"]["missing_rate_removal_threshold"]
        ),
        near_constant_top_value_rate=float(
            spec["preprocessing_policy"]["near_constant_top_value_rate"]
        ),
        model_configs=model_configs,
    )
    outputs = evaluate_temporal_classification(analysis, split_plan, config)
    for name, df in outputs.items():
        if name != "predictions":
            validate_no_credentials_or_absolute_paths(df, name)
            validate_single_header(df, name)

    write_classification_outputs(outputs, **output_paths)

    analysis_sha_after = calculate_file_sha256(input_path)
    if analysis_sha_before != analysis_sha_after:
        raise RuntimeError("Analysis-ready source CSV changed during classification.")

    parse_outputs([Path(path) for path in output_paths.values()])
    summary = build_console_summary(outputs, preflight, output_paths)
    summary["analysis_ready_sha256"] = analysis_sha_after
    summary["analysis_ready_sha_unchanged"] = analysis_sha_before == analysis_sha_after
    summary["output_sizes"] = {
        key: Path(path).stat().st_size for key, path in output_paths.items()
    }
    return summary


def run_preflight_checks(
    spec: dict[str, Any],
    input_path: Path,
    split_path: Path,
) -> dict[str, Any]:
    """Validate source, target, ordering, and split readiness before modeling."""
    if not input_path.exists():
        raise FileNotFoundError(f"Analysis-ready local file is missing: {input_path}")
    if not split_path.exists():
        raise FileNotFoundError(f"Split feasibility CSV is missing: {split_path}")
    manifest = load_json(spec["source_manifest"])
    raw_sha_status = verify_manifest_raw_sha(manifest)
    analysis = pd.read_csv(input_path)
    if len(analysis) != int(spec["expected_row_count"]):
        raise ValueError(
            f"Unexpected analysis-ready row count: {len(analysis)} "
            f"!= {spec['expected_row_count']}"
        )
    target_column = spec["target_definition"]["target_column"]
    target_values = set(pd.to_numeric(analysis[target_column], errors="raise").astype(int))
    if target_values != {0, 1}:
        raise ValueError(f"Unexpected target values: {sorted(target_values)}")
    fail_count = int(analysis[target_column].sum())
    if fail_count != int(spec["expected_failure_count"]):
        raise ValueError(
            f"Unexpected failure count: {fail_count} != {spec['expected_failure_count']}"
        )
    sample_index = pd.to_numeric(analysis[spec["identifier_column"]], errors="raise").astype(int)
    expected_index = pd.Series(range(len(analysis)), index=analysis.index)
    if not sample_index.reset_index(drop=True).equals(expected_index):
        raise ValueError("sample_index must be contiguous from 0 in source order.")
    parsed = pd.to_datetime(analysis[spec["timestamp_column"]], errors="coerce")
    parse_failure_count = int(parsed.isna().sum())
    if parse_failure_count:
        raise ValueError(f"Timestamp parse failures found: {parse_failure_count}")
    chronological_consistency = check_chronological_consistency(analysis, spec)
    if not chronological_consistency["ready"]:
        raise ValueError(chronological_consistency["reason"])
    split_plan = pd.read_csv(split_path)
    feasible = split_plan[
        split_plan["feasibility_status"].astype(str).str.lower().eq("feasible")
    ]
    if feasible.empty:
        raise ValueError("No feasible time-aware split is available.")
    return {
        "raw_sha_status": raw_sha_status,
        "analysis_rows": int(len(analysis)),
        "failure_count": fail_count,
        "timestamp_parse_failure_count": parse_failure_count,
        "chronological_consistency": chronological_consistency["reason"],
        "feasible_split_count": int(len(feasible)),
    }


def verify_manifest_raw_sha(manifest: dict[str, Any]) -> str:
    """Verify raw SECOM source hashes listed in the acquisition manifest."""
    base = Path("data/raw/smart_factory/secom")
    statuses = []
    for item in manifest.get("raw_files", []):
        path = base / item["relative_path"]
        if not path.exists():
            raise FileNotFoundError(f"Raw source file listed in manifest is missing: {path}")
        observed = calculate_file_sha256(path)
        expected = item["sha256"]
        if observed != expected:
            raise RuntimeError(f"Raw source SHA mismatch for {item['relative_path']}")
        statuses.append(item["relative_path"])
    return "verified:" + ",".join(statuses)


def check_chronological_consistency(
    analysis: pd.DataFrame,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Check that source-order timestamps align with chronological ranks."""
    timestamp_column = spec["timestamp_column"]
    source_order_column = spec["source_order_column"]
    rank_column = spec["chronological_rank_column"]
    ordered_index = (
        analysis[[timestamp_column, source_order_column]]
        .assign(_timestamp=pd.to_datetime(analysis[timestamp_column], errors="coerce"))
        .sort_values(
            ["_timestamp", source_order_column],
            ascending=[True, True],
            kind="mergesort",
        )
        .index
    )
    observed_ranks = pd.Series(range(len(analysis)), index=ordered_index).sort_index()
    expected_ranks = pd.to_numeric(analysis[rank_column], errors="raise").astype(int)
    if not observed_ranks.reset_index(drop=True).equals(expected_ranks.reset_index(drop=True)):
        return {
            "ready": False,
            "reason": "chronological_rank is inconsistent with timestamp/source-order sorting",
        }
    source_time = pd.to_datetime(analysis[timestamp_column], errors="coerce")
    monotonic = bool(source_time.is_monotonic_increasing)
    inversions = int((source_time.diff().dt.total_seconds().fillna(0) < 0).sum())
    if inversions:
        return {"ready": False, "reason": f"source-order chronological inversions={inversions}"}
    return {
        "ready": True,
        "reason": f"source_order_monotonic={monotonic}; chronological_inversions={inversions}",
    }


def build_console_summary(
    outputs: dict[str, pd.DataFrame],
    preflight: dict[str, Any],
    output_paths: dict[str, str],
) -> dict[str, Any]:
    """Build a compact console summary."""
    metrics = outputs["metrics"]
    model_summary = outputs["model_summary"]
    valid = metrics[metrics["status"].eq("valid")]
    temporal = valid[valid["validation_type"].eq("primary_temporal")]
    final = valid[valid["split_id"].astype(str).str.contains("final_holdout")]
    return {
        "preflight": preflight,
        "model_count": int(model_summary["model_name"].nunique()),
        "valid_metric_rows": int(len(valid)),
        "temporal_metric_rows": int(len(temporal)),
        "final_holdout_metric_rows": int(len(final)),
        "prediction_rows": int(len(outputs["predictions"])),
        "best_temporal_pr_auc": _best_metric(model_summary, "temporal_median_pr_auc"),
        "best_final_holdout_pr_auc": _best_metric(model_summary, "final_holdout_pr_auc"),
        "model_status_counts": model_summary["model_status"].value_counts().to_dict(),
        "tracked_outputs": {
            key: str(path).replace("\\", "/")
            for key, path in output_paths.items()
            if key != "predictions_path"
        },
        "local_only_prediction_output": str(output_paths["predictions_path"]).replace("\\", "/"),
    }


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON object."""
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")
    return data


def _output_paths(spec: dict[str, Any]) -> dict[str, str]:
    local = spec["local_output_paths"]
    tracked = spec["tracked_output_paths"]
    return {
        "predictions_path": local["classification_predictions"],
        "metrics_path": tracked["classification_metrics"],
        "split_diagnostics_path": tracked["classification_split_diagnostics"],
        "model_summary_path": tracked["classification_model_summary"],
        "random_temporal_gap_path": tracked["random_temporal_gap"],
        "threshold_summary_path": tracked["threshold_summary"],
        "error_structure_path": tracked["error_structure_summary"],
        "conclusion_path": tracked["classification_conclusion"],
    }


def validate_no_credentials_or_absolute_paths(df: pd.DataFrame, name: str) -> None:
    """Reject tracked outputs that contain absolute paths or credential text."""
    text = df.to_csv(index=False)
    patterns = [
        (r"[A-Za-z]:\\", "Windows absolute path"),
        (r"/home/|/Users/|/mnt/", "Unix-like absolute path"),
        (r"api[_-]?key|secret|credential|token", "credential-like string"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise RuntimeError(f"{label} detected in tracked output: {name}")


def validate_single_header(df: pd.DataFrame, name: str) -> None:
    """Basic duplicate-header guard for generated CSV tables."""
    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Duplicate header(s) detected in {name}: {duplicated}")


def parse_outputs(paths: list[Path]) -> None:
    """Ensure generated CSV outputs are readable."""
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Expected output was not created: {path}")
        pd.read_csv(path, nrows=5)


def _best_metric(model_summary: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(model_summary[column], errors="coerce").dropna()
    return float(values.max()) if len(values) else float("nan")


if __name__ == "__main__":
    main()
