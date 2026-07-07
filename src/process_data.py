"""Command line entry point for Materials Data Analyzer."""

from __future__ import annotations

import argparse
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
    from config import ANALYSIS_MODES, DEFAULT_INPUT, OUTPUT_DIR, OutputPaths
    from io_utils import (
        create_output_dirs,
        display_path,
        load_data,
        resolve_project_path,
        resolve_run_name,
    )
    from preprocessing import clean_data, standardize_column_names
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


def run_selected_analysis(args: argparse.Namespace) -> dict[str, Path]:
    """Load data, run common cleanup, then execute the selected analysis mode."""
    input_path = resolve_project_path(args.input)

    run_name = resolve_run_name(input_path, args.run_name)
    output_paths = create_output_dirs(run_name)

    raw_df = load_data(input_path)
    standardized_df = standardize_column_names(raw_df)
    cleaned_df = clean_data(standardized_df)

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


def main() -> None:
    """Program entry point."""
    args = parse_args()

    try:
        output_files = run_selected_analysis(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
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
    if "report" in output_files:
        print(f"Report saved to: {display_path(output_files['report'])}")


if __name__ == "__main__":
    main()
