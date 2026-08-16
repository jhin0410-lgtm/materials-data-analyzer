#!/usr/bin/env python
"""Verify and execute exactly one mission-authenticated NIST structural action."""
from __future__ import annotations

import argparse
import json

from materials_data_analyzer.research_loop.nist_authenticated_execution import (
    execute_nist_authenticated_action,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--mission", required=True)
    parser.add_argument("--expected-mission-sha256", required=True)
    parser.add_argument("--policy-id", required=True)
    parser.add_argument("--request-delegation-policy", required=True)
    args = parser.parse_args()
    result = execute_nist_authenticated_action(
        repository_root=args.repository_root,
        mission_path=args.mission,
        expected_mission_sha256=args.expected_mission_sha256,
        policy_id=args.policy_id,
        request_delegation_policy_path=args.request_delegation_policy,
        research_run=args.run,
        action_registry_path=args.registry,
        request_path=args.request,
        manifest_path=args.manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
