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
    'ZENODO_HOST = "zenodo.org"\n_POST_ARCHIVE_PRODUCTION_PATHS = (',
    'ZENODO_HOST = "zenodo.org"\n'
    '_RETAINED_METADATA_MAX_BYTES = 8 * 1024 * 1024\n'
    '_EXPORTED_JSON_MAX_BYTES = 8 * 1024 * 1024\n'
    '_POST_ARCHIVE_PRODUCTION_PATHS = (',
    "bounded constants",
)

old_read_json = '''def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Cycle1TransportStopVerificationError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise Cycle1TransportStopVerificationError(f"{field} root must be an object")
    return value
'''
new_read_json = '''def _read_bounded_bytes(path: Path, field: str, *, max_bytes: int) -> bytes:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise Cycle1TransportStopVerificationError(
            f"{field} bounded byte ceiling must be a positive integer"
        )
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        raise Cycle1TransportStopVerificationError(
            f"{field} must be readable bounded bytes"
        ) from exc
    if len(raw) > max_bytes:
        raise Cycle1TransportStopVerificationError(
            f"{field} exceeds bounded byte ceiling {max_bytes}"
        )
    return raw


def _read_json(path: Path, field: str) -> dict[str, Any]:
    raw = _read_bounded_bytes(
        path,
        field,
        max_bytes=_EXPORTED_JSON_MAX_BYTES,
    )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Cycle1TransportStopVerificationError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise Cycle1TransportStopVerificationError(f"{field} root must be an object")
    return value
'''
verifier = replace_once(verifier, old_read_json, new_read_json, "bounded JSON read")

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
    "portable qualification",
)

verifier = replace_once(
    verifier,
    '    metadata_bytes = record_path.read_bytes()\n',
    '    metadata_bytes = _read_bounded_bytes(\n'
    '        record_path,\n'
    '        "retained completed record metadata",\n'
    '        max_bytes=_RETAINED_METADATA_MAX_BYTES,\n'
    '    )\n',
    "bounded metadata witness",
)

qualification_anchor = '''    qualification = authenticate_in625_network_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=EXPECTED_MISSION_SHA256,
        policy_path=policy,
        source_config_path=source,
    )
    persisted = _read_json(output / STOP_PATH, "cycle-1 transport stop")
'''
qualification_replacement = '''    qualification = authenticate_in625_network_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=EXPECTED_MISSION_SHA256,
        policy_path=policy,
        source_config_path=source,
    )
    persisted_qualification = _read_json(
        output / "standing-network-policy-qualification.json",
        "standing network policy qualification",
    )
    _require(
        _portable_qualification(
            persisted_qualification,
            "persisted standing network policy qualification",
        )
        == _portable_qualification(
            qualification,
            "reconstructed standing network policy qualification",
        ),
        "persisted standing network policy qualification differs from reconstructed authority",
    )
    persisted = _read_json(output / STOP_PATH, "cycle-1 transport stop")
'''
verifier = replace_once(
    verifier,
    qualification_anchor,
    qualification_replacement,
    "qualification replay",
)

archive_identity_anchor = '''    _require(
        isinstance(archive_name, str) and archive_name,
        "source archive identity is invalid",
    )
    _require(
        not (output / archive_name).exists(),
'''
archive_identity_replacement = '''    _require(
        isinstance(archive_name, str) and archive_name,
        "source archive identity is invalid",
    )
    files = zenodo.get("files")
    _require(isinstance(files, Mapping), "source config file bindings are invalid")
    readme_rule = files.get(readme_name)
    _require(isinstance(readme_rule, Mapping), "source README file binding is invalid")
    readme_size = readme_rule.get("size_bytes")
    _require(
        isinstance(readme_size, int)
        and not isinstance(readme_size, bool)
        and readme_size > 0,
        "source README size binding is invalid",
    )
    _require(
        not (output / archive_name).exists(),
'''
verifier = replace_once(
    verifier,
    archive_identity_anchor,
    archive_identity_replacement,
    "README size binding",
)

verifier = replace_once(
    verifier,
    '        readme_bytes = readme_path.read_bytes()\n',
    '        readme_bytes = _read_bounded_bytes(\n'
    '            readme_path,\n'
    '            "retained completed README",\n'
    '            max_bytes=readme_size,\n'
    '        )\n',
    "bounded README witness",
)
VERIFIER.write_text(verifier, encoding="utf-8")


tests = TESTS.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    '''    qualification = _qualification()
    prior: dict[str, str] = {}
''',
    '''    qualification = _qualification()
    (output / "standing-network-policy-qualification.json").write_text(
        json.dumps(qualification, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    prior: dict[str, str] = {}
''',
    "persist qualification fixture",
)

new_tests = r'''


def test_verifier_rejects_forged_persisted_policy_qualification(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(path.read_text(encoding="utf-8"))
    qualification["unrestricted_search_authorized"] = True
    path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="qualification differs from reconstructed authority",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_verifier_requires_retained_policy_qualification(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    (output / "standing-network-policy-qualification.json").unlink()

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="standing network policy qualification must be readable bounded bytes",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_readme_stop_bounds_retained_metadata_before_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    monkeypatch.setattr(stop_verifier, "_RETAINED_METADATA_MAX_BYTES", 64)

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="retained completed record metadata exceeds bounded byte ceiling 64",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_archive_stop_bounds_retained_readme_before_validation(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    readme_size = source["zenodo"]["files"][README_NAME]["size_bytes"]
    (output / README_NAME).write_bytes(b"x" * (readme_size + 1))

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match=f"retained completed README exceeds bounded byte ceiling {readme_size}",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
'''
if "test_verifier_rejects_forged_persisted_policy_qualification" in tests:
    raise SystemExit("final review hardening tests already present")
tests = tests.rstrip() + new_tests + "\n"
TESTS.write_text(tests, encoding="utf-8")
