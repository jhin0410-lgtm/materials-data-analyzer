"""Build Materials Project normalized local table and quality summary."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.materials_project_connector import calculate_file_sha256  # noqa: E402
from loaders.materials_project_loader import (  # noqa: E402
    build_quality_summary,
    load_schema_contract,
    normalize_materials_project_dataframe,
    summarize_actual_schema,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate and conservatively normalize a local Materials Project "
            "processed CSV without calling the Materials Project API."
        )
    )
    parser.add_argument("--input", required=True, help="Local Materials Project CSV path.")
    parser.add_argument(
        "--schema-contract",
        required=True,
        help="Materials Project schema contract JSON path.",
    )
    parser.add_argument(
        "--normalized-output",
        required=True,
        help="Output normalized local artifact CSV path.",
    )
    parser.add_argument(
        "--quality-summary-output",
        required=True,
        help="Output compact quality summary CSV path.",
    )
    return parser.parse_args()


def _formula_elements(formula: object) -> set[str]:
    if pd.isna(formula):
        return set()
    return set(re.findall(r"[A-Z][a-z]?", str(formula)))


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
    """Build normalized and quality-summary artifacts."""
    args = parse_args()
    input_path = Path(args.input)
    schema_contract_path = Path(args.schema_contract)
    normalized_output = Path(args.normalized_output)
    quality_summary_output = Path(args.quality_summary_output)

    try:
        input_sha_before = calculate_file_sha256(input_path)
        contract = load_schema_contract(schema_contract_path)
        source_df = pd.read_csv(input_path)
        actual_schema = summarize_actual_schema(source_df, contract)
        normalized_df, audit = normalize_materials_project_dataframe(source_df, contract)
        quality_summary = build_quality_summary(normalized_df, contract, audit)
        input_sha_after = calculate_file_sha256(input_path)
        if input_sha_before != input_sha_after:
            raise ValueError("Input CSV changed while building normalized artifacts.")
        if _credential_like_value_count(normalized_df):
            raise ValueError("Normalized output contains credential-like values.")
        if _absolute_path_value_count(normalized_df):
            raise ValueError("Normalized output contains absolute path-like values.")
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Materials Project normalization failed: {exc}", file=sys.stderr)
        sys.exit(1)

    normalized_output.parent.mkdir(parents=True, exist_ok=True)
    quality_summary_output.parent.mkdir(parents=True, exist_ok=True)
    normalized_df.to_csv(normalized_output, index=False)
    quality_summary.to_csv(quality_summary_output, index=False)

    required_elements = set(contract["quality_rules"].get("required_elements", []))
    formula_elements = normalized_df["formula"].map(_formula_elements)
    fe_rows = int(formula_elements.map(lambda elements: "Fe" in elements).sum())
    si_rows = int(formula_elements.map(lambda elements: "Si" in elements).sum())
    both_rows = int(
        formula_elements.map(lambda elements: required_elements.issubset(elements)).sum()
    )
    binary_rows = int(formula_elements.map(lambda elements: elements == required_elements).sum())
    multinary_rows = both_rows - binary_rows
    conversion_failures = int(sum(audit["conversion_failures_by_column"].values()))
    nonfinite_count = int(sum(audit["nonfinite_by_column"].values()))
    missing_numeric = int(
        normalized_df[
            [
                mapping["canonical_column"]
                for mapping in contract["column_mappings"]
                if mapping["expected_dtype"] != "string"
            ]
        ]
        .isna()
        .sum()
        .sum()
    )
    target_coverages = {
        mapping["canonical_column"]: int(normalized_df[mapping["canonical_column"]].notna().sum())
        for mapping in contract["column_mappings"]
        if mapping["target_candidate"]
    }

    print(f"input: {input_path}")
    print(f"schema contract: {schema_contract_path}")
    print(f"normalized output: {normalized_output}")
    print(f"quality summary output: {quality_summary_output}")
    print(f"input sha256: {input_sha_before}")
    print(f"input row count: {len(source_df)}")
    print(f"output row count: {len(normalized_df)}")
    print(f"source columns: {source_df.columns.tolist()}")
    print(
        "canonical columns: "
        + str([mapping["canonical_column"] for mapping in contract["column_mappings"]])
    )
    print(
        "quality status counts: "
        + str(normalized_df["quality_status"].value_counts(dropna=False).to_dict())
    )
    print(
        "valid/warning/invalid rows: "
        + str(
            {
                "valid": int(normalized_df["quality_status"].eq("valid").sum()),
                "warning": int(normalized_df["quality_status"].eq("warning").sum()),
                "invalid": int(normalized_df["quality_status"].eq("invalid").sum()),
            }
        )
    )
    print(f"identifier coverage: {int(normalized_df['material_id'].notna().sum())}")
    print(f"duplicate identifiers: {int(normalized_df['material_id'].duplicated().sum())}")
    print(f"Fe rows: {fe_rows}")
    print(f"Si rows: {si_rows}")
    print(f"Fe and Si rows: {both_rows}")
    print(f"binary Fe-Si rows: {binary_rows}")
    print(f"multinary Fe-Si-containing rows: {multinary_rows}")
    print(f"numeric conversion failures: {conversion_failures}")
    print(f"nonfinite numeric values: {nonfinite_count}")
    print(f"missing numeric property values: {missing_numeric}")
    print(f"constant columns: {audit['constant_columns']}")
    print(f"target candidate coverage: {target_coverages}")
    print(
        "semantic roles: "
        + str(actual_schema["semantic_role"].value_counts(dropna=False).to_dict())
    )
    print(f"credential included: {_credential_like_value_count(normalized_df) > 0}")
    print(f"absolute path included: {_absolute_path_value_count(normalized_df) > 0}")
    print(
        "output sizes bytes: "
        + str(
            {
                str(normalized_output): normalized_output.stat().st_size,
                str(quality_summary_output): quality_summary_output.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    main()
