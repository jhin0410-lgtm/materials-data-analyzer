from pathlib import Path

VERIFIER = Path("src/materials_data_analyzer/research_loop/autonomous_production_cycle1_transport_stop_verifier.py")
TESTS = Path("tests/test_autonomous_production_cycle1_transport_stop_verifier.py")

text = VERIFIER.read_text(encoding="utf-8")

anchor = '''STOP_PATH = "cycle-1-transport-stop.json"\nZENODO_HOST = "zenodo.org"\n_POST_ARCHIVE_PRODUCTION_PATHS = (\n'''
replacement = '''STOP_PATH = "cycle-1-transport-stop.json"\nZENODO_HOST = "zenodo.org"\n_ZENODO_CONTROL_PLANE_MAX_BYTES = 8 * 1024 * 1024\n_PERSISTED_JSON_MAX_BYTES = _ZENODO_CONTROL_PLANE_MAX_BYTES\n_POST_ARCHIVE_PRODUCTION_PATHS = (\n'''
if text.count(anchor) != 1:
    raise SystemExit("constant anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''def _read_json(path: Path, field: str) -> dict[str, Any]:\n    try:\n        value = json.loads(\n            path.read_text(encoding="utf-8"),\n            object_pairs_hook=_reject_duplicate_pairs,\n        )\n    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:\n        raise Cycle1TransportStopVerificationError(\n            f"{field} must be valid UTF-8 JSON"\n        ) from exc\n    if not isinstance(value, dict):\n        raise Cycle1TransportStopVerificationError(f"{field} root must be an object")\n    return value\n\n\n'''
replacement = '''def _read_bounded_bytes(\n    path: Path,\n    field: str,\n    *,\n    maximum_bytes: int,\n) -> bytes:\n    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or maximum_bytes <= 0:\n        raise Cycle1TransportStopVerificationError(f"{field} byte bound is invalid")\n    try:\n        if not path.is_file():\n            raise Cycle1TransportStopVerificationError(f"{field} must be a regular file")\n        observed_size = path.stat().st_size\n    except OSError as exc:\n        raise Cycle1TransportStopVerificationError(f"{field} could not be inspected") from exc\n    if observed_size > maximum_bytes:\n        raise Cycle1TransportStopVerificationError(\n            f"{field} exceeds {maximum_bytes}-byte verification bound"\n        )\n    try:\n        with path.open("rb") as handle:\n            value = handle.read(maximum_bytes + 1)\n    except OSError as exc:\n        raise Cycle1TransportStopVerificationError(f"{field} could not be read") from exc\n    if len(value) > maximum_bytes:\n        raise Cycle1TransportStopVerificationError(\n            f"{field} exceeds {maximum_bytes}-byte verification bound"\n        )\n    return value\n\n\ndef _read_json(path: Path, field: str) -> dict[str, Any]:\n    raw = _read_bounded_bytes(\n        path,\n        field,\n        maximum_bytes=_PERSISTED_JSON_MAX_BYTES,\n    )\n    try:\n        value = json.loads(\n            raw.decode("utf-8"),\n            object_pairs_hook=_reject_duplicate_pairs,\n        )\n    except (UnicodeDecodeError, json.JSONDecodeError) as exc:\n        raise Cycle1TransportStopVerificationError(\n            f"{field} must be valid UTF-8 JSON"\n        ) from exc\n    if not isinstance(value, dict):\n        raise Cycle1TransportStopVerificationError(f"{field} root must be an object")\n    return value\n\n\n'''
if text.count(anchor) != 1:
    raise SystemExit("json reader anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''    metadata_bytes = record_path.read_bytes()\n    try:\n        metadata_witness = validate_verified_in625_zenodo_metadata(\n'''
replacement = '''    metadata_bytes = _read_bounded_bytes(\n        record_path,\n        "retained completed record metadata",\n        maximum_bytes=_ZENODO_CONTROL_PLANE_MAX_BYTES,\n    )\n    try:\n        metadata_witness = validate_verified_in625_zenodo_metadata(\n'''
if text.count(anchor) != 1:
    raise SystemExit("metadata read anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''    qualification = authenticate_in625_network_policy(\n        repository_root=root,\n        mission_path=mission,\n        expected_mission_sha256=EXPECTED_MISSION_SHA256,\n        policy_path=policy,\n        source_config_path=source,\n    )\n    persisted = _read_json(output / STOP_PATH, "cycle-1 transport stop")\n'''
replacement = '''    qualification = authenticate_in625_network_policy(\n        repository_root=root,\n        mission_path=mission,\n        expected_mission_sha256=EXPECTED_MISSION_SHA256,\n        policy_path=policy,\n        source_config_path=source,\n    )\n    persisted_qualification = _read_json(\n        output / "standing-network-policy-qualification.json",\n        "standing network policy qualification",\n    )\n    _require(\n        persisted_qualification == qualification,\n        "retained standing network policy qualification differs from reconstructed authority",\n    )\n    persisted = _read_json(output / STOP_PATH, "cycle-1 transport stop")\n'''
if text.count(anchor) != 1:
    raise SystemExit("qualification anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''    _require(\n        isinstance(archive_name, str) and archive_name,\n        "source archive identity is invalid",\n    )\n    _require(\n        not (output / archive_name).exists(),\n'''
replacement = '''    _require(\n        isinstance(archive_name, str) and archive_name,\n        "source archive identity is invalid",\n    )\n    file_rules = zenodo.get("files")\n    _require(isinstance(file_rules, Mapping), "source config file rules are missing")\n    readme_rule = file_rules.get(readme_name)\n    _require(isinstance(readme_rule, Mapping), "source README rule is missing")\n    readme_max_bytes = readme_rule.get("size_bytes")\n    _require(\n        isinstance(readme_max_bytes, int)\n        and not isinstance(readme_max_bytes, bool)\n        and readme_max_bytes > 0,\n        "source README size bound is invalid",\n    )\n    _require(\n        not (output / archive_name).exists(),\n'''
if text.count(anchor) != 1:
    raise SystemExit("readme bound anchor drifted")
text = text.replace(anchor, replacement)

anchor = '''        readme_path = output / readme_name\n        _require(readme_path.is_file(), "archive stop lost completed README bytes")\n        readme_bytes = readme_path.read_bytes()\n        _require(\n'''
replacement = '''        readme_path = output / readme_name\n        _require(readme_path.is_file(), "archive stop lost completed README bytes")\n        readme_bytes = _read_bounded_bytes(\n            readme_path,\n            "retained completed README",\n            maximum_bytes=readme_max_bytes,\n        )\n        _require(\n'''
if text.count(anchor) != 1:
    raise SystemExit("README read anchor drifted")
text = text.replace(anchor, replacement)
VERIFIER.write_text(text, encoding="utf-8")

test_text = TESTS.read_text(encoding="utf-8")
anchor = '''def _write_stop(output: Path, *, stage: str = "zenodo_record_metadata") -> dict[str, object]:\n    output.mkdir(parents=True)\n    qualification = _qualification()\n    prior: dict[str, str] = {}\n'''
replacement = '''def _write_stop(output: Path, *, stage: str = "zenodo_record_metadata") -> dict[str, object]:\n    output.mkdir(parents=True)\n    qualification = _qualification()\n    (output / "standing-network-policy-qualification.json").write_text(\n        json.dumps(qualification, sort_keys=True) + "\\n",\n        encoding="utf-8",\n    )\n    prior: dict[str, str] = {}\n'''
if test_text.count(anchor) != 1:
    raise SystemExit("fixture qualification anchor drifted")
test_text = test_text.replace(anchor, replacement)

append = r'''


def test_verifier_rejects_forged_retained_policy_qualification(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    qualification_path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["unrestricted_search_authorized"] = True
    qualification_path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="qualification differs from reconstructed authority",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_readme_stop_rejects_oversized_retained_metadata_before_parse(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    with (output / "record.json").open("wb") as handle:
        handle.truncate(stop_verifier._ZENODO_CONTROL_PLANE_MAX_BYTES + 1)

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="record metadata exceeds .* verification bound",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_archive_stop_rejects_oversized_retained_readme_before_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    maximum = source["zenodo"]["files"][README_NAME]["size_bytes"]
    assert isinstance(maximum, int) and not isinstance(maximum, bool)
    with (output / README_NAME).open("wb") as handle:
        handle.truncate(maximum + 1)

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="completed README exceeds .* verification bound",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
'''
marker = "def test_verifier_rejects_forged_retained_policy_qualification("
if marker in test_text:
    raise SystemExit("retained authority regressions already present")
TESTS.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")
