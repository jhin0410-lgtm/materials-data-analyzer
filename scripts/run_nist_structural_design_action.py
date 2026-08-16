#!/usr/bin/env python
"""Run exactly one verifier-pinned authorized NIST structural-design action."""
from __future__ import annotations

import argparse
import json

from materials_data_analyzer.research_loop.authorized_execution import (
    execute_authorized_action,
)

ADAPTER_ID = "nist-ambench-process-characterization"
ACTION_TYPE = "nist_structural_design_simulation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--expected-request-sha256",
        required=True,
        help="Exact execution-request SHA-256 returned by independent request verification.",
    )
    parser.add_argument(
        "--expected-research-ledger-sha256",
        required=True,
        help="Pre-execution research-ledger SHA-256 returned by independent request verification.",
    )
    args = parser.parse_args()
    result = execute_authorized_action(
        ADAPTER_ID,
        repository_root=args.repository_root,
        research_run=args.run,
        action_registry_path=args.registry,
        request_path=args.request,
        expected_action_type=ACTION_TYPE,
        expected_request_sha256=args.expected_request_sha256,
        expected_research_ledger_sha256=args.expected_research_ledger_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
