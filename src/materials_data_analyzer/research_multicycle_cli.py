"""Installed CLI for finite, predeclared-request research sequences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.kernel import ResearchLoopError
from materials_data_analyzer.research_loop.multicycle import run_bounded_multicycle
from materials_data_analyzer.research_loop.planning_adapter import available_planning_adapters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-multicycle",
        description=(
            "Run a finite sequence of checksum-bound, predeclared typed research requests. "
            "Every step delegates to the existing one-action research-cycle authorization and "
            "verification boundary; no request is generated automatically."
        ),
    )
    parser.add_argument("--adapter", required=True, choices=available_planning_adapters())
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument(
        "--run",
        type=Path,
        help="Existing research-loop run directory when required by the selected adapter.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        help="Versioned action registry when required by the selected adapter.",
    )
    parser.add_argument(
        "--request-queue",
        type=Path,
        help=(
            "Finite request-queue JSON. If omitted, the command can inspect the current state "
            "but will stop before any action that requires an explicit request."
        ),
    )
    parser.add_argument(
        "--request-root",
        type=Path,
        help=(
            "Allowed root for request files referenced by the queue. Defaults to the queue "
            "file's parent directory."
        ),
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=8,
        help="Maximum cycles for this invocation; hard-capped by the library policy.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_bounded_multicycle(
            args.adapter,
            repository_root=args.repository_root,
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
        print(f"Bounded multi-cycle research command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
