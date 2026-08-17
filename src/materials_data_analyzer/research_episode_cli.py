"""CLI for creating, inspecting, and appending checksum-bound research episodes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .research_loop.research_episode import (
    checkpoint_episode,
    create_research_episode,
    record_episode_iteration,
    resume_episode,
)


def _json_file(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mda-research-episode")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a new persistent research episode")
    init.add_argument("--episode", required=True)
    init.add_argument("--episode-id", required=True)
    init.add_argument("--question", required=True)
    init.add_argument("--mission-id", required=True)
    init.add_argument("--objective", action="append", required=True)
    init.add_argument("--max-iterations", type=int, default=20)
    init.add_argument("--cost-budget", type=float, default=100.0)

    show = sub.add_parser("show", help="Verify and display one episode checkpoint")
    show.add_argument("--episode", required=True)

    record = sub.add_parser("record", help="Append one exact planner iteration reference")
    record.add_argument("--episode", required=True)
    record.add_argument("--planner-record", required=True)
    record.add_argument("--artifact-ref", action="append", default=[])
    record.add_argument("--evidence-ref", action="append", default=[])
    record.add_argument("--gap", action="append")
    record.add_argument("--review", action="append")
    record.add_argument("--blocker", action="append")
    record.add_argument("--cost-units", type=float, default=0.0)
    record.add_argument("--iteration-status", default="completed")
    record.add_argument("--episode-status", choices=["active", "blocked", "concluded", "stopped"])
    record.add_argument("--conclusion")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.episode)
    if args.command == "init":
        state = create_research_episode(
            episode_id=args.episode_id,
            research_question=args.question,
            mission_id=args.mission_id,
            objectives=args.objective,
            max_iterations=args.max_iterations,
            cost_budget=args.cost_budget,
        )
        envelope = checkpoint_episode(path, state)
        print(json.dumps(envelope, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "show":
        print(json.dumps(resume_episode(path), indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    state = resume_episode(path)
    conclusion = _json_file(args.conclusion) if args.conclusion else None
    if conclusion is not None and not isinstance(conclusion, dict):
        raise ValueError("--conclusion JSON root must be an object")
    next_state = record_episode_iteration(
        state,
        planner_record=_json_file(args.planner_record),
        artifact_refs=args.artifact_ref,
        evidence_refs=args.evidence_ref,
        unresolved_gaps=args.gap,
        review_queue=args.review,
        blockers=args.blocker,
        cost_units=args.cost_units,
        status=args.iteration_status,
        episode_status=args.episode_status,
        conclusion=conclusion,
    )
    envelope = checkpoint_episode(path, next_state)
    print(json.dumps(envelope, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
