from __future__ import annotations

import argparse
import json
from pathlib import Path

from materials_data_analyzer.research_loop.ssrm_titanium_zenodo_episode import (
    run_ssrm_titanium_zenodo_episode,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/research/ssrm_titanium_zenodo_episode.v1.json",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("config JSON root must be an object")
    summary = run_ssrm_titanium_zenodo_episode(
        config=config,
        output_dir=args.output,
        overwrite=args.overwrite,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
