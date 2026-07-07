"""Tests for shared analysis result schemas."""

from __future__ import annotations

from pathlib import Path

from results import AnalysisRequest, analysis_result_from_output_files


def test_analysis_request_defaults_goal_to_maximize() -> None:
    request = AnalysisRequest(mode="simulation")

    assert request.goal == "maximize"
    assert request.run_name is None


def test_analysis_result_wrapper_preserves_output_files() -> None:
    output_files = {"report": Path("outputs/demo/reports/report.md")}

    result = analysis_result_from_output_files(
        mode="eda",
        run_name="demo",
        output_files=output_files,
    )

    assert result.mode == "eda"
    assert result.run_name == "demo"
    assert result.output_files == output_files
    assert result.tables == {}
    assert result.warnings == []
