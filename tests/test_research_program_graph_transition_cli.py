from __future__ import annotations

from materials_data_analyzer.research_program_cli import build_parser


def test_research_program_parser_exposes_graph_transition_command() -> None:
    args = build_parser().parse_args(
        [
            "apply-graph-transition",
            "--mission",
            "mission.json",
            "--repository-root",
            ".",
            "--base-graph",
            "graph.json",
            "--transition-proposal",
            "proposal.json",
            "--verification-decision",
            "verification.json",
            "--artifact-root",
            "artifacts",
            "--output",
            "out",
        ]
    )
    assert args.command == "apply-graph-transition"
    assert str(args.base_graph) == "graph.json"
    assert str(args.transition_proposal) == "proposal.json"
    assert str(args.verification_decision) == "verification.json"
    assert str(args.output) == "out"
