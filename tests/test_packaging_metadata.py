"""Tests for the installable package and stable console command."""

from __future__ import annotations

import tomllib
from pathlib import Path

import materials_data_analyzer
from platform_core.version import PLATFORM_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_package_version_reuses_platform_version() -> None:
    assert materials_data_analyzer.__version__ == PLATFORM_VERSION


def test_pyproject_declares_stable_mda_console_command() -> None:
    payload = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert payload["project"]["name"] == "materials-data-analyzer"
    assert payload["project"]["scripts"]["mda"] == (
        "materials_data_analyzer.cli:main"
    )
    assert payload["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "platform_core.version.PLATFORM_VERSION"
    )
