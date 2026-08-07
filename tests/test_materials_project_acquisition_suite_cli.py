from __future__ import annotations

import argparse
from pathlib import Path

from scripts import run_materials_project_acquisition_loop as cli


def test_suite_runs_all_predeclared_strategies_before_comparison(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_run(**kwargs):
        strategy = kwargs["strategy"]
        calls.append(("run", strategy))
        Path(kwargs["output_dir"]).mkdir(parents=True, exist_ok=True)
        return {"execution_status": "completed"}

    def fake_evaluate(**kwargs):
        strategy = Path(kwargs["sequence_dir"]).name
        calls.append(("evaluate", strategy))
        Path(kwargs["output_dir"]).mkdir(parents=True, exist_ok=True)
        return {
            "evaluation_status": "completed",
            "cost_used": 100,
            "primary_model_result": {
                "model_variant": "ridge_raw",
                "seed_only_mae": 1.0,
                "final_sequence_mae": 0.9,
            },
        }

    def fake_compare(**kwargs):
        calls.append(("compare", "all"))
        assert [path.name for path in kwargs["evaluation_dirs"]] == list(cli.STRATEGIES)
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("{}\n", encoding="utf-8")
        return {
            "benchmark_id": "fixture",
            "primary_model": "ridge_raw",
            "strategy_count": 4,
            "strategies": [],
            "lowest_locked_mae_strategy": "uncertainty",
            "scientific_evidence_level": "Diagnostic",
            "selection_warning": "fixture",
        }

    monkeypatch.setattr(cli, "run_materials_project_acquisition_sequence", fake_run)
    monkeypatch.setattr(cli, "evaluate_materials_project_acquisition_sequence", fake_evaluate)
    monkeypatch.setattr(cli, "compare_materials_project_acquisition_evaluations", fake_compare)

    args = argparse.Namespace(
        benchmark=tmp_path / "benchmark",
        instance=tmp_path / "instance.json",
        benchmark_config=tmp_path / "benchmark-config.json",
        acquisition_config=tmp_path / "acquisition-config.json",
        output_root=tmp_path / "suite",
        overwrite=False,
    )
    result = cli._run_suite(args)

    assert calls == [
        ("run", "fixed_catalog"),
        ("evaluate", "fixed_catalog"),
        ("run", "random"),
        ("evaluate", "random"),
        ("run", "diversity"),
        ("evaluate", "diversity"),
        ("run", "uncertainty"),
        ("evaluate", "uncertainty"),
        ("compare", "all"),
    ]
    assert result["suite_status"] == "completed"
    assert result["comparison"]["strategy_count"] == 4
    assert (tmp_path / "suite" / "strategy_comparison.json").is_file()


def test_suite_parser_uses_locked_four_strategy_inventory(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(
        ["suite", "--output-root", str(tmp_path / "suite")]
    )
    assert args.command == "suite"
    assert args.output_root == tmp_path / "suite"
    assert cli.STRATEGIES == (
        "fixed_catalog",
        "random",
        "diversity",
        "uncertainty",
    )
