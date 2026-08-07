"""Build or verify the Materials Project Stage 4 retrospective benchmark boundary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from materials_data_analyzer.research_loop.materials_project_retrospective_benchmark import (  # noqa: E402
    MaterialsProjectBenchmarkError,
    build_materials_project_retrospective_benchmark,
    verify_materials_project_retrospective_benchmark,
)


def _common_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        default="data/processed/materials_project_v1_3_analysis_ready.csv",
        type=Path,
        help="Local-only v1.3 analysis-ready Materials Project CSV.",
    )
    parser.add_argument(
        "--inventory",
        default="data/processed/materials_project_v1_3_descriptor_inventory.csv",
        type=Path,
        help="Tracked descriptor inventory used to resolve primary features.",
    )
    parser.add_argument(
        "--config",
        default="configs/research/materials_project_retrospective_benchmark.v1.json",
        type=Path,
        help="Versioned Stage 4 benchmark partition contract.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lock or verify the target-blind Materials Project Stage 4 benchmark. "
            "This command does not train a model or run a research planner."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Create planner/oracle/locked partitions.")
    _common_inputs(build)
    build.add_argument(
        "--output",
        default="outputs/materials_project_retrospective_benchmark_v1",
        type=Path,
    )
    build.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only a previously recognized benchmark output directory.",
    )

    verify = subparsers.add_parser(
        "verify", help="Independently recompute and verify an existing benchmark."
    )
    _common_inputs(verify)
    verify.add_argument(
        "--benchmark",
        default="outputs/materials_project_retrospective_benchmark_v1",
        type=Path,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_materials_project_retrospective_benchmark(
                input_path=args.input,
                inventory_path=args.inventory,
                config_path=args.config,
                output_dir=args.output,
                overwrite=args.overwrite,
            )
        else:
            result = verify_materials_project_retrospective_benchmark(
                benchmark_dir=args.benchmark,
                input_path=args.input,
                inventory_path=args.inventory,
                config_path=args.config,
            )
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        MaterialsProjectBenchmarkError,
        ValueError,
    ) as exc:
        print(f"Materials Project retrospective benchmark failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
