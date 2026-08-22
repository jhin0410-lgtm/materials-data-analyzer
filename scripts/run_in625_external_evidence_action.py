#!/usr/bin/env python
"""Execute one independently pinned IN625 external-evidence registration action."""
from __future__ import annotations

import argparse
import json

from materials_data_analyzer.research_loop.authorized_execution import execute_authorized_action
from materials_data_analyzer.research_loop.in625_execution_verifier import (
    verify_in625_execution_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    verified = verify_in625_execution_handoff(
        repository_root=args.repository_root,
        research_run=args.run,
        action_registry_path=args.registry,
        request_path=args.request,
    )
    result = execute_authorized_action(
        "in625-external-evidence",
        repository_root=args.repository_root,
        research_run=args.run,
        action_registry_path=args.registry,
        request_path=args.request,
        expected_action_type=verified["action_type"],
        expected_request_sha256=verified["request_sha256"],
        expected_research_ledger_sha256=verified["research_ledger_sha256"],
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
