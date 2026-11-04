from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_PIN = "pypdf==6.21.4"


def test_historical_replay_pypdf_pin_is_synchronized_across_install_surfaces() -> None:
    pyproject = (_REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (_REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert f'"{_EXPECTED_PIN}"' in pyproject
    assert _EXPECTED_PIN in {line.strip() for line in requirements.splitlines()}
    assert "pypdf>=5,<7" not in pyproject
    assert "pypdf>=5,<7" not in requirements
    assert not (_REPOSITORY_ROOT / "requirements-historical-replay.txt").exists()
    workflow = (_REPOSITORY_ROOT / ".github/workflows/quality.yml").read_text()
    assert "requirements-historical-replay.txt" not in workflow
    assert "git archive 257dcf" not in workflow
    assert "--network none --read-only --cap-drop ALL" in workflow
    assert "--memory 1536m" in workflow
    assert "resource.RLIMIT_AS" in workflow
