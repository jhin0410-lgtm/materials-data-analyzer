"""Project-wide configuration for Materials Data Analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("data") / "sample" / "experiment_process.csv"
DEFAULT_PROCESS_TARGET = "yield_percent"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
ANALYSIS_MODES = (
    "eda",
    "process",
    "reliability",
    "smart_factory",
    "spc",
    "simulation",
)


@dataclass(frozen=True)
class OutputPaths:
    """A small container for the output folders used by one analysis run."""

    root: Path
    processed: Path
    figures: Path
    reports: Path
