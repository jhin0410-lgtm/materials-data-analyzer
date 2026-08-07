"""Run the non-locked Materials Project policy-development replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from materials_data_analyzer.research_loop.materials_project_policy_development_replay import (  # noqa: E402
    MaterialsProjectPolicyReplayError,
    run_materials_project_policy_development_replay,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay frozen Materials Project acquisition policies on non-locked development "
            "partitions only. Benchmark-v1 locked-test content is never read."
        )
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("outputs/materials_project_retrospective_benchmark_v1"),
    )
    parser.add_argument(
        "--benchmark-config",
        type=Path,
        default=Path("configs/research/materials_project_retrospective_benchmark.v1.json"),
    )
    parser.add_argument(
        "--replay-config",
        type=Path,
        default=Path("configs/research/materials_project_policy_development_replay.v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/materials_project_policy_development_replay_v1"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_materials_project_policy_development_replay(
            benchmark_dir=args.benchmark,
            benchmark_config_path=args.benchmark_config,
            replay_config_path=args.replay_config,
            output_dir=args.output,
            overwrite=args.overwrite,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        MaterialsProjectPolicyReplayError,
        ValueError,
    ) as exc:
        print(f"Materials Project policy development replay failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
