"""Audit and close out a completed Materials Project acquisition suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from materials_data_analyzer.research_loop.materials_project_acquisition_closeout import (  # noqa: E402
    MaterialsProjectAcquisitionCloseoutError,
    audit_materials_project_acquisition_suite,
)
from materials_data_analyzer.research_loop.materials_project_acquisition_closeout_binding import (  # noqa: E402
    MaterialsProjectCloseoutBindingError,
    validate_strategy_comparison_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the frozen Materials Project Stage 4 suite, summarize planner-side "
            "selection behavior, compare the already-exposed locked metrics, and emit a "
            "non-tuning scientific closeout."
        )
    )
    parser.add_argument(
        "--suite-root",
        type=Path,
        default=Path("outputs/materials_project_acquisition_suite_v1"),
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("outputs/materials_project_retrospective_benchmark_v1"),
    )
    parser.add_argument(
        "--benchmark-config",
        type=Path,
        default=Path("configs/research/materials_project_retrospective_benchmark.v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/materials_project_acquisition_closeout_v1"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        binding = validate_strategy_comparison_binding(args.suite_root)
        result = audit_materials_project_acquisition_suite(
            suite_root=args.suite_root,
            benchmark_dir=args.benchmark,
            benchmark_config_path=args.benchmark_config,
            output_dir=args.output,
        )
        result["comparison_binding"] = binding
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ValueError,
        MaterialsProjectAcquisitionCloseoutError,
        MaterialsProjectCloseoutBindingError,
    ) as exc:
        print(f"Materials Project acquisition closeout failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
