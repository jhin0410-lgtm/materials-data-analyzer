"""Project-wide configuration for Materials Data Analyzer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _resolve_project_root() -> Path:
    """Resolve a writable analysis root for checkout and installed execution.

    ``MDA_PROJECT_ROOT`` takes precedence. A source checkout keeps the historical
    repository root. An installed console command defaults to the current working
    directory instead of attempting to write inside ``site-packages``.
    """
    configured = os.environ.get("MDA_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    source_candidate = Path(__file__).resolve().parents[1]
    if (source_candidate / "src").is_dir() and (source_candidate / "README.md").is_file():
        return source_candidate
    return Path.cwd().resolve()


PROJECT_ROOT = _resolve_project_root()
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
