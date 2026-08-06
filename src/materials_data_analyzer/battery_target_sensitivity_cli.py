"""Installed command for predeclared Battery target-reference sensitivity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from platform_core.battery_intelligence import (
    build_target_reference_sensitivity,
    load_target_reference_inputs,
    target_reference_markdown,
)
from platform_core.output_safety import transactional_output_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-battery-target-sensitivity",
        description=(
            "Re-express fixed Battery validation predictions under predeclared "
            "rated-retention and absolute-capacity target views without refitting."
        ),
    )
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def run_target_sensitivity(
    run_directory: str | Path,
    output_directory: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    run_path = Path(run_directory).expanduser().resolve(strict=True)
    if not run_path.is_dir():
        raise NotADirectoryError(f"Battery run is not a directory: {run_path}")
    cycle, predictions, group_column = load_target_reference_inputs(run_path)
    result = build_target_reference_sensitivity(
        cycle_summary=cycle,
        predictions=predictions,
        group_column=group_column,
    )
    output_path = Path(output_directory).expanduser().resolve(strict=False)
    with transactional_output_directory(
        output_path,
        overwrite=overwrite,
        protected_paths=(run_path,),
        recognized_markers=("summary.json",),
    ) as staging:
        result["model_comparison"].to_csv(
            staging / "model_comparison_by_target.csv", index=False
        )
        result["per_battery_comparison"].to_csv(
            staging / "per_battery_comparison.csv", index=False
        )
        result["bound_predictions"].to_csv(
            staging / "bound_validation_predictions.csv", index=False
        )
        (staging / "summary.json").write_text(
            json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (staging / "report.md").write_text(
            target_reference_markdown(result["summary"]),
            encoding="utf-8",
        )
    return {
        "outcome": result["summary"]["outcome"],
        "output_directory": str(output_path),
        "summary": str(output_path / "summary.json"),
        "model_comparison": str(output_path / "model_comparison_by_target.csv"),
        "per_battery_comparison": str(output_path / "per_battery_comparison.csv"),
        "bound_predictions": str(output_path / "bound_validation_predictions.csv"),
        "report": str(output_path / "report.md"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_target_sensitivity(
            args.run,
            args.output,
            overwrite=args.overwrite,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Battery target-reference sensitivity failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
