from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_PIN = "pypdf==6.18.1"


def test_historical_replay_pypdf_pin_is_synchronized_across_install_surfaces() -> None:
    pyproject = (_REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (_REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert f'"{_EXPECTED_PIN}"' in pyproject
    assert _EXPECTED_PIN in {line.strip() for line in requirements.splitlines()}
    assert "pypdf>=5,<7" not in pyproject
    assert "pypdf>=5,<7" not in requirements
