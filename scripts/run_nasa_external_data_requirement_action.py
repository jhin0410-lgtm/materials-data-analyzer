"""Execute or verify the NASA external-data requirement action."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from materials_data_analyzer.research_loop.authorized_execution import (
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.nasa_external_data_requirement_action import (
    verify_nasa_external_data_requirement_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the checksum-bound NASA external-data requirement action."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute = subparsers.add_parser(
        "execute",
        help="Execute an explicitly authorized external-data requirement request.",
    )
    execute.add_argument("--repository-root", required=True)
    execute.add_argument("--run", required=True)
    execute.add_argument("--registry", required=True)
    execute.add_argument("--request", required=True)

    verify = subparsers.add_parser("verify", help="Verify an action report.")
    verify.add_argument("--report", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result: dict[str, Any]
    if args.command == "execute":
        result = execute_authorized_action(
            "nasa-battery",
            repository_root=args.repository_root,
            research_run=args.run,
            action_registry_path=args.registry,
            request_path=args.request,
        )
    else:
        result = verify_nasa_external_data_requirement_report(args.report)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
