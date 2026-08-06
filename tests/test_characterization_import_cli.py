from __future__ import annotations

import tomllib
from pathlib import Path

import materials_data_analyzer.characterization_import_cli as cli

ROOT = Path(__file__).resolve().parents[1]


def test_characterization_import_cli_forwards_explicit_inputs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    bundle = tmp_path / "characterization_handoff_bundle.json"
    process = tmp_path / "process.csv"
    output = tmp_path / "consumer"
    bundle.write_text("{}", encoding="utf-8")
    process.write_text("sample_id\nsample-a\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_consume(
        bundle_manifest,
        output_dir,
        *,
        process_table_path=None,
        requested_use="descriptive",
        split_group_field=None,
    ):
        captured.update(
            {
                "bundle_manifest": bundle_manifest,
                "output_dir": output_dir,
                "process_table_path": process_table_path,
                "requested_use": requested_use,
                "split_group_field": split_group_field,
            }
        )
        return {
            "integrated_sample_table": Path(output_dir) / "integrated_sample_table.csv",
            "cross_repository_report": Path(output_dir) / "cross_repository_handoff_report.md",
        }

    monkeypatch.setattr(
        cli,
        "consume_characterization_bundle_for_use",
        fake_consume,
    )
    result = cli.main(
        [
            "--bundle-manifest",
            str(bundle),
            "--process-table",
            str(process),
            "--output",
            str(output),
            "--requested-use",
            "association",
            "--split-group-field",
            "parent_specimen_id",
        ]
    )

    assert result == 0
    assert captured == {
        "bundle_manifest": bundle,
        "output_dir": output,
        "process_table_path": process,
        "requested_use": "association",
        "split_group_field": "parent_specimen_id",
    }
    stdout = capsys.readouterr().out
    assert "Cross-repository characterization handoff completed." in stdout
    assert "integrated_sample_table" in stdout
    assert "cross_repository_report" in stdout


def test_characterization_import_cli_fails_closed(tmp_path: Path, monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ValueError("checksum mismatch")

    monkeypatch.setattr(
        cli,
        "consume_characterization_bundle_for_use",
        fail,
    )
    result = cli.main(
        [
            "--bundle-manifest",
            str(tmp_path / "bundle.json"),
            "--output",
            str(tmp_path / "output"),
        ]
    )

    assert result == 1
    assert "checksum mismatch" in capsys.readouterr().err


def test_characterization_import_is_installed_console_command() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["scripts"]["mda-characterization-import"] == (
        "materials_data_analyzer.characterization_import_cli:main"
    )


def test_legacy_script_delegates_to_packaged_command() -> None:
    text = (ROOT / "scripts" / "consume_characterization_handoff_bundle.py").read_text(
        encoding="utf-8"
    )

    assert "materials_data_analyzer.characterization_import_cli import main" in text
    assert "consume_characterization_bundle" not in text
