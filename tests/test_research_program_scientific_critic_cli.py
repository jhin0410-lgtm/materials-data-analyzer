from __future__ import annotations

from materials_data_analyzer import research_program_cli


def test_scientific_critic_cli_parser_exposes_planning_only_surface() -> None:
    parser = research_program_cli.build_parser()
    args = parser.parse_args(
        [
            "criticize-graph",
            "--mission",
            "mission.json",
            "--repository-root",
            ".",
            "--graph",
            "graph.json",
            "--target",
            "h1",
            "--target",
            "h2",
            "--artifact-root",
            "artifacts",
        ]
    )
    assert args.command == "criticize-graph"
    assert args.critic_targets == ["h1", "h2"]
    assert not hasattr(args, "request_queue")
    assert not hasattr(args, "action_registry")
    assert not hasattr(args, "output")
