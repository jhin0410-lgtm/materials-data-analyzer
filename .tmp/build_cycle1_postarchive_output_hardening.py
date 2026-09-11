from pathlib import Path

VERIFIER = Path("src/materials_data_analyzer/research_loop/autonomous_production_cycle1_transport_stop_verifier.py")
TESTS = Path("tests/test_autonomous_production_cycle1_transport_stop_verifier.py")

text = VERIFIER.read_text(encoding="utf-8")

anchor = 'ZENODO_HOST = "zenodo.org"\n\n\nclass Cycle1TransportStopVerificationError'
replacement = '''ZENODO_HOST = "zenodo.org"\n_POST_ARCHIVE_PRODUCTION_PATHS = (\n    "selected-source-files",\n    "archive-manifest.json",\n    "reviewed-tensile",\n    "tensile-quality-verification.json",\n    "typed-research-objective.json",\n    "typed-research-run",\n    "cycle-1-planning.json",\n    "machine-authored-request",\n    "machine-request-compilation.json",\n    "typed-execution-handoff.json",\n    "typed-execution-result.json",\n    "typed-research-state.json",\n    "quality-aware-rediagnosis.json",\n    "physical-comparability-assessment.json",\n)\n\n\nclass Cycle1TransportStopVerificationError'''
if text.count(anchor) != 1:
    raise SystemExit("constant insertion anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''    _require(\n        not (output / "network-acquisition-receipt.json").exists(),\n        "transport stop may not retain a completed network acquisition receipt",\n    )\n\n    bounded = _read_json(output / "bounded-stop.json", "bounded stop")\n'''
replacement = '''    _require(\n        not (output / "network-acquisition-receipt.json").exists(),\n        "transport stop may not retain a completed network acquisition receipt",\n    )\n    for relative_path in _POST_ARCHIVE_PRODUCTION_PATHS:\n        _require(\n            not (output / relative_path).exists(),\n            "transport stop may not retain post-archive production artifact: "\n            f"{relative_path}",\n        )\n\n    bounded = _read_json(output / "bounded-stop.json", "bounded stop")\n'''
if text.count(anchor) != 1:
    raise SystemExit("post-archive enforcement anchor drifted")
text = text.replace(anchor, replacement)
VERIFIER.write_text(text, encoding="utf-8")

append = r'''

@pytest.mark.parametrize(
    "artifact_name",
    [
        "selected-source-files",
        "archive-manifest.json",
        "reviewed-tensile",
        "tensile-quality-verification.json",
        "typed-research-objective.json",
        "typed-research-run",
        "cycle-1-planning.json",
        "machine-authored-request",
        "machine-request-compilation.json",
        "typed-execution-handoff.json",
        "typed-execution-result.json",
        "typed-research-state.json",
        "quality-aware-rediagnosis.json",
        "physical-comparability-assessment.json",
    ],
)
def test_transport_stop_rejects_known_post_archive_production_outputs(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    artifact = output / artifact_name
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("forged downstream production artifact", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="post-archive production artifact",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
'''

test_text = TESTS.read_text(encoding="utf-8")
marker = "def test_transport_stop_rejects_known_post_archive_production_outputs("
if marker in test_text:
    raise SystemExit("post-archive output regression already present")
TESTS.write_text(
    test_text.rstrip() + "\n\n" + append.strip() + "\n",
    encoding="utf-8",
)
