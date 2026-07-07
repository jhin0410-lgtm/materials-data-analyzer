"""Shared analysis request/result schemas for future app and API layers.

These dataclasses are intentionally lightweight. They can be used later by a
Streamlit app or FastAPI endpoint while the current CLI and analyzer functions
continue returning their existing ``dict[str, Path]`` output maps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class AnalysisRequest:
    """User-provided analysis options independent of a specific interface."""

    mode: str
    run_name: str | None = None
    target: str | None = None
    targets: list[str] | None = None
    goals: list[str] | None = None
    goal: str = "maximize"
    features: list[str] | None = None
    scenario_input: str | None = None
    lsl: float | None = None
    usl: float | None = None


@dataclass
class AnalysisResult:
    """Structured analysis output for future CLI, app, and API reuse."""

    mode: str
    run_name: str
    output_files: dict[str, Path]
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    metrics: dict[str, object] = field(default_factory=dict)
    figures: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def analysis_result_from_output_files(
    mode: str,
    run_name: str,
    output_files: dict[str, Path],
    warnings: list[str] | None = None,
) -> AnalysisResult:
    """Wrap the current analyzer output-file map in an AnalysisResult."""
    return AnalysisResult(
        mode=mode,
        run_name=run_name,
        output_files=output_files,
        warnings=[] if warnings is None else warnings,
    )
