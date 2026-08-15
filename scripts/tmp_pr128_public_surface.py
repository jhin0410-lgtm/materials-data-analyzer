from __future__ import annotations

from pathlib import Path

INIT = Path("src/materials_data_analyzer/research_loop/__init__.py")
CLI = Path("src/materials_data_analyzer/research_program_cli.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_init() -> None:
    text = INIT.read_text(encoding="utf-8")
    anchor = '''from .authorized_execution import (
    EXECUTION_POLICY_VERSION,
    EXECUTION_SCHEMA_VERSION,
    AuthorizedExecutionError,
    execute_authorized_action,
)
'''
    addition = anchor + '''from .authenticated_transition_consumer import (
    AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION,
    AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION,
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)
'''
    text = replace_once(text, anchor, addition, "consumer import")
    text = replace_once(
        text,
        '    "AUTHORIZATION_SCHEMA_VERSION",\n',
        '    "AUTHORIZATION_SCHEMA_VERSION",\n    "AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION",\n    "AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION",\n',
        "consumer constants export",
    )
    text = replace_once(
        text,
        '    "AuthorizedExecutionError",\n',
        '    "AuthenticatedTransitionConsumerError",\n    "AuthorizedExecutionError",\n',
        "consumer error export",
    )
    text = replace_once(
        text,
        '    "available_planning_adapters",\n',
        '    "authenticate_transition_bundle",\n    "available_planning_adapters",\n',
        "consumer function export",
    )
    INIT.write_text(text, encoding="utf-8")


def patch_cli() -> None:
    text = CLI.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    ResearchLoopError,
    build_research_program,
''',
        '''    ResearchLoopError,
    authenticate_transition_bundle,
    build_research_program,
''',
        "CLI import",
    )
    text = replace_once(
        text,
        '''            "Build a provenance-aware mission-level research agenda, validate evidence-bound "
            "scientific reasoning proposals, evaluate and critique checksum-bound epistemic "
            "graphs, create immutable result-to-graph transitions, and run a finite "
''',
        '''            "Build a provenance-aware mission-level research agenda, validate evidence-bound "
            "scientific reasoning proposals, independently re-authenticate published transition "
            "bundles, evaluate and critique checksum-bound epistemic graphs, create immutable "
            "result-to-graph transitions, and run a finite "
''',
        "CLI description",
    )
    marker = '''    subparsers = parser.add_subparsers(dest="command", required=True)

'''
    addition = marker + '''    authenticate_bundle = subparsers.add_parser(
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

'''
    text = replace_once(text, marker, addition, "CLI parser")
    marker = '''def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "run-closed-loop":
'''
    replacement = '''def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "authenticate-transition-bundle":
        return authenticate_transition_bundle(args.bundle)
    if args.command == "run-closed-loop":
'''
    text = replace_once(text, marker, replacement, "CLI execution")
    CLI.write_text(text, encoding="utf-8")


def main() -> None:
    patch_init()
    patch_cli()


if __name__ == "__main__":
    main()
