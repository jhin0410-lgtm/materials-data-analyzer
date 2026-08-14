"""Installed CLI for mission-level autonomous research planning contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop import (
    ResearchLoopError,
    build_research_program,
    validate_reasoning_proposal_file,
)


def _add_program_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mission",
        required=True,
        type=Path,
        help="Versioned research-mission JSON file.",
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        type=Path,
        help="Repository checkout root containing tracked planning evidence.",
    )
    parser.add_argument(
        "--context",
        type=Path,
        help=(
            "Optional runtime-context JSON. Required only for workstreams such as NASA "
            "that depend on an existing research run and action registry."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-program",
        description=(
            "Build a provenance-aware mission-level research agenda from verified domain "
            "planning states and validate evidence-bound scientific reasoning proposals. "
            "This command does not execute actions, access the network, or run physical experiments."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser(
        "show",
        help=(
            "Generate bounded research goals across enabled workstreams and select the next "
            "mission-level planning step."
        ),
    )
    _add_program_arguments(show)

    validate = subparsers.add_parser(
        "validate-proposal",
        help=(
            "Validate a scientific reasoning proposal against the current mission goals and "
            "checksum-bound evidence. Validation is planning-only and grants no execution authority."
        ),
    )
    _add_program_arguments(validate)
    validate.add_argument("--proposal", required=True, type=Path)
    return parser


def _build_program(args: argparse.Namespace) -> dict[str, object]:
    return build_research_program(
        args.mission,
        repository_root=args.repository_root,
        runtime_context_path=args.context,
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    program = _build_program(args)
    if args.command == "show":
        return program
    if args.command == "validate-proposal":
        return validate_reasoning_proposal_file(args.proposal, program)
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run(args)
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ResearchLoopError,
        TypeError,
        KeyError,
        ValueError,
    ) as exc:
        print(f"Research program command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
