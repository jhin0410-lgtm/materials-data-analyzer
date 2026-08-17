"""Export a verified ResearchEpisode checkpoint to a read-only HTML operations view."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .research_loop.research_episode import resume_episode
from .research_loop.research_operations_ui import render_research_episode_html


def _json_array(path: str | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("--evidence-records must be a JSON array of objects")
    return value


def _json_object(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("--benchmark-summary must be a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mda-research-operations")
    parser.add_argument("--episode", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-records")
    parser.add_argument("--benchmark-summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    episode = resume_episode(Path(args.episode))
    rendered = render_research_episode_html(
        episode,
        evidence_records=_json_array(args.evidence_records),
        benchmark_summary=_json_object(args.benchmark_summary),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "episode_id": episode["episode_id"],
                "status": episode["status"],
                "read_only": True,
                "scientific_status_changed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
