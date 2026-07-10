"""Build Materials Project v1.3.3 composition-only descriptor artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from features.materials_composition import (  # noqa: E402
    run_descriptor_pipeline,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build Materials Project v1.3.3 composition-only descriptors and "
            "readiness summaries without API calls or model training."
        )
    )
    parser.add_argument(
        "--input",
        default="data/processed/materials_project_v1_3_acquired.csv",
        help="v1.3 acquired Materials Project CSV.",
    )
    parser.add_argument(
        "--manifest",
        default="data/processed/materials_project_v1_3_acquisition_manifest.json",
        help="v1.3 acquisition manifest JSON.",
    )
    parser.add_argument(
        "--analysis-output",
        default="data/processed/materials_project_v1_3_analysis_ready.csv",
        help="Local-only analysis-ready descriptor CSV.",
    )
    parser.add_argument(
        "--inventory-output",
        default="data/processed/materials_project_v1_3_descriptor_inventory.csv",
        help="Descriptor provenance inventory CSV.",
    )
    parser.add_argument(
        "--redundancy-output",
        default="data/processed/materials_project_v1_3_descriptor_redundancy_summary.csv",
        help="Descriptor redundancy audit CSV.",
    )
    parser.add_argument(
        "--ambiguity-output",
        default="data/processed/materials_project_v1_3_composition_ambiguity_summary.csv",
        help="Composition ambiguity summary CSV.",
    )
    parser.add_argument(
        "--target-output",
        default="data/processed/materials_project_v1_3_target_suitability_summary.csv",
        help="Target suitability summary CSV.",
    )
    parser.add_argument(
        "--split-output",
        default="data/processed/materials_project_v1_3_split_readiness_summary.csv",
        help="Split readiness summary CSV.",
    )
    parser.add_argument(
        "--group-inventory-output",
        default="data/processed/materials_project_v1_3_group_inventory.csv",
        help="Group inventory CSV.",
    )
    return parser.parse_args()


def main() -> None:
    """Run descriptor generation and print a compact JSON summary."""
    args = parse_args()
    result = run_descriptor_pipeline(
        acquired_path=args.input,
        manifest_path=args.manifest,
        analysis_ready_output=args.analysis_output,
        inventory_output=args.inventory_output,
        redundancy_output=args.redundancy_output,
        ambiguity_output=args.ambiguity_output,
        target_output=args.target_output,
        split_output=args.split_output,
        group_inventory_output=args.group_inventory_output,
    )
    print(
        json.dumps(
            {
                "input_rows": result["input_row_count"],
                "output_rows": result["output_row_count"],
                "source_sha_unchanged": result["input_sha256_before"]
                == result["input_sha256_after"],
                "composition_source_priority": result["composition_source_priority"],
                "parse_status_counts": result["parse_status_counts"],
                "descriptor_quality_status_counts": result[
                    "descriptor_quality_status_counts"
                ],
                "primary_feature_count": result["primary_feature_count"],
                "included_elemental_properties": result[
                    "included_elemental_properties"
                ],
                "excluded_elemental_properties": result[
                    "excluded_elemental_properties"
                ],
                "high_correlation_pair_count": result[
                    "high_correlation_pair_count"
                ],
                "duplicate_descriptor_vector_rows": result[
                    "duplicate_descriptor_vector_rows"
                ],
                "ambiguous_formula_group_count": result[
                    "ambiguous_formula_group_count"
                ],
                "composition_diagnostic_mae": result["composition_diagnostic_mae"],
                "composition_diagnostic_rmse": result["composition_diagnostic_rmse"],
                "target_zero_rate": result["target_zero_rate"],
                "target_skew": result["target_skew"],
                "reduced_formula_group_count": result[
                    "reduced_formula_group_count"
                ],
                "chemical_system_group_count": result[
                    "chemical_system_group_count"
                ],
                "overall_modeling_readiness": result[
                    "overall_modeling_readiness"
                ],
                "output_sizes": result["output_sizes"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

