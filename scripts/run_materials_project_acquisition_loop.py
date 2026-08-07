"""Run and evaluate Materials Project Stage 4 costed acquisition sequences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from materials_data_analyzer.research_loop.materials_project_acquisition_loop import (  # noqa: E402
    MaterialsProjectAcquisitionError,
    compare_materials_project_acquisition_evaluations,
    evaluate_materials_project_acquisition_sequence,
    run_materials_project_acquisition_sequence,
)


DEFAULT_BENCHMARK = Path("outputs/materials_project_retrospective_benchmark_v1")
DEFAULT_INSTANCE = Path("configs/research/materials_project_retrospective_instance.v1.json")
DEFAULT_BENCHMARK_CONFIG = Path(
    "configs/research/materials_project_retrospective_benchmark.v1.json"
)
DEFAULT_ACQUISITION_CONFIG = Path(
    "configs/research/materials_project_acquisition_loop.v1.json"
)


def _common_contract_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--benchmark-config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--acquisition-config", type=Path, default=DEFAULT_ACQUISITION_CONFIG)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run cost-bounded Materials Project evidence acquisition without exposing "
            "the locked test, then evaluate only after sequence completion."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one planner-side acquisition sequence.")
    _common_contract_args(run)
    run.add_argument(
        "--strategy",
        required=True,
        choices=["fixed_catalog", "random", "diversity", "uncertainty"],
    )
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--overwrite", action="store_true")

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate one completed sequence against the locked test.",
    )
    _common_contract_args(evaluate)
    evaluate.add_argument("--sequence", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--overwrite", action="store_true")

    compare = subparsers.add_parser(
        "compare",
        help="Compare completed locked evaluation manifests without re-reading test rows.",
    )
    compare.add_argument(
        "--evaluation",
        type=Path,
        action="append",
        required=True,
        help="Evaluation directory; repeat once per strategy.",
    )
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            result = run_materials_project_acquisition_sequence(
                benchmark_dir=args.benchmark,
                instance_path=args.instance,
                benchmark_config_path=args.benchmark_config,
                acquisition_config_path=args.acquisition_config,
                strategy=args.strategy,
                output_dir=args.output,
                overwrite=args.overwrite,
            )
        elif args.command == "evaluate":
            result = evaluate_materials_project_acquisition_sequence(
                benchmark_dir=args.benchmark,
                instance_path=args.instance,
                benchmark_config_path=args.benchmark_config,
                acquisition_config_path=args.acquisition_config,
                sequence_dir=args.sequence,
                output_dir=args.output,
                overwrite=args.overwrite,
            )
        else:
            result = compare_materials_project_acquisition_evaluations(
                evaluation_dirs=args.evaluation,
                output_path=args.output,
            )
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        MaterialsProjectAcquisitionError,
        ValueError,
    ) as exc:
        print(f"Materials Project acquisition loop failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
