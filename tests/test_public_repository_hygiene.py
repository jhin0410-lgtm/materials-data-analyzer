"""Public-release hygiene regression tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_release_policy_files_exist() -> None:
    for relative in (
        "LICENSE",
        "SECURITY.md",
        "docs/PUBLIC_REPOSITORY_POLICY.md",
    ):
        assert (PROJECT_ROOT / relative).is_file(), relative


def test_gitignore_contains_public_safety_rules() -> None:
    text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    required_rules = {
        ".env",
        ".env.*",
        "!.env.example",
        "*.pem",
        "*.key",
        ".streamlit/secrets.toml",
        "data/raw/**",
        "data/local/**",
        "outputs/**",
        ".vscode/",
        ".idea/",
        ".ipynb_checkpoints/",
    }
    missing = sorted(rule for rule in required_rules if rule not in text)
    assert not missing, missing


def test_tracked_checkout_passes_hygiene_scan() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_public_repository_hygiene.py"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "hygiene check passed" in completed.stdout.lower()
