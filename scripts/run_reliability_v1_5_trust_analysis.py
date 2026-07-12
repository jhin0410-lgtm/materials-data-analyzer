"""Run Reliability v1.5.5 trust-boundary closeout.

This script reads existing v1.5.3/v1.5.4 compact artifacts only. It does not
fit models, tune thresholds, regenerate labels, run SHAP, call networks, or
read local row-level predictions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.reliability_trust import (  # noqa: E402
    ReliabilityTrustConfig,
    build_reliability_trust_outputs,
    calculate_file_sha256,
    validate_no_forbidden_output_content,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run v1.5.5 Reliability trust-boundary closeout from compact "
            "classification artifacts. No model fitting or row-level prediction "
            "generation is performed."
        )
    )
    parser.add_argument(
        "--spec",
        default="data/case_studies/reliability/trust_spec_v1_5.json",
        help="v1.5.5 trust closeout specification.",
    )
    return parser.parse_args()


def main() -> None:
    """Run trust closeout and print a compact JSON summary."""
    summary = run_trust_analysis(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_trust_analysis(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the v1.5.5 trust closeout from existing compact artifacts."""
    spec = load_json(args.spec)
    input_paths = {name: Path(path) for name, path in spec["input_artifacts"].items()}
    output_paths = {name: Path(path) for name, path in spec["tracked_outputs"].items()}
    for name, path in input_paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Required input artifact missing: {name} -> {path}")
    if "raw_archive" in spec.get("source_provenance", {}):
        raw_archive = Path(spec["source_provenance"]["raw_archive"])
        if not raw_archive.exists():
            raise FileNotFoundError(f"Raw archive missing for source SHA check: {raw_archive}")
        raw_sha = calculate_file_sha256(raw_archive)
        if raw_sha != spec["source_provenance"]["raw_archive_sha256"]:
            raise RuntimeError("Raw source archive SHA mismatch.")

    before_sha = {name: calculate_file_sha256(path) for name, path in input_paths.items()}
    frames = {
        "metrics": pd.read_csv(input_paths["classification_metrics"]),
        "split_diagnostics": pd.read_csv(input_paths["classification_split_diagnostics"]),
        "model_summary": pd.read_csv(input_paths["classification_model_summary"]),
        "top_risk_summary": pd.read_csv(input_paths["top_risk_summary"]),
        "threshold_summary": pd.read_csv(input_paths["threshold_summary"]),
        "error_structure_summary": pd.read_csv(input_paths["error_structure_summary"]),
        "classification_conclusion": pd.read_csv(input_paths["classification_conclusion"]),
        "full_readiness_summary": pd.read_csv(input_paths["full_readiness_summary"]),
        "event_integrity_summary": pd.read_csv(input_paths["event_integrity_summary"]),
        "censoring_summary": pd.read_csv(input_paths["censoring_summary"]),
    }
    classification_conclusion = _field_value_map(frames["classification_conclusion"])
    if classification_conclusion.get("representative_model") not in {
        "none_selected",
        "none",
    }:
        raise RuntimeError("v1.5.4 representative model must be none_selected.")

    source_artifact = str(frames["metrics"]["source_artifact"].dropna().astype(str).iloc[0])
    source_sha = str(frames["metrics"]["source_sha256"].dropna().astype(str).iloc[0])
    config = ReliabilityTrustConfig(
        case_study_version=spec["case_study_version"],
        source_artifact=source_artifact,
        source_sha256=source_sha,
        baseline_model_name=spec["baseline_model_name"],
        eligible_origins=int(spec["prevalence_baseline_policy"]["eligible_origins"]),
        positive_rows=int(spec["prevalence_baseline_policy"]["positive_rows"]),
        positive_assets=int(spec["prevalence_baseline_policy"]["positive_assets"]),
        total_assets=int(spec["prevalence_baseline_policy"]["total_assets"]),
        top_risk_reference_fraction=float(spec["top_risk_interpretation"]["reference_fraction"]),
        min_candidate_combined_lift_over_prevalence=float(
            spec["model_eligibility_rules"]["min_candidate_combined_lift_over_prevalence"]
        ),
        min_candidate_top_1_lift=float(
            spec["model_eligibility_rules"]["min_candidate_top_1_lift"]
        ),
        min_candidate_top_1_failed_asset_capture=float(
            spec["model_eligibility_rules"]["min_candidate_top_1_failed_asset_capture"]
        ),
    )
    outputs = build_reliability_trust_outputs(config=config, **frames)
    validate_release_gate(outputs)
    validate_no_forbidden_output_content(outputs)
    for name, frame in outputs.items():
        output_path = output_paths[name]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output_path, index=False)
        pd.read_csv(output_path, nrows=5)

    after_sha = {name: calculate_file_sha256(path) for name, path in input_paths.items()}
    if before_sha != after_sha:
        changed = [name for name in before_sha if before_sha[name] != after_sha[name]]
        raise RuntimeError("Input artifacts changed during trust analysis: " + ", ".join(changed))
    return build_console_summary(outputs, output_paths, before_sha)


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON object."""
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")
    return data


def validate_release_gate(outputs: dict[str, pd.DataFrame]) -> None:
    """Validate closeout release gates."""
    eligibility = outputs["model_eligibility"]
    if eligibility["representative_model_selected"].astype(bool).any():
        raise RuntimeError("Representative model must remain unselected.")
    non_dummy = eligibility[~eligibility["model_name"].eq("dummy_prior")]
    if not non_dummy["eligibility_status"].isin(
        ["diagnostic_only", "limited_predictive_evidence", "candidate_for_further_validation"]
    ).all():
        raise RuntimeError("Unexpected non-dummy eligibility status.")
    closeout = _field_value_map(outputs["closeout_conclusion"])
    if closeout.get("representative_model") != "none_selected":
        raise RuntimeError("Closeout conclusion must keep representative_model=none_selected.")
    claims = outputs["claim_boundary"]
    prohibited = claims[claims["status"].eq("prohibited")]
    if prohibited.empty:
        raise RuntimeError("Claim boundary must include prohibited claims.")


def build_console_summary(
    outputs: dict[str, pd.DataFrame],
    output_paths: dict[str, Path],
    input_sha: dict[str, str],
) -> dict[str, Any]:
    """Build a deterministic console summary."""
    eligibility = outputs["model_eligibility"]
    trust = _field_value_map(outputs["trust_summary"])
    closeout = _field_value_map(outputs["closeout_conclusion"])
    return {
        "input_artifact_count": len(input_sha),
        "input_sha_unchanged": True,
        "model_eligibility_rows": int(len(eligibility)),
        "eligibility_status_counts": eligibility["eligibility_status"].value_counts().to_dict(),
        "representative_model": closeout.get("representative_model"),
        "release_readiness": closeout.get("v1_5_release_readiness"),
        "best_primary_median_pr_auc": trust.get("best_primary_median_pr_auc"),
        "best_combined_pr_auc": trust.get("best_combined_pr_auc"),
        "tracked_outputs": {name: str(path).replace("\\", "/") for name, path in output_paths.items()},
    }


def _field_value_map(frame: pd.DataFrame) -> dict[str, str]:
    if {"field", "value"}.issubset(frame.columns):
        return {str(row["field"]): str(row["value"]) for _, row in frame.iterrows()}
    return {}


if __name__ == "__main__":
    main()
