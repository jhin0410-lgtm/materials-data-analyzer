"""Run Smart Factory v1.4.5 trust-boundary closeout.

This script reads existing v1.4.4 compact classification artifacts only. It
does not fit models, tune thresholds, call networks, run SHAP, or regenerate
row-level predictions.
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

from analyzers.classification_trust import (  # noqa: E402
    ClassificationTrustConfig,
    build_trust_outputs,
    calculate_file_sha256,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run v1.4.5 Smart Factory trust-boundary closeout from existing "
            "compact classification artifacts. No model fitting, threshold "
            "tuning, SHAP, or network calls are performed."
        )
    )
    parser.add_argument(
        "--spec",
        default="data/case_studies/smart_factory/trust_spec_v1_4.json",
        help="v1.4.5 trust closeout specification.",
    )
    return parser.parse_args()


def main() -> None:
    """Run trust closeout and print a compact JSON summary."""
    args = parse_args()
    summary = run_trust_analysis(args)
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_trust_analysis(args: argparse.Namespace) -> dict[str, Any]:
    """Run trust analysis from parsed CLI arguments."""
    spec = load_json(args.spec)
    input_paths = {name: Path(path) for name, path in spec["input_artifacts"].items()}
    output_paths = {name: Path(path) for name, path in spec["tracked_output_paths"].items()}
    for name, path in input_paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Required input artifact missing: {name} -> {path}")
    before_sha = {name: calculate_file_sha256(path) for name, path in input_paths.items()}

    metrics = pd.read_csv(input_paths["classification_metrics"])
    split_diagnostics = pd.read_csv(input_paths["classification_split_diagnostics"])
    model_summary = pd.read_csv(input_paths["classification_model_summary"])
    random_temporal_gap = pd.read_csv(input_paths["random_temporal_gap"])
    threshold_summary = pd.read_csv(input_paths["threshold_summary"])
    error_structure = pd.read_csv(input_paths["error_structure_summary"])
    classification_conclusion = pd.read_csv(input_paths["classification_conclusion"])
    validate_required_columns(metrics, split_diagnostics, model_summary)

    classification_spec = load_json(input_paths["classification_spec"])
    classification_source = classification_spec["source_artifact"]
    source_sha = (
        metrics["source_sha256"].dropna().astype(str).iloc[0]
        if "source_sha256" in metrics.columns and not metrics.empty
        else ""
    )
    config = ClassificationTrustConfig(
        case_study_version=spec["case_study_version"],
        source_artifact=classification_source,
        source_sha256=source_sha,
        baseline_model_name=spec["baseline_model_name"],
        global_row_count=int(spec["prevalence_baseline_policy"]["row_count"]),
        global_failure_count=int(spec["prevalence_baseline_policy"]["failure_count"]),
        min_temporal_pr_auc_lift_over_prevalence=float(
            spec["model_eligibility_rules"]["min_temporal_pr_auc_lift_over_prevalence"]
        ),
        min_final_pr_auc_lift_over_prevalence=float(
            spec["model_eligibility_rules"]["min_final_pr_auc_lift_over_prevalence"]
        ),
        min_temporal_dummy_lift_fold_rate=float(
            spec["model_eligibility_rules"]["min_temporal_dummy_lift_fold_rate"]
        ),
        max_temporal_iqr_pr_auc=float(
            spec["model_eligibility_rules"]["max_temporal_iqr_pr_auc"]
        ),
        max_random_temporal_pr_auc_gap=float(
            spec["model_eligibility_rules"]["max_random_temporal_pr_auc_gap"]
        ),
        min_threshold_recall=float(spec["model_eligibility_rules"]["min_threshold_recall"]),
        min_threshold_precision=float(
            spec["model_eligibility_rules"]["min_threshold_precision"]
        ),
        min_supported_fold_count=int(
            spec["model_eligibility_rules"]["min_supported_fold_count"]
        ),
    )
    outputs = build_trust_outputs(
        metrics=metrics,
        split_diagnostics=split_diagnostics,
        model_summary=model_summary,
        random_temporal_gap=random_temporal_gap,
        threshold_summary=threshold_summary,
        error_structure=error_structure,
        classification_conclusion=classification_conclusion,
        config=config,
    )
    validate_release_gate(outputs, baseline_model_name=spec["baseline_model_name"])
    for name, frame in outputs.items():
        validate_no_local_paths_or_auth_material(frame, name)
        validate_single_header(frame, name)
        output_paths[name].parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output_paths[name], index=False)

    after_sha = {name: calculate_file_sha256(path) for name, path in input_paths.items()}
    if before_sha != after_sha:
        changed = [name for name in before_sha if before_sha[name] != after_sha[name]]
        raise RuntimeError("Input artifact changed during trust analysis: " + ", ".join(changed))
    for path in output_paths.values():
        pd.read_csv(path, nrows=5)

    eligibility = outputs["model_eligibility"]
    trust = outputs["trust_summary"]
    return {
        "input_artifact_count": len(input_paths),
        "input_sha_unchanged": before_sha == after_sha,
        "model_count": int(eligibility["model_name"].nunique()),
        "eligibility_status_counts": eligibility["eligibility_status"].value_counts().to_dict(),
        "representative_model_selected": bool(
            eligibility["representative_model_selected"].astype(bool).any()
        ),
        "release_readiness": _trust_value(outputs["closeout_conclusion"], "v1_4_release_readiness"),
        "best_temporal_median_pr_auc": _trust_value(trust, "best_temporal_median_pr_auc"),
        "tracked_outputs": {name: str(path).replace("\\", "/") for name, path in output_paths.items()},
    }


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON object."""
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")
    return data


def validate_required_columns(
    metrics: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
    model_summary: pd.DataFrame,
) -> None:
    """Validate the compact input schema needed for closeout."""
    metric_required = {
        "split_id",
        "validation_type",
        "model_name",
        "average_precision",
        "test_failures",
        "status",
    }
    split_required = {
        "split_id",
        "validation_type",
        "train_rows",
        "test_rows",
        "leakage_status",
    }
    model_required = {
        "model_name",
        "temporal_median_pr_auc",
        "final_holdout_pr_auc",
        "random_reference_pr_auc",
    }
    for name, frame, required in [
        ("classification_metrics", metrics, metric_required),
        ("classification_split_diagnostics", split_diagnostics, split_required),
        ("classification_model_summary", model_summary, model_required),
    ]:
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"Missing {name} column(s): " + ", ".join(missing))


def validate_release_gate(
    outputs: dict[str, pd.DataFrame],
    *,
    baseline_model_name: str,
) -> None:
    """Guard against accidental representative selection or unsupported claims."""
    eligibility = outputs["model_eligibility"]
    if eligibility["representative_model_selected"].astype(bool).any():
        raise RuntimeError("Representative model was selected; closeout gate expected none.")
    non_dummy = eligibility[~eligibility["model_name"].eq(baseline_model_name)]
    if not non_dummy["eligibility_status"].eq("diagnostic_only").all():
        raise RuntimeError("Current v1.4.4 non-dummy models should remain diagnostic_only.")
    claims = outputs["claim_boundary"]
    prohibited = claims[claims["status"].eq("prohibited")]
    if prohibited.empty:
        raise RuntimeError("Claim boundary must include prohibited claims.")


def validate_no_local_paths_or_auth_material(df: pd.DataFrame, name: str) -> None:
    """Reject tracked outputs with absolute paths or auth-like material."""
    text = df.to_csv(index=False)
    patterns = [
        (r"[A-Za-z]:\\", "Windows absolute path"),
        (r"/home/|/Users/|/mnt/", "Unix-like absolute path"),
        (r"api[_-]?key|secret|token|password", "auth-like string"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise RuntimeError(f"{label} detected in tracked output: {name}")


def validate_single_header(df: pd.DataFrame, name: str) -> None:
    """Ensure generated tables do not contain duplicated headers."""
    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Duplicate header(s) detected in {name}: {duplicated}")


def _trust_value(frame: pd.DataFrame, field: str) -> str:
    if "field" not in frame.columns or "value" not in frame.columns:
        return ""
    subset = frame[frame["field"].eq(field)]
    return "" if subset.empty else str(subset["value"].iloc[0])


if __name__ == "__main__":
    main()
