"""Run controlled Materials Project v1.3 acquisition.

The API key is read only from MP_API_KEY by the connector module.  This script
does not accept API keys through command-line arguments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.materials_project_acquisition import (  # noqa: E402
    AcquisitionOutputs,
    AcquisitionStopError,
    CredentialRequiredError,
    load_acquisition_spec,
    print_sanitized_json,
    run_full_acquisition,
    run_preflight,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Controlled Materials Project v1.3 live acquisition."
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="Path to data/case_studies/materials_project/acquisition_spec_v1_3.json.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run one small preflight request and do not save the full dataset.",
    )
    parser.add_argument(
        "--raw-output",
        help="Full acquisition raw JSONL output path.",
    )
    parser.add_argument(
        "--table-output",
        help="Full acquisition deterministic CSV output path.",
    )
    parser.add_argument(
        "--manifest-output",
        help="Full acquisition compact manifest JSON output path.",
    )
    parser.add_argument(
        "--summary-output",
        help="Full acquisition compact summary CSV output path.",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=1,
        help="Bounded retry count for full acquisition API errors.",
    )
    return parser.parse_args()


def main() -> None:
    """Run preflight or full acquisition."""
    args = parse_args()
    try:
        spec = load_acquisition_spec(args.spec)
        if args.preflight:
            report = run_preflight(spec, spec_path=args.spec)
            print_sanitized_json(
                {
                    "status": report["preflight_status"],
                    "sample_row_count": report["sample_row_count"],
                    "mandatory_field_check": report["mandatory_field_check"],
                    "required_element_check": report["required_element_check"],
                    "element_count_check": report["element_count_check"],
                    "target_field_check": report["target_field_check"],
                    "database_version_available": report["database_version_available"],
                    "network_called": report["network_called"],
                    "credential_included": report["credential_included"],
                    "absolute_path_included": report["absolute_path_included"],
                    "exact_query_parameters": report["exact_query_parameters"],
                    "stop_reasons": report["stop_reasons"],
                }
            )
            if report["preflight_status"] != "passed":
                sys.exit(1)
            return

        missing_outputs = [
            name
            for name in [
                "raw_output",
                "table_output",
                "manifest_output",
                "summary_output",
            ]
            if getattr(args, name) is None
        ]
        if missing_outputs:
            raise ValueError(
                "Full acquisition requires output argument(s): "
                + ", ".join("--" + name.replace("_", "-") for name in missing_outputs)
            )

        result = run_full_acquisition(
            spec,
            spec_path=args.spec,
            outputs=AcquisitionOutputs(
                raw_output=Path(args.raw_output),
                table_output=Path(args.table_output),
                manifest_output=Path(args.manifest_output),
                summary_output=Path(args.summary_output),
            ),
            retry_count=args.retry_count,
        )
        print_sanitized_json(
            {
                "status": result["execution_status"],
                "preflight_status": result["preflight_status"],
                "row_count": result["table_row_count"],
                "column_count": result["column_count"],
                "raw_sha256": result["raw_sha256"],
                "sorted_table_sha256": result["sorted_table_sha256"],
                "data_sufficiency_gate": result["data_sufficiency_gate"],
                "stop_reasons": result["stop_reasons"],
            }
        )
        if result["execution_status"] != "success":
            sys.exit(1)
    except CredentialRequiredError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    except (AcquisitionStopError, ValueError, FileNotFoundError) as exc:
        print(f"Materials Project v1.3 acquisition stopped: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

