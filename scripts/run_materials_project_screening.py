"""Run Materials Project descriptive property screening without API access."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.property_screening import (  # noqa: E402
    build_screening_summary,
    load_screening_spec,
    rank_screening_candidates,
)
from connectors.materials_project_connector import calculate_file_sha256  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Rank a local Materials Project normalized table using already "
            "available computed properties. This script does not call the "
            "Materials Project API and does not train a model."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Local normalized Materials Project CSV path.",
    )
    parser.add_argument(
        "--screening-spec",
        required=True,
        help="Credential-free property screening spec JSON path.",
    )
    parser.add_argument(
        "--results-output",
        required=True,
        help="Output full screening results CSV path.",
    )
    parser.add_argument(
        "--summary-output",
        required=True,
        help="Output compact top-N screening summary CSV path.",
    )
    return parser.parse_args()


def _credential_like_value_count(df: pd.DataFrame) -> int:
    text_columns = df.select_dtypes(exclude="number").columns
    count = 0
    for column in text_columns:
        count += int(
            df[column]
            .dropna()
            .astype(str)
            .str.contains(
                r"api[_-]?key|token|secret|credential|password|sk-",
                case=False,
                regex=True,
            )
            .sum()
        )
    return count


def _absolute_path_value_count(df: pd.DataFrame) -> int:
    text_columns = df.select_dtypes(exclude="number").columns
    count = 0
    for column in text_columns:
        count += int(
            df[column]
            .dropna()
            .astype(str)
            .str.contains(r"^[A-Za-z]:\\|^/|^\\\\", regex=True)
            .sum()
        )
    return count


def main() -> None:
    """Run descriptive screening and write full/compact outputs."""
    args = parse_args()
    input_path = Path(args.input)
    spec_path = Path(args.screening_spec)
    results_output = Path(args.results_output)
    summary_output = Path(args.summary_output)

    try:
        input_sha_before = calculate_file_sha256(input_path)
        spec = load_screening_spec(spec_path)
        df = pd.read_csv(input_path)
        results = rank_screening_candidates(df, spec)
        summary = build_screening_summary(results, spec)
        input_sha_after = calculate_file_sha256(input_path)
        if input_sha_before != input_sha_after:
            raise ValueError("Input CSV changed while running Materials Project screening.")
        if _credential_like_value_count(results) or _credential_like_value_count(summary):
            raise ValueError("Screening output contains credential-like values.")
        if _absolute_path_value_count(results) or _absolute_path_value_count(summary):
            raise ValueError("Screening output contains absolute path-like values.")
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Materials Project screening failed: {exc}", file=sys.stderr)
        sys.exit(1)

    results_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(results_output, index=False)
    summary.to_csv(summary_output, index=False)

    ranked = results[results["screening_status"].eq("ranked")]
    objective_properties = [objective["property"] for objective in spec["objectives"]]
    missing_objective_count = int(results["screening_status"].eq("missing_objective").sum())
    tie_count = int(ranked["overall_rank"].duplicated(keep=False).sum())
    top_preview_columns = [
        spec["identifier_column"],
        *spec["display_columns"],
        *objective_properties,
        "overall_rank",
        "composite_score",
    ]
    top_preview_columns = [
        column for column in top_preview_columns if column in summary.columns
    ]

    print(f"input: {input_path}")
    print(f"screening spec: {spec_path}")
    print(f"results output: {results_output}")
    print(f"summary output: {summary_output}")
    print(f"input sha256: {input_sha_before}")
    print(f"total rows: {len(results)}")
    print(f"filter pass/fail: {results['filter_status'].value_counts().to_dict()}")
    print(f"objective count: {len(spec['objectives'])}")
    print(f"objectives: {objective_properties}")
    print(f"ranked candidate count: {len(ranked)}")
    print(f"missing objective count: {missing_objective_count}")
    print(f"tie count: {tie_count}")
    print("top N candidates:")
    print(summary[top_preview_columns].to_string(index=False))
    print(f"credential included: {_credential_like_value_count(results) > 0}")
    print(f"absolute path included: {_absolute_path_value_count(results) > 0}")
    print(
        "output sizes bytes: "
        + str(
            {
                str(results_output): results_output.stat().st_size,
                str(summary_output): summary_output.stat().st_size,
            }
        )
    )
    print(
        "interpretation: descriptive screening over existing computed properties; "
        "not prediction or validation of experimental performance."
    )


if __name__ == "__main__":
    main()
