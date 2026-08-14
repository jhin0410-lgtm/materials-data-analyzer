"""Installed CLI for epistemic-graph-gated finite research sequences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.epistemic_multicycle import (
    run_epistemically_bounded_multicycle,
)
from materials_data_analyzer.research_loop.kernel import ResearchLoopError
from materials_data_analyzer.research_loop.planning_adapter import available_planning_adapters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-epistemic-multicycle",
        description=(
            "Run a finite sequence of checksum-bound predeclared research requests while "
            "revalidating selected epistemic-graph targets before every possible execution."
        ),
    )
    parser.add_argument("--adapter", required=True, choices=available_planning_adapters())
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--mission", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--epistemic-workstream", required=True)
    parser.add_argument(
        "--epistemic-target",
        required=True,
        action="append",
        dest="epistemic_targets",
        help="Target hypothesis/claim/conclusion node ID. Repeat for multiple targets.",
    )
    parser.add_argument(
        "--context",
        type=Path,
        help="Optional mission runtime-context JSON for workstreams such as NASA.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Root for graph verifier/result artifact paths. Defaults to repository root.",
    )
    parser.add_argument("--run", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--request-queue", type=Path)
    parser.add_argument("--request-root", type=Path)
    parser.add_argument("--max-cycles", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_epistemically_bounded_multicycle(
            args.adapter,
            repository_root=args.repository_root,
            mission_path=args.mission,
            graph_path=args.graph,
            epistemic_workstream_id=args.epistemic_workstream,
            epistemic_target_node_ids=args.epistemic_targets,
            runtime_context_path=args.context,
            artifact_root=args.artifact_root,
            research_run=args.run,
            action_registry_path=args.registry,
            request_queue_path=args.request_queue,
            request_root=args.request_root,
            max_cycles=args.max_cycles,
        )
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
        print(f"Epistemic multi-cycle research command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
