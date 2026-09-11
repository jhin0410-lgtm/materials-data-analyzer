from pathlib import Path

VERIFIER = Path("src/materials_data_analyzer/research_loop/autonomous_production_cycle1_transport_stop_verifier.py")
TESTS = Path("tests/test_autonomous_production_cycle1_transport_stop_verifier.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


verifier = VERIFIER.read_text(encoding="utf-8")
verifier = replace_once(
    verifier,
    '''def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Cycle1TransportStopVerificationError(message)


def _published_record_file_route(''',
    '''def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Cycle1TransportStopVerificationError(message)


def _portable_qualification(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    normalized = dict(value)
    source_path = normalized.get("source_config_path")
    _require(
        isinstance(source_path, str) and source_path,
        f"{field} source config path is missing",
    )
    portable_path = source_path.replace("\\\\", "/")
    _require(
        portable_path == SOURCE_CONFIG_PATH
        or portable_path.endswith(f"/{SOURCE_CONFIG_PATH}"),
        f"{field} source config path differs from repository-pinned identity",
    )
    normalized["source_config_path"] = SOURCE_CONFIG_PATH
    return normalized


def _published_record_file_route(''',
    "portable qualification helper",
)
verifier = replace_once(
    verifier,
    '''    _require(
        persisted_qualification == qualification,
        "retained standing network policy qualification differs from reconstructed authority",
    )
''',
    '''    _require(
        _portable_qualification(
            persisted_qualification,
            "retained standing network policy qualification",
        )
        == _portable_qualification(
            qualification,
            "reconstructed standing network policy qualification",
        ),
        "retained standing network policy qualification differs from reconstructed authority",
    )
''',
    "portable qualification equality",
)
VERIFIER.write_text(verifier, encoding="utf-8")


tests = TESTS.read_text(encoding="utf-8")
new_tests = r'''


def test_verifier_accepts_exported_qualification_from_different_checkout_root(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    qualification_path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["source_config_path"] = (
        "/different/checkout/materials-data-analyzer/"
        "configs/research/in625_zenodo_20503603_verified_source.v1.json"
    )
    qualification_path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    result = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )
    assert result["verification_status"] == "cycle_1_transport_stop_authenticated"


def test_verifier_rejects_exported_qualification_with_wrong_source_path(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    qualification_path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["source_config_path"] = "/different/checkout/configs/research/other.json"
    qualification_path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="source config path differs from repository-pinned identity",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
'''
if "test_verifier_accepts_exported_qualification_from_different_checkout_root" in tests:
    raise SystemExit("qualification portability tests already present")
tests = tests.rstrip() + new_tests.rstrip() + "\n"
TESTS.write_text(tests, encoding="utf-8")
