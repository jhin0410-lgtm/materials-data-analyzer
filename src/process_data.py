"""Command line entry point for Materials Data Analyzer."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Callable

try:
    import pandas as pd

    from analyzers.eda import run_eda_analysis
    from analyzers.process import run_process_analysis
    from analyzers.reliability import run_reliability_analysis
    from analyzers.simulation import run_simulation_analysis
    from analyzers.smart_factory import run_smart_factory_analysis
    from analyzers.spc import run_spc_analysis
    from config import ANALYSIS_MODES, DEFAULT_INPUT, OutputPaths
    from io_utils import (
        create_output_dirs,
        display_path,
        load_data,
        resolve_project_path,
        resolve_run_name,
        save_json,
        save_preprocessing_audit,
    )
    from platform_core.version import PLATFORM_VERSION
    from preprocessing import preprocess_data
except ModuleNotFoundError as exc:
    missing_dependency = exc.name or "unknown package"
    print(
        f"Error: Missing Python package: {missing_dependency}\n"
        "Please install the project dependencies with: pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Read command line options entered by the user."""
    parser = argparse.ArgumentParser(
        description="Analyze materials and semiconductor process CSV data."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        required=False,
        help=f"Path to the input CSV file. Default: {DEFAULT_INPUT.as_posix()}",
    )
    parser.add_argument(
        "--target",
        default=None,
        required=False,
        help="Optional target column. Process mode uses yield_percent when omitted.",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        required=False,
        help=(
            "Optional target columns for multi-objective process screening. "
            "Example: --targets yield_percent hardness_hv resistivity_ohm_cm"
        ),
    )
    parser.add_argument(
        "--features",
        nargs="*",
        default=None,
        required=False,
        help=(
            "Numeric feature columns for simulation mode. "
            "Example: --features process_temp_c process_time_min pressure_mpa"
        ),
    )
    parser.add_argument(
        "--scenario-input",
        default=None,
        required=False,
        help=(
            "Optional scenario CSV file for simulation what-if prediction. "
            "Example: --scenario-input data/sample/simulation_scenarios.csv"
        ),
    )
    parser.add_argument(
        "--design-method",
        choices=("random", "grid"),
        default="random",
        required=False,
        help=(
            "Virtual experiment design method for simulation mode when "
            "--scenario-input is omitted. Default: random"
        ),
    )
    parser.add_argument(
        "--design-samples",
        type=int,
        default=100,
        required=False,
        help=(
            "Number of random virtual experiment rows to generate when "
            "--design-method random is used. Default: 100"
        ),
    )
    parser.add_argument(
        "--grid-levels",
        type=int,
        default=5,
        required=False,
        help=(
            "Number of levels per feature for grid virtual experiment design. "
            "Default: 5"
        ),
    )
    parser.add_argument(
        "--group-column",
        default=None,
        required=False,
        help=(
            "Optional group column for group-aware simulation validation. "
            "Example: battery_id"
        ),
    )
    parser.add_argument(
        "--goal",
        choices=("maximize", "minimize"),
        default="maximize",
        required=False,
        help="Optimization direction for process mode. Default: maximize",
    )
    parser.add_argument(
        "--goals",
        nargs="*",
        choices=("maximize", "minimize"),
        default=None,
        required=False,
        help=(
            "Goals for --targets. Use one maximize or minimize value per target. "
            "Example: --goals maximize maximize minimize"
        ),
    )
    parser.add_argument(
        "--lsl",
        type=float,
        default=None,
        required=False,
        help="Optional lower specification limit for SPC capability analysis.",
    )
    parser.add_argument(
        "--usl",
        type=float,
        default=None,
        required=False,
        help="Optional upper specification limit for SPC capability analysis.",
    )
    parser.add_argument(
        "--mode",
        choices=ANALYSIS_MODES,
        default="eda",
        required=False,
        help="Analysis mode to run. Default: eda",
    )
    parser.add_argument(
        "--run-name",
        required=False,
        help=(
            "Optional output folder name. If omitted, the input CSV file name "
            "is used. Example: experiment_process"
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Delete and recreate an existing non-empty output run directory. "
            "Without this flag, existing run artifacts are never overwritten."
        ),
    )
    return parser.parse_args()


def get_analysis_runner() -> dict[str, Callable[..., dict[str, Path]]]:
    """Map each mode name to the function that runs that mode."""
    return {
        "eda": run_eda_analysis,
        "process": run_process_analysis,
        "reliability": run_reliability_analysis,
        "smart_factory": run_smart_factory_analysis,
        "spc": run_spc_analysis,
        "simulation": run_simulation_analysis,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_analysis(
    args: argparse.Namespace,
    *,
    cleaned_df: pd.DataFrame,
    input_path: Path,
    output_paths: OutputPaths,
) -> dict[str, Path]:
    if args.mode == "process":
        return run_process_analysis(
            df=cleaned_df,
            input_path=input_path,
            target=args.target,
            output_paths=output_paths,
            goal=args.goal,
            targets=args.targets,
            goals=args.goals,
        )

    if args.mode == "spc":
        return run_spc_analysis(
            df=cleaned_df,
            input_path=input_path,
            target=args.target,
            output_paths=output_paths,
            lsl=args.lsl,
            usl=args.usl,
        )

    if args.mode == "simulation":
        return run_simulation_analysis(
            df=cleaned_df,
            input_path=input_path,
            target=args.target,
            output_paths=output_paths,
            features=args.features,
            scenario_input=args.scenario_input,
            goal=args.goal,
            design_method=args.design_method,
            design_samples=args.design_samples,
            grid_levels=args.grid_levels,
            group_column=args.group_column,
        )

    analysis_runner = get_analysis_runner()[args.mode]
    return analysis_runner(
        df=cleaned_df,
        input_path=input_path,
        target=args.target,
        output_paths=output_paths,
    )


def _build_run_manifest(
    args: argparse.Namespace,
    *,
    input_path: Path,
    run_name: str,
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    preprocessing_audit_path: Path,
    preprocessing_warning_count: int,
    output_files: dict[str, Path],
) -> dict[str, object]:
    options = {
        key: value
        for key, value in vars(args).items()
        if key not in {"overwrite"}
    }
    return {
        "schema_version": "1.0",
        "platform_version": PLATFORM_VERSION,
        "mode": args.mode,
        "run_name": run_name,
        "input": {
            "path": display_path(input_path),
            "sha256": _sha256_file(input_path),
            "row_count_before_preprocessing": int(len(raw_df)),
            "column_count_before_preprocessing": int(raw_df.shape[1]),
        },
        "preprocessing": {
            "audit_path": display_path(preprocessing_audit_path),
            "warning_count": int(preprocessing_warning_count),
            "row_count_after_preprocessing": int(len(cleaned_df)),
            "column_count_after_preprocessing": int(cleaned_df.shape[1]),
            "column_collision_policy": "fail_on_collision",
        },
        "options": options,
        "overwrite_requested": bool(args.overwrite),
        "outputs": {
            name: display_path(path)
            for name, path in sorted(output_files.items())
        },
    }


def run_selected_analysis(args: argparse.Namespace) -> dict[str, Path]:
    """Load data, record preprocessing, and execute the selected analysis mode."""
    input_path = resolve_project_path(args.input)
    run_name = resolve_run_name(input_path, args.run_name)

    raw_df = load_data(input_path)
    preprocessing_result = preprocess_data(
        raw_df,
        fail_on_column_collision=True,
    )
    cleaned_df = preprocessing_result.dataframe

    output_paths = create_output_dirs(run_name, overwrite=args.overwrite)
    preprocessing_audit_path = save_preprocessing_audit(
        preprocessing_result.audit,
        output_paths,
    )

    output_files = _run_analysis(
        args,
        cleaned_df=cleaned_df,
        input_path=input_path,
        output_paths=output_paths,
    )
    output_files["preprocessing_audit"] = preprocessing_audit_path

    manifest = _build_run_manifest(
        args,
        input_path=input_path,
        run_name=run_name,
        raw_df=raw_df,
        cleaned_df=cleaned_df,
        preprocessing_audit_path=preprocessing_audit_path,
        preprocessing_warning_count=len(preprocessing_result.warnings),
        output_files=output_files,
    )
    manifest_path = save_json(manifest, output_paths.root / "run_manifest.json")
    output_files["run_manifest"] = manifest_path
    return output_files


def main() -> None:
    """Program entry point."""
    args = parse_args()

    try:
        output_files = run_selected_analysis(args)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(
            f"Error: Could not read or write a file.\nDetails: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not output_files:
        return

    print("Analysis completed successfully.")
    if "cleaned_data" in output_files:
        print(f"Cleaned data saved to: {display_path(output_files['cleaned_data'])}")
    if "preprocessing_audit" in output_files:
        print(
            "Preprocessing audit saved to: "
            f"{display_path(output_files['preprocessing_audit'])}"
        )
    if "report" in output_files:
        print(f"Report saved to: {display_path(output_files['report'])}")
    if "run_manifest" in output_files:
        print(f"Run manifest saved to: {display_path(output_files['run_manifest'])}")


if __name__ == "__main__":
    main()
