"""CLI for response-free structural experiment-design simulation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.design_simulation import (
    DesignSimulationError,
    simulate_design_structure_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-design-sim",
        description=(
            "Compare the design-matrix rank and residual degrees of freedom before and after "
            "a proposed two-factor experiment. No response values are consumed or generated."
        ),
    )
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. The result is always printed to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = simulate_design_structure_file(args.spec)
        if args.output is not None:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        OSError,
        DesignSimulationError,
        TypeError,
        KeyError,
        ValueError,
    ) as exc:
        print(f"Structural design simulation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
