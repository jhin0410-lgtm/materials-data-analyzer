"""Installed CLI for policy-bounded automatic public research-data acquisition."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.frontier_acquisition import (
    FrontierAcquisitionError,
    acquire_frontier_candidate,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    PublicAcquisitionError,
)

_MIB = 1024 * 1024


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-public-acquisition",
        description=(
            "Execute a machine-actionable research-frontier acquisition plan. "
            "Public checksum-bound files run automatically; exceptional access "
            "conditions are returned for human review rather than bypassed."
        ),
    )
    parser.add_argument(
        "--frontier",
        required=True,
        type=Path,
        help="Versioned research-frontier JSON containing automatic_acquisition_plan.",
    )
    parser.add_argument(
        "--candidate-id",
        required=True,
        help="Scientific frontier candidate selected by the research planner.",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
        help="Output root for checksum-bound acquisition packages.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only previously recognized acquisition-package directories.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Per-request network timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--max-auto-mib",
        type=_positive_int,
        default=DEFAULT_MAX_AUTO_ARTIFACT_BYTES // _MIB,
        help="Maximum size of one automatically acquired artifact in MiB.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout_seconds <= 0:
        print("error: --timeout-seconds must be positive", file=sys.stderr)
        return 2
    try:
        report = acquire_frontier_candidate(
            frontier_path=args.frontier,
            candidate_id=args.candidate_id,
            output_root=args.output_root,
            overwrite=args.overwrite,
            timeout_seconds=args.timeout_seconds,
            max_auto_bytes=args.max_auto_mib * _MIB,
        )
    except (FrontierAcquisitionError, PublicAcquisitionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    acquisition = report["acquisition"]
    if acquisition["automatic_execution_failed"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
