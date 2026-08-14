"""Installed CLI for mission-level autonomous research planning contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop import (
    ResearchLoopError,
    build_research_program,
    validate_reasoning_proposal_file,
)
from materials_data_analyzer.research_loop.epistemic_graph import evaluate_epistemic_graph


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchLoopError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path) -> tuple[dict[str, Any], Path, str]:
    resolved = path.expanduser().resolve(strict=True)
    with resolved.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    if not isinstance(value, dict):
        raise ResearchLoopError(f"JSON root must be an object: {resolved}")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return value, resolved, digest


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
            "Build a provenance-aware mission-level research agenda, validate evidence-bound "
            "scientific reasoning proposals, and evaluate checksum-bound epistemic graphs. "
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

    graph = subparsers.add_parser(
        "evaluate-graph",
        help=(
            "Validate and evaluate an epistemic graph. Only domain-verified relations with "
            "checksum-bound verifier artifacts may affect verified status, and positive support "
            "remains provisional."
        ),
    )
    _add_program_arguments(graph)
    graph.add_argument("--graph", required=True, type=Path)
    graph.add_argument(
        "--artifact-root",
        type=Path,
        help=(
            "Root for relative verifier/result artifact paths. Defaults to --repository-root."
        ),
    )
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
    if args.command == "evaluate-graph":
        graph, graph_path, graph_sha256 = _load_json_object(args.graph)
        artifact_root = args.artifact_root or args.repository_root
        result = evaluate_epistemic_graph(
            graph,
            program_state=program,
            artifact_root=artifact_root,
        )
        return {
            **result,
            "graph_binding": {
                "path": str(graph_path),
                "sha256": graph_sha256,
            },
        }
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
