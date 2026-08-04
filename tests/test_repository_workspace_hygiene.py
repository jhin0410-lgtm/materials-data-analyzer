from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _non_comment_lines(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_gitignore_protects_versioned_virtualenvs_and_nasa_import() -> None:
    rules = _non_comment_lines(PROJECT_ROOT / ".gitignore")

    assert ".venv*/" in rules
    assert "data/processed/nasa_pcoe_battery_import/" in rules
    assert "outputs/**" in rules
    assert "data/raw/**" in rules


def test_workspace_hygiene_policy_preserves_canonical_nasa_evidence() -> None:
    policy = (PROJECT_ROOT / "docs" / "WORKSPACE_HYGIENE.md").read_text(
        encoding="utf-8"
    )

    assert "data/processed/nasa_pcoe_battery_import/" in policy
    assert "outputs/nasa_pcoe_signal_enriched_battery_intelligence/" in policy
    assert "final post-remediation closed audit ZIP" in policy
    assert "git clean -fdx" in policy
    assert "The predictive Ridge result remains `Unsupported`" in policy


def test_outputs_policy_links_workspace_hygiene() -> None:
    outputs_policy = (PROJECT_ROOT / "docs" / "OUTPUTS_POLICY.md").read_text(
        encoding="utf-8"
    )

    assert "[Local Workspace Hygiene](WORKSPACE_HYGIENE.md)" in outputs_policy
    assert "Canonical evidence" in outputs_policy
    assert "git clean -fdx" in outputs_policy
