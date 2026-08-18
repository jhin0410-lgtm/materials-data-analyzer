"""Evaluate the three canonical live real-data research episodes for Issue #165."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.live_real_data_mvp import (
    LiveRealDataMvpError,
    build_live_real_data_mvp_suite,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nasa-raw", type=Path, required=True)
    parser.add_argument("--nasa-import", type=Path, required=True)
    parser.add_argument("--nasa-analysis", type=Path, required=True)
    parser.add_argument("--dwcnt-producer-result", type=Path, required=True)
    parser.add_argument("--dwcnt-consumer-output", type=Path, required=True)
    parser.add_argument("--rwgs-producer-result", type=Path, required=True)
    parser.add_argument("--rwgs-producer-validation", type=Path, required=True)
    parser.add_argument("--rwgs-consumer-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_live_real_data_mvp_suite(
            nasa_raw_directory=args.nasa_raw,
            nasa_import_output=args.nasa_import,
            nasa_analysis_output=args.nasa_analysis,
            dwcnt_producer_result=args.dwcnt_producer_result,
            dwcnt_consumer_output=args.dwcnt_consumer_output,
            rwgs_producer_result=args.rwgs_producer_result,
            rwgs_producer_validation=args.rwgs_producer_validation,
            rwgs_consumer_output=args.rwgs_consumer_output,
        )
    except (LiveRealDataMvpError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"live real-data MVP acceptance failed closed: {exc}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    for report in result["episode_reports"]:
        episode_id = str(report["episode_id"])
        (args.output / f"{episode_id}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    output_path = args.output / "live_real_data_mvp_acceptance.json"
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["suite_acceptance"], indent=2, ensure_ascii=False, sort_keys=True))
    print(f"acceptance_result: {output_path}")
    return 0 if result["suite_acceptance"]["mvp_acceptance_passed"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
