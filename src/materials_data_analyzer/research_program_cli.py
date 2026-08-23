"""Installed CLI for mission-level autonomous research planning contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop import (
    ResearchLoopError,
    authenticate_transition_bundle,
    build_research_program,
    build_scientific_critic_report,
    validate_reasoning_proposal_file,
)
from materials_data_analyzer.research_loop.autonomous_production_multisource_extension import (
    run_autonomous_production,
)
from materials_data_analyzer.research_loop.epistemic_graph import (
    evaluate_epistemic_graph,
)
from materials_data_analyzer.research_loop.epistemic_transition import (
    apply_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.policy_authorized_closed_loop import (
    run_policy_authorized_closed_loop,
)

_AUTONOMOUS_PRODUCTION_MISSION = Path(
    "configs/research/autonomous_in625_production_mission.v1.json"
)
_AUTONOMOUS_PRODUCTION_MISSION_SHA256 = (
    "44091458e8a10a6ba4ef67a47056d98e4ba1a2ac5e29695cbeba7bb79f47160f"
)
_AUTONOMOUS_PRODUCTION_OUTPUT = Path("outputs/autonomous-in625-production")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchLoopError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path) -> tuple[dict[str, Any], Path, str]:
    resolved = path.expanduser().resolve(strict=True)
    raw = resolved.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchLoopError(f"invalid UTF-8 in {resolved}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ResearchLoopError(f"invalid JSON in {resolved}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchLoopError(f"JSON root must be an object: {resolved}")
    digest = hashlib.sha256(raw).hexdigest()
    return value, resolved, digest


def _add_program_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mission",
        required=True,
        type=Path,
        help="Versioned research-mission JSON file.",
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        type=Path,
        help="Repository checkout root containing tracked planning evidence.",
    )
    parser.add_argument(
        "--context",
        type=Path,
        help=(
            "Optional runtime-context JSON. Required only for workstreams such as NASA "
            "that depend on an existing research run and action registry."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-research-program",
        description=(
            "Build a provenance-aware mission-level research agenda, validate evidence-bound "
            "scientific reasoning proposals, independently re-authenticate published transition "
            "bundles, evaluate and critique checksum-bound epistemic graphs, create immutable "
            "result-to-graph transitions, run a finite policy-authorized local execute-record-regate "
            "loop, or run the exact audited autonomous IN625 production profile. Only run-autonomous "
            "may initiate narrowly mission-pinned Zenodo, NIST mds2-2923, and reviewed official/paper "
            "condition-evidence acquisitions; no command grants unrestricted-web, physical-experiment, "
            "or arbitrary-command authority."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    authenticate_bundle = subparsers.add_parser(
        "authenticate-transition-bundle",
        help=(
            "Independently re-authenticate the current transition in a published authenticated "
            "bundle from its exact bundle-relative bytes. This is provenance-only and does not "
            "grant scientific or execution authority."
        ),
    )
    authenticate_bundle.add_argument(
        "--bundle",
        required=True,
        type=Path,
        help="Published authenticated-transition bundle directory.",
    )

    autonomous = subparsers.add_parser(
        "run-autonomous",
        help=(
            "Run the exact audited IN625 production mission from the independently pinned mission "
            "SHA: acquire Zenodo 20503603, execute the typed row-level intake and physical "
            "comparability gate, acquire and scientifically intake exact NIST mds2-2923 geometry "
            "evidence, then acquire mission-pinned NIST official pages and primary papers and run "
            "a reviewed geometry-condition mapping. Literature claims retain claim-level authority "
            "and never become row-level measurements. The command advances to a bounded calibration/"
            "protocol bridge frontier when direct condition equivalence is not established."
        ),
    )
    autonomous.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository checkout root. Defaults to the current directory.",
    )
    autonomous.add_argument(
        "--output",
        type=Path,
        default=_AUTONOMOUS_PRODUCTION_OUTPUT,
        help=(
            "Repository-contained output directory. It must be absent or empty. "
            "Defaults to outputs/autonomous-in625-production."
        ),
    )
    autonomous.add_argument(
        "--max-cycles",
        type=int,
        default=5,
        help="Maximum audited production cycles (1-8). Defaults to 5.",
    )

    show = subparsers.add_parser(
        "show",
        help=(
            "Generate bounded research goals across enabled workstreams and select the next "
            "mission-level planning step."
        ),
    )
    _add_program_arguments(show)

    validate = subparsers.add_parser(
        "validate-proposal",
        help=(
            "Validate a scientific reasoning proposal against the current mission goals and "
            "checksum-bound evidence. Validation is planning-only and grants no execution authority."
        ),
    )
    _add_program_arguments(validate)
    validate.add_argument("--proposal", required=True, type=Path)

    graph = subparsers.add_parser(
        "evaluate-graph",
        help=(
            "Validate and evaluate an epistemic graph. Only domain-verified relations with "
            "checksum-bound verifier artifacts may affect verified status, and positive support "
            "remains provisional."
        ),
    )
    _add_program_arguments(graph)
    graph.add_argument("--graph", required=True, type=Path)
    graph.add_argument(
        "--artifact-root",
        type=Path,
        help=(
            "Root for relative verifier/result artifact paths. Defaults to --repository-root."
        ),
    )

    critic = subparsers.add_parser(
        "criticize-graph",
        help=(
            "Run the deterministic scientific critic over a checksum-bound graph. It proposes "
            "counterevidence, robustness, replication, and discriminating next-work items but "
            "does not change scientific status or authorize execution."
        ),
    )
    _add_program_arguments(critic)
    critic.add_argument("--graph", required=True, type=Path)
    critic.add_argument(
        "--target",
        action="append",
        dest="critic_targets",
        help=(
            "Optional hypothesis/claim/conclusion node ID to critique. Repeat for multiple "
            "targets. When omitted, all assessed targets are reviewed."
        ),
    )
    critic.add_argument(
        "--artifact-root",
        type=Path,
        help="Root for graph result/verifier artifacts. Defaults to --repository-root.",
    )

    transition = subparsers.add_parser(
        "apply-graph-transition",
        help=(
            "Append one completed result to an epistemic graph and optionally apply a separate "
            "checksum-bound domain-verification decision. The base graph is never mutated."
        ),
    )
    _add_program_arguments(transition)
    transition.add_argument("--base-graph", required=True, type=Path)
    transition.add_argument("--transition-proposal", required=True, type=Path)
    transition.add_argument("--verification-decision", type=Path)
    transition.add_argument("--output", required=True, type=Path)
    transition.add_argument(
        "--artifact-root",
        type=Path,
        help="Root for relative result/verifier artifact paths. Defaults to --repository-root.",
    )

    closed = subparsers.add_parser(
        "run-closed-loop",
        help=(
            "Consume a finite checksum-bound request queue, execute only currently authorized "
            "typed local actions, record each verified action report into an immutable successor "
            "graph without directional inference, and re-gate/replan from that successor."
        ),
    )
    _add_program_arguments(closed)
    closed.add_argument("--base-graph", required=True, type=Path)
    closed.add_argument("--epistemic-workstream", required=True)
    closed.add_argument(
        "--epistemic-target",
        required=True,
        action="append",
        dest="epistemic_targets",
        help="Target hypothesis/claim/conclusion node ID. Repeat for multiple targets.",
    )
    closed.add_argument("--research-run", required=True, type=Path)
    closed.add_argument("--action-registry", required=True, type=Path)
    closed.add_argument("--request-queue", required=True, type=Path)
    closed.add_argument("--request-root", type=Path)
    closed.add_argument("--result-record-plan", required=True, type=Path)
    closed.add_argument("--output", required=True, type=Path)
    closed.add_argument("--max-cycles", type=int, default=8)
    closed.add_argument(
        "--artifact-root",
        type=Path,
        help="Root for verifier/result artifacts. Defaults to --repository-root.",
    )
    return parser


def _build_program(args: argparse.Namespace) -> dict[str, object]:
    return build_research_program(
        args.mission,
        repository_root=args.repository_root,
        runtime_context_path=args.context,
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "authenticate-transition-bundle":
        return authenticate_transition_bundle(args.bundle)
    if args.command == "run-autonomous":
        repository_root = args.repository_root.expanduser().resolve(strict=True)
        return run_autonomous_production(
            repository_root=repository_root,
            mission_path=repository_root / _AUTONOMOUS_PRODUCTION_MISSION,
            expected_mission_sha256=_AUTONOMOUS_PRODUCTION_MISSION_SHA256,
            output_root=args.output,
            max_cycles=args.max_cycles,
        )
    if args.command == "run-closed-loop":
        if args.context is None:
            raise ResearchLoopError("run-closed-loop requires --context")
        artifact_root = args.artifact_root or args.repository_root
        return run_policy_authorized_closed_loop(
            "nasa-battery",
            repository_root=args.repository_root,
            mission_path=args.mission,
            initial_graph_path=args.base_graph,
            epistemic_workstream_id=args.epistemic_workstream,
            epistemic_target_node_ids=args.epistemic_targets,
            runtime_context_path=args.context,
            artifact_root=artifact_root,
            research_run=args.research_run,
            action_registry_path=args.action_registry,
            request_queue_path=args.request_queue,
            request_root=args.request_root,
            result_record_plan_path=args.result_record_plan,
            output_root=args.output,
            max_cycles=args.max_cycles,
        )

    program = _build_program(args)
    if args.command == "show":
        return program
    if args.command == "validate-proposal":
        return validate_reasoning_proposal_file(args.proposal, program)
    if args.command == "evaluate-graph":
        graph, graph_path, graph_sha256 = _load_json_object(args.graph)
        artifact_root = args.artifact_root or args.repository_root
        result = evaluate_epistemic_graph(
            graph,
            program_state=program,
            artifact_root=artifact_root,
        )
        return {
            **result,
            "graph_binding": {
                "path": str(graph_path),
                "sha256": graph_sha256,
            },
        }
    if args.command == "criticize-graph":
        artifact_root = args.artifact_root or args.repository_root
        return build_scientific_critic_report(
            args.graph,
            program_state=program,
            artifact_root=artifact_root,
            target_node_ids=args.critic_targets,
        )
    if args.command == "apply-graph-transition":
        artifact_root = args.artifact_root or args.repository_root
        return apply_epistemic_transition_files(
            base_graph_path=args.base_graph,
            proposal_path=args.transition_proposal,
            verification_decision_path=args.verification_decision,
            program_state=program,
            artifact_root=artifact_root,
            output_dir=args.output,
        )
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run(args)
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ResearchLoopError,
        TypeError,
        KeyError,
        ValueError,
    ) as exc:
        print(f"Research program command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
