"""Installed command for deterministic autonomous-research contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop import (
    ResearchLoopError,
    action_summaries,
    append_action,
    append_evidence,
    append_hypothesis,
    append_stop,
    assess_current_action_authorization,
    available_planning_adapters,
    build_current_research_transition,
    build_reopen_evidence_review,
    build_research_planning_state,
    describe_action,
    execute_nasa_audit_action,
    execute_nasa_protocol_stratification_action,
    execute_nasa_target_reference_action,
    initialize_research_loop,
    load_action_registry,
    load_research_state,
    plan_nasa_next_action,
    plan_research_next_action,
    verify_nasa_audit_action_report,
    verify_nasa_protocol_stratification_report,
    verify_nasa_target_reference_report,
    verify_research_loop,
)


def _add_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Existing research-loop run directory.",
    )


def _add_registry_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--registry",
        required=True,
        type=Path,
        help="Versioned action-registry JSON file.",
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        type=Path,
        help=(
            "Repository checkout root used to verify installed-command declarations "
            "and source-script paths."
        ),
    )


def _add_generic_planning_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--adapter",
        required=True,
        choices=available_planning_adapters(),
        help="Domain adapter whose existing scientific policy should be revalidated.",
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        type=Path,
        help="Repository checkout root containing tracked planning evidence.",
    )
    parser.add_argument(
        "--run",
        type=Path,
        help="NASA only: existing research-loop run directory.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        help="NASA only: versioned action-registry JSON file.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-loop",
        description=(
            "Create and verify append-only research state, bounded action registries, "
            "typed deterministic actions, and deterministic planning baselines. "
            "No unrestricted code generation is enabled."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Initialize a new research run from a versioned objective JSON."
    )
    init_parser.add_argument("--objective", required=True, type=Path)
    init_parser.add_argument("--output", required=True, type=Path)

    hypothesis_parser = subparsers.add_parser(
        "add-hypothesis", help="Append a proposed hypothesis to the immutable ledger."
    )
    _add_run_argument(hypothesis_parser)
    hypothesis_parser.add_argument("--hypothesis-id", required=True)
    hypothesis_parser.add_argument("--statement", required=True)
    hypothesis_parser.add_argument("--rationale", required=True)

    evidence_parser = subparsers.add_parser(
        "add-evidence", help="Append checksum-bound file evidence to the immutable ledger."
    )
    _add_run_argument(evidence_parser)
    evidence_parser.add_argument("--evidence-id", required=True)
    evidence_parser.add_argument("--evidence-type", required=True)
    evidence_parser.add_argument("--source", required=True, type=Path)
    evidence_parser.add_argument("--summary", required=True)

    action_parser = subparsers.add_parser(
        "record-action", help="Record one completed, failed, or rejected research action."
    )
    _add_run_argument(action_parser)
    action_parser.add_argument("--action-id", required=True)
    action_parser.add_argument("--action-type", required=True)
    action_parser.add_argument(
        "--status", required=True, choices=("completed", "failed", "rejected")
    )
    action_parser.add_argument("--summary", required=True)
    action_parser.add_argument("--cost-units", required=True, type=int)
    action_parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=Path,
        help="Optional output artifact file; repeat for multiple files.",
    )

    stop_parser = subparsers.add_parser(
        "stop", help="Append a terminal stop decision to the immutable ledger."
    )
    _add_run_argument(stop_parser)
    stop_parser.add_argument("--reason-code", required=True)
    stop_parser.add_argument("--summary", required=True)

    show_parser = subparsers.add_parser(
        "show", help="Print verified state reconstructed from the immutable ledger."
    )
    _add_run_argument(show_parser)

    verify_parser = subparsers.add_parser(
        "verify", help="Verify objective binding, hash chaining, and state reconstruction."
    )
    _add_run_argument(verify_parser)

    validate_actions = subparsers.add_parser(
        "validate-actions",
        help="Validate an action registry and all currently available bindings.",
    )
    _add_registry_arguments(validate_actions)

    list_actions = subparsers.add_parser(
        "list-actions",
        help="List available and planned actions from a validated registry.",
    )
    _add_registry_arguments(list_actions)

    describe = subparsers.add_parser(
        "describe-action",
        help="Show the complete bounded contract for one registered action.",
    )
    _add_registry_arguments(describe)
    describe.add_argument("--action-type", required=True)

    execute_audit = subparsers.add_parser(
        "execute-nasa-audit",
        help=(
            "Execute the typed existing-Battery-run audit request, independently "
            "verify outputs, and append the result to the research ledger."
        ),
    )
    execute_audit.add_argument("--request", required=True, type=Path)

    verify_audit = subparsers.add_parser(
        "verify-nasa-audit",
        help="Re-verify a completed or failed typed NASA audit action report.",
    )
    verify_audit.add_argument("--report", required=True, type=Path)

    execute_target = subparsers.add_parser(
        "execute-nasa-target-reference",
        help=(
            "Execute the fixed target-reference robustness request without model "
            "refitting, target repair, or row exclusion."
        ),
    )
    execute_target.add_argument("--request", required=True, type=Path)

    verify_target = subparsers.add_parser(
        "verify-nasa-target-reference",
        help="Recompute and verify a target-reference action report.",
    )
    verify_target.add_argument("--report", required=True, type=Path)

    execute_protocol = subparsers.add_parser(
        "execute-nasa-protocol-stratification",
        help=(
            "Execute exact-temperature battery-level protocol stratification without "
            "binning, filtering, model refitting, or evidence promotion."
        ),
    )
    execute_protocol.add_argument("--request", required=True, type=Path)

    verify_protocol = subparsers.add_parser(
        "verify-nasa-protocol-stratification",
        help="Recompute and verify a protocol-stratification action report.",
    )
    verify_protocol.add_argument("--report", required=True, type=Path)

    plan_next = subparsers.add_parser(
        "plan-nasa-next-action",
        help=(
            "Apply the deterministic NASA baseline policy to verified research state. "
            "The command recommends but never executes an action."
        ),
    )
    _add_run_argument(plan_next)
    _add_registry_arguments(plan_next)

    plan_generic = subparsers.add_parser(
        "plan-next-action",
        help=(
            "Translate existing domain-specific scientific state into the common read-only "
            "planning-decision contract. The command never executes the selected action."
        ),
    )
    _add_generic_planning_arguments(plan_generic)

    show_planning_state = subparsers.add_parser(
        "show-planning-state",
        help=(
            "Project the verified decision into the domain-general research question, blocker, "
            "evidence-gap, action-frontier, and stop/reopen state."
        ),
    )
    _add_generic_planning_arguments(show_planning_state)

    transition_parser = subparsers.add_parser(
        "decide-transition",
        help=(
            "Classify the current state as action/evidence pending authorization, manual review, "
            "blocked, or stopped. This command never executes or reopens research."
        ),
    )
    _add_generic_planning_arguments(transition_parser)

    authorization_parser = subparsers.add_parser(
        "assess-action-authorization",
        help=(
            "Revalidate the selected typed action, execution registry, verifier contract, and "
            "budget. A successful result still requires a separate explicit execution request."
        ),
    )
    _add_generic_planning_arguments(authorization_parser)

    reopen_parser = subparsers.add_parser(
        "prepare-reopen-review",
        help=(
            "Checksum-bind a new evidence file to one frozen reopen condition and route it to "
            "manual semantic review without asserting that the condition is satisfied."
        ),
    )
    _add_generic_planning_arguments(reopen_parser)
    reopen_parser.add_argument("--condition-index", required=True, type=int)
    reopen_parser.add_argument("--evidence", required=True, type=Path)
    return parser


def _load_registry_from_args(args: argparse.Namespace) -> dict[str, object]:
    return load_action_registry(
        args.registry,
        repository_root=args.repository_root,
    )


def _run_command(args: argparse.Namespace) -> dict[str, object] | list[dict[str, object]]:
    if args.command == "init":
        return initialize_research_loop(args.objective, args.output)
    if args.command == "add-hypothesis":
        return append_hypothesis(
            args.run,
            hypothesis_id=args.hypothesis_id,
            statement=args.statement,
            rationale=args.rationale,
        )
    if args.command == "add-evidence":
        return append_evidence(
            args.run,
            evidence_id=args.evidence_id,
            evidence_type=args.evidence_type,
            source_path=args.source,
            summary=args.summary,
        )
    if args.command == "record-action":
        return append_action(
            args.run,
            action_id=args.action_id,
            action_type=args.action_type,
            status=args.status,
            summary=args.summary,
            cost_units=args.cost_units,
            artifact_paths=args.artifact,
        )
    if args.command == "stop":
        return append_stop(
            args.run,
            reason_code=args.reason_code,
            summary=args.summary,
        )
    if args.command == "show":
        return load_research_state(args.run)
    if args.command == "verify":
        return verify_research_loop(args.run)
    if args.command == "validate-actions":
        registry = _load_registry_from_args(args)
        return {
            "valid": True,
            "registry_id": registry["registry_id"],
            "domain": registry["domain"],
            "registry_path": registry["registry_path"],
            "registry_sha256": registry["registry_sha256"],
            "available_action_count": registry["available_action_count"],
            "planned_action_count": registry["planned_action_count"],
        }
    if args.command == "list-actions":
        return action_summaries(_load_registry_from_args(args))
    if args.command == "describe-action":
        return describe_action(_load_registry_from_args(args), args.action_type)
    if args.command == "execute-nasa-audit":
        return execute_nasa_audit_action(args.request)
    if args.command == "verify-nasa-audit":
        return verify_nasa_audit_action_report(args.report)
    if args.command == "execute-nasa-target-reference":
        return execute_nasa_target_reference_action(args.request)
    if args.command == "verify-nasa-target-reference":
        return verify_nasa_target_reference_report(args.report)
    if args.command == "execute-nasa-protocol-stratification":
        return execute_nasa_protocol_stratification_action(args.request)
    if args.command == "verify-nasa-protocol-stratification":
        return verify_nasa_protocol_stratification_report(args.report)
    if args.command == "plan-nasa-next-action":
        return plan_nasa_next_action(
            args.run,
            args.registry,
            args.repository_root,
        )
    if args.command == "plan-next-action":
        return plan_research_next_action(
            args.adapter,
            repository_root=args.repository_root,
            research_run=args.run,
            action_registry_path=args.registry,
        )
    if args.command == "show-planning-state":
        return build_research_planning_state(
            args.adapter,
            repository_root=args.repository_root,
            research_run=args.run,
            action_registry_path=args.registry,
        )
    if args.command == "decide-transition":
        return build_current_research_transition(
            args.adapter,
            repository_root=args.repository_root,
            research_run=args.run,
            action_registry_path=args.registry,
        )
    if args.command == "assess-action-authorization":
        return assess_current_action_authorization(
            args.adapter,
            repository_root=args.repository_root,
            research_run=args.run,
            action_registry_path=args.registry,
        )
    if args.command == "prepare-reopen-review":
        return build_reopen_evidence_review(
            args.adapter,
            repository_root=args.repository_root,
            condition_index=args.condition_index,
            evidence_path=args.evidence,
            research_run=args.run,
            action_registry_path=args.registry,
        )
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run_command(args)
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ResearchLoopError,
        TypeError,
        KeyError,
        ValueError,
    ) as exc:
        print(f"Research loop command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    if isinstance(result, dict) and result.get("execution_status") == "failed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
