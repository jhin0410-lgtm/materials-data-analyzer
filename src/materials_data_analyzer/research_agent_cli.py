"""Preferred CLI facade for one bounded self-directed research-agent iteration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.autonomous_inquiry import AutonomousInquiryError
from materials_data_analyzer.research_loop.kernel import ResearchLoopError
from materials_data_analyzer.research_loop.research_agent import build_research_agent_iteration
from materials_data_analyzer.research_loop.research_program import build_research_program


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AutonomousInquiryError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
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
        prog="python -m materials_data_analyzer.research_agent_cli",
        description=(
            "Build one critic-aware self-directed research iteration from the current mission, "
            "verified program state, optional hardened scientific-critic report, and optional "
            "validated domain reasoning proposal. No action is executed by this command."
        ),
    )
    parser.add_argument("--mission", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--scientific-critic-report", type=Path)
    parser.add_argument("--validated-reasoning-proposal", type=Path)
    parser.add_argument("--previous-plan", type=Path)
    parser.add_argument("--budget-units", type=float, default=8.0)
    parser.add_argument("--minimum-utility", type=float, default=0.01)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    program = build_research_program(
        args.mission,
        repository_root=args.repository_root,
        runtime_context_path=args.context,
    )
    return build_research_agent_iteration(
        program,
        scientific_critic_report=(
            _load_json(args.scientific_critic_report)
            if args.scientific_critic_report
            else None
        ),
        validated_reasoning_proposal=(
            _load_json(args.validated_reasoning_proposal)
            if args.validated_reasoning_proposal
            else None
        ),
        previous_plan=_load_json(args.previous_plan) if args.previous_plan else None,
        budget_units=args.budget_units,
        minimum_utility=args.minimum_utility,
        max_iterations=args.max_iterations,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run(args)
        output = args.output.expanduser().resolve()
        if output.exists():
            raise AutonomousInquiryError(f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 0
    except (AutonomousInquiryError, ResearchLoopError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
