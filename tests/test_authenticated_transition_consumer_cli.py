from __future__ import annotations

import json
from pathlib import Path

from materials_data_analyzer import research_program_cli


def test_bundle_consumer_subcommand_requires_only_bundle_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    observed: list[Path] = []

    def fake_authenticate(value: str | Path) -> dict[str, object]:
        observed.append(Path(value))
        return {
            "schema_version": "1.0",
            "current_transition_exact_provenance_authenticated": True,
            "scientific_authority_applied": False,
        }

    monkeypatch.setattr(
        research_program_cli,
        "authenticate_transition_bundle",
        fake_authenticate,
    )

    code = research_program_cli.main(
        ["authenticate-transition-bundle", "--bundle", str(bundle)]
    )
    assert code == 0
    assert observed == [bundle]
    payload = json.loads(capsys.readouterr().out)
    assert payload["current_transition_exact_provenance_authenticated"] is True
    assert payload["scientific_authority_applied"] is False


def test_bundle_consumer_subcommand_does_not_build_research_program(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()

    def fail_build(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("bundle authentication must not build a research program")

    monkeypatch.setattr(research_program_cli, "_build_program", fail_build)
    monkeypatch.setattr(
        research_program_cli,
        "authenticate_transition_bundle",
        lambda value: {"bundle": str(value)},
    )

    assert (
        research_program_cli.main(
            ["authenticate-transition-bundle", "--bundle", str(bundle)]
        )
        == 0
    )


def test_bundle_consumer_subcommand_surfaces_provenance_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()

    def fail_authenticate(value: str | Path) -> dict[str, object]:
        del value
        raise research_program_cli.ResearchLoopError("bundle provenance mismatch")

    monkeypatch.setattr(
        research_program_cli,
        "authenticate_transition_bundle",
        fail_authenticate,
    )

    code = research_program_cli.main(
        ["authenticate-transition-bundle", "--bundle", str(bundle)]
    )
    assert code == 1
    assert "bundle provenance mismatch" in capsys.readouterr().err
