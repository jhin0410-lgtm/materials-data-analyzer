from pathlib import Path

VERIFIER = Path("src/materials_data_analyzer/research_loop/autonomous_production_cycle1_transport_stop_verifier.py")
TESTS = Path("tests/test_autonomous_production_cycle1_transport_stop_verifier.py")

text = VERIFIER.read_text(encoding="utf-8")

anchor = '''    _require(\n        isinstance(archive_name, str) and archive_name,\n        "source archive identity is invalid",\n    )\n\n    bounded = _read_json(output / "bounded-stop.json", "bounded stop")\n'''
replacement = '''    _require(\n        isinstance(archive_name, str) and archive_name,\n        "source archive identity is invalid",\n    )\n    _require(\n        not (output / archive_name).exists(),\n        "transport stop may not retain completed archive bytes",\n    )\n    _require(\n        not (output / "network-acquisition-receipt.json").exists(),\n        "transport stop may not retain a completed network acquisition receipt",\n    )\n\n    bounded = _read_json(output / "bounded-stop.json", "bounded stop")\n'''
if text.count(anchor) != 1:
    raise SystemExit("global downstream-artifact anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''        _require(\n            not (output / "record.json").exists(),\n            "metadata transport stop may not retain nonexistent completed metadata",\n        )\n        _require(\n            not (output / "source-readme-manifest.json").exists(),\n'''
replacement = '''        _require(\n            not (output / "record.json").exists(),\n            "metadata transport stop may not retain nonexistent completed metadata",\n        )\n        _require(\n            not (output / readme_name).exists(),\n            "metadata transport stop may not retain downstream README bytes",\n        )\n        _require(\n            not (output / "source-readme-manifest.json").exists(),\n'''
if text.count(anchor) != 1:
    raise SystemExit("metadata sequencing anchor drifted")
text = text.replace(anchor, replacement)

redundant = '''        _require(\n            not (output / archive_name).exists(),\n            "archive transport stop may not retain completed archive bytes",\n        )\n        _require(\n            not (output / "network-acquisition-receipt.json").exists(),\n            "archive transport stop may not retain a completed network acquisition receipt",\n        )\n'''
if text.count(redundant) != 1:
    raise SystemExit("archive duplicate downstream checks drifted")
text = text.replace(redundant, "")
VERIFIER.write_text(text, encoding="utf-8")

append = r'''

@pytest.mark.parametrize(
    ("artifact_name", "error_match"),
    [
        (README_NAME, "downstream README bytes"),
        ("Dataset.zip", "completed archive bytes"),
        (
            "network-acquisition-receipt.json",
            "completed network acquisition receipt",
        ),
    ],
)
def test_metadata_stop_rejects_impossible_downstream_artifacts(
    tmp_path: Path,
    artifact_name: str,
    error_match: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    (output / artifact_name).write_bytes(b"impossible downstream artifact")

    with pytest.raises(Cycle1TransportStopVerificationError, match=error_match):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


@pytest.mark.parametrize(
    ("artifact_name", "error_match"),
    [
        ("Dataset.zip", "completed archive bytes"),
        (
            "network-acquisition-receipt.json",
            "completed network acquisition receipt",
        ),
    ],
)
def test_readme_stop_rejects_impossible_archive_success_artifacts(
    tmp_path: Path,
    artifact_name: str,
    error_match: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    (output / artifact_name).write_bytes(b"impossible downstream artifact")

    with pytest.raises(Cycle1TransportStopVerificationError, match=error_match):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
'''

test_text = TESTS.read_text(encoding="utf-8")
marker = "def test_metadata_stop_rejects_impossible_downstream_artifacts("
if marker in test_text:
    raise SystemExit("sequencing regression already present")
TESTS.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")
