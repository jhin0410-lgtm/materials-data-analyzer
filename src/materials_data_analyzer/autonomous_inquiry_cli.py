"""CLI for bounded self-directed research inquiry planning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.autonomous_inquiry import (
    AutonomousInquiryError,
    build_autonomous_inquiry_plan,
)
from materials_data_analyzer.research_loop.kernel import ResearchLoopError
from materials_data_analyzer.research_loop.research_program import build_research_program


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AutonomousInquiryError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousInquiryError(f"could not load JSON object: {resolved}") from exc
    if not isinstance(value, dict):
        raise AutonomousInquiryError(f"JSON root must be an object: {resolved}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m materials_data_analyzer.autonomous_inquiry_cli",
        description=(
            "Derive bounded research objectives, methodological rival hypotheses, evidence gaps, "
            "and ranked analysis/simulation/experiment-design actions from a verified research "
            "program. Planning never grants execution, network, physical-experiment, or scientific "
            "truth authority."
        ),
    )
    parser.add_argument("--mission", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument(
        "--critic-report",
        type=Path,
        help="Optional previously generated deterministic scientific-critic report JSON.",
    )
    parser.add_argument(
        "--validated-reasoning-proposal",
        type=Path,
        help=(
            "Optional proposal JSON that has already passed validate-proposal and contains "
            "proposal_status=validated_for_planning_only."
        ),
    )
    parser.add_argument("--budget-units", type=float, default=8.0)
    parser.add_argument("--minimum-utility", type=float, default=0.01)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional new JSON output path. Existing files are never overwritten.",
    )
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    program = build_research_program(
        args.mission,
        repository_root=args.repository_root,
        runtime_context_path=args.context,
    )
    critic = _load_json_object(args.critic_report) if args.critic_report else None
    proposal = (
        _load_json_object(args.validated_reasoning_proposal)
        if args.validated_reasoning_proposal
        else None
    )
    return build_autonomous_inquiry_plan(
        program,
        critic_report=critic,
        validated_reasoning_proposal=proposal,
        budget_units=args.budget_units,
        minimum_utility=args.minimum_utility,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run(args)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            output = args.output.expanduser().resolve()
            if output.exists():
                raise AutonomousInquiryError(f"output already exists: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 0
    except (AutonomousInquiryError, ResearchLoopError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
