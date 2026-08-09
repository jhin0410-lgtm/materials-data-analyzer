"""CLI for the frozen TM-Fe-Si MCA-to-MDA descriptive case."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tm_fe_si_cross_repo import build_tm_fe_si_cross_repo_case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--magnetic-source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--requested-use",
        default="descriptive",
        choices=("display", "descriptive", "association", "predictive", "causal", "engineering"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_tm_fe_si_cross_repo_case(
            args.bundle_manifest,
            args.magnetic_source_dir,
            args.output,
            requested_use=args.requested_use,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"TM-Fe-Si cross-repo case failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
