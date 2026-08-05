"""Installed command for the deterministic autonomous-research state kernel."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop import (
    ResearchLoopError,
    append_action,
    append_evidence,
    append_hypothesis,
    append_stop,
    initialize_research_loop,
    load_research_state,
    verify_research_loop,
)


def _add_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Existing research-loop run directory.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-loop",
        description=(
            "Create and verify append-only research state for bounded autonomous "
            "materials research. This command records objectives, hypotheses, evidence, "
            "actions, budgets, and stop decisions; it does not yet plan or execute models."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Initialize a new research run from a versioned objective JSON."
    )
    init_parser.add_argument("--objective", required=True, type=Path)
    init_parser.add_argument("--output", required=True, type=Path)

    hypothesis_parser = subparsers.add_parser(
        "add-hypothesis", help="Append a proposed hypothesis to the immutable ledger."
    )
    _add_run_argument(hypothesis_parser)
    hypothesis_parser.add_argument("--hypothesis-id", required=True)
    hypothesis_parser.add_argument("--statement", required=True)
    hypothesis_parser.add_argument("--rationale", required=True)

    evidence_parser = subparsers.add_parser(
        "add-evidence", help="Append checksum-bound file evidence to the immutable ledger."
    )
    _add_run_argument(evidence_parser)
    evidence_parser.add_argument("--evidence-id", required=True)
    evidence_parser.add_argument("--evidence-type", required=True)
    evidence_parser.add_argument("--source", required=True, type=Path)
    evidence_parser.add_argument("--summary", required=True)

    action_parser = subparsers.add_parser(
        "record-action", help="Record one completed, failed, or rejected research action."
    )
    _add_run_argument(action_parser)
    action_parser.add_argument("--action-id", required=True)
    action_parser.add_argument("--action-type", required=True)
    action_parser.add_argument(
        "--status", required=True, choices=("completed", "failed", "rejected")
    )
    action_parser.add_argument("--summary", required=True)
    action_parser.add_argument("--cost-units", required=True, type=int)
    action_parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=Path,
        help="Optional output artifact file; repeat for multiple files.",
    )

    stop_parser = subparsers.add_parser(
        "stop", help="Append a terminal stop decision to the immutable ledger."
    )
    _add_run_argument(stop_parser)
    stop_parser.add_argument("--reason-code", required=True)
    stop_parser.add_argument("--summary", required=True)

    show_parser = subparsers.add_parser(
        "show", help="Print verified state reconstructed from the immutable ledger."
    )
    _add_run_argument(show_parser)

    verify_parser = subparsers.add_parser(
        "verify", help="Verify objective binding, hash chaining, and state reconstruction."
    )
    _add_run_argument(verify_parser)
    return parser


def _run_command(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "init":
        return initialize_research_loop(args.objective, args.output)
    if args.command == "add-hypothesis":
        return append_hypothesis(
            args.run,
            hypothesis_id=args.hypothesis_id,
            statement=args.statement,
            rationale=args.rationale,
        )
    if args.command == "add-evidence":
        return append_evidence(
            args.run,
            evidence_id=args.evidence_id,
            evidence_type=args.evidence_type,
            source_path=args.source,
            summary=args.summary,
        )
    if args.command == "record-action":
        return append_action(
            args.run,
            action_id=args.action_id,
            action_type=args.action_type,
            status=args.status,
            summary=args.summary,
            cost_units=args.cost_units,
            artifact_paths=args.artifact,
        )
    if args.command == "stop":
        return append_stop(
            args.run,
            reason_code=args.reason_code,
            summary=args.summary,
        )
    if args.command == "show":
        return load_research_state(args.run)
    if args.command == "verify":
        return verify_research_loop(args.run)
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run_command(args)
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ResearchLoopError,
        TypeError,
        KeyError,
    ) as exc:
        print(f"Research loop command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
