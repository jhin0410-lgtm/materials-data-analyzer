"""Build Materials Project query contract artifacts without API access."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.materials_project_connector import (  # noqa: E402
    build_property_inventory,
    calculate_file_sha256,
    create_provenance_manifest,
    load_query_spec,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create credential-free Materials Project query manifest and "
            "property inventory artifacts from a local processed CSV."
        )
    )
    parser.add_argument("--input", required=True, help="Local processed CSV path.")
    parser.add_argument("--query-spec", required=True, help="Query specification JSON.")
    parser.add_argument(
        "--manifest-output",
        required=True,
        help="Output provenance manifest JSON path.",
    )
    parser.add_argument(
        "--property-inventory-output",
        required=True,
        help="Output property inventory CSV path.",
    )
    return parser.parse_args()


def _repo_relative(path: str | Path) -> str:
    """Return a repository-relative POSIX path when possible."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _formula_elements(formula: object) -> set[str]:
    """Extract element-like tokens from a formula string for consistency checks."""
    if pd.isna(formula):
        return set()
    return set(re.findall(r"[A-Z][a-z]?", str(formula)))


def _build_consistency_checks(
    df: pd.DataFrame,
    query_spec: dict[str, object],
    manifest: dict[str, object],
) -> dict[str, object]:
    """Summarize consistency between query spec and local artifact."""
    required_elements = set(query_spec["required_elements"])
    mapped_requested_columns = set(manifest["mapped_requested_columns"])
    columns = set(df.columns)
    formula_contains_required_count = 0
    binary_only_count = 0
    if "formula" in df.columns:
        for formula in df["formula"]:
            elements = _formula_elements(formula)
            if required_elements.issubset(elements):
                formula_contains_required_count += 1
            if elements == required_elements:
                binary_only_count += 1

    return {
        "requested_columns_match": sorted(mapped_requested_columns) == sorted(columns),
        "missing_requested_columns": manifest["missing_requested_columns"],
        "extra_columns": manifest["extra_columns"],
        "identifier_column_present": manifest["identifier_column"] in df.columns,
        "formula_contains_required_elements_count": formula_contains_required_count,
        "formula_binary_only_count": binary_only_count,
        "row_count": int(len(df)),
    }


def _ensure_safe_manifest(manifest: dict[str, object]) -> None:
    """Fail if generated manifest reports credential or absolute-path content."""
    if manifest["credential_included"]:
        raise ValueError("Generated manifest indicates credential-like values in the CSV.")
    if manifest["absolute_path_included"]:
        raise ValueError("Generated manifest indicates absolute path-like values in the CSV.")


def main() -> None:
    """Build query contract artifacts from local Materials Project CSV."""
    args = parse_args()
    input_path = Path(args.input)
    query_spec_path = Path(args.query_spec)
    manifest_output = Path(args.manifest_output)
    property_inventory_output = Path(args.property_inventory_output)

    try:
        input_sha_before = calculate_file_sha256(input_path)
        query_spec = load_query_spec(query_spec_path)
        df = pd.read_csv(input_path)
        manifest = create_provenance_manifest(
            df=df,
            artifact_path=_repo_relative(input_path),
            query_spec=query_spec,
            query_spec_path=_repo_relative(query_spec_path),
        )
        manifest["consistency_checks"] = _build_consistency_checks(
            df,
            query_spec,
            manifest,
        )
        _ensure_safe_manifest(manifest)
        property_inventory = build_property_inventory(df)
        input_sha_after = calculate_file_sha256(input_path)
        if input_sha_before != input_sha_after:
            raise ValueError("Input CSV changed while building query contract artifacts.")
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Materials Project query contract build failed: {exc}", file=sys.stderr)
        sys.exit(1)

    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    property_inventory_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    property_inventory.to_csv(property_inventory_output, index=False)

    checks = manifest["consistency_checks"]
    print(f"input: {input_path}")
    print(f"query spec: {query_spec_path}")
    print(f"manifest output: {manifest_output}")
    print(f"property inventory output: {property_inventory_output}")
    print(f"row count: {manifest['row_count']}")
    print(f"column count: {manifest['column_count']}")
    print(f"artifact sha256: {manifest['artifact_sha256']}")
    print(f"query provenance status: {manifest['query_provenance_status']}")
    print(f"requested columns match: {checks['requested_columns_match']}")
    print(f"missing requested columns: {checks['missing_requested_columns']}")
    print(f"extra columns: {checks['extra_columns']}")
    print(f"duplicate identifiers: {manifest['duplicate_identifier_count']}")
    print(
        "formula rows containing required elements: "
        + str(checks["formula_contains_required_elements_count"])
    )
    print(f"binary-only formula rows: {checks['formula_binary_only_count']}")
    print(f"credential included: {manifest['credential_included']}")
    print(f"absolute path included: {manifest['absolute_path_included']}")
    print(
        "property semantic roles: "
        + str(property_inventory["semantic_role"].value_counts(dropna=False).to_dict())
    )
    print(
        "target candidate columns: "
        + str(
            property_inventory.loc[
                property_inventory["target_candidate"].astype(bool),
                "column_name",
            ].tolist()
        )
    )
    print(
        "leakage candidate columns: "
        + str(
            property_inventory.loc[
                property_inventory["leakage_risk"].eq("leakage candidate"),
                "column_name",
            ].tolist()
        )
    )
    print(
        "output sizes bytes: "
        + str(
            {
                str(manifest_output): manifest_output.stat().st_size,
                str(property_inventory_output): property_inventory_output.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    main()
