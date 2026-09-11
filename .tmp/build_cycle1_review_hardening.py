from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, addition: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if marker in text:
        raise SystemExit(f"{path}: marker already present: {marker}")
    file_path.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n", encoding="utf-8")


STOP = "src/materials_data_analyzer/research_loop/autonomous_production_cycle1_transport_stop.py"
VERIFIER = "src/materials_data_analyzer/research_loop/autonomous_production_cycle1_transport_stop_verifier.py"
WORKFLOW = ".github/workflows/cycle1-zenodo-transport-contract.yml"
STOP_TEST = "tests/test_autonomous_production_cycle1_transport_stop.py"
VERIFIER_TEST = "tests/test_autonomous_production_cycle1_transport_stop_verifier.py"
ROUTE_TEST = "tests/test_cycle1_exact_zenodo_route_hardening.py"

replace_once(
    STOP,
    '''def _text(value: object, field: str) -> str:\n    if not isinstance(value, str) or not value or value != value.strip():\n        raise Cycle1TransportStopError(f"{field} must be non-empty trimmed text")\n    return value\n\n\ndef _exact_https_zenodo_url''',
    '''def _text(value: object, field: str) -> str:\n    if not isinstance(value, str) or not value or value != value.strip():\n        raise Cycle1TransportStopError(f"{field} must be non-empty trimmed text")\n    return value\n\n\ndef _exact_int(value: object, expected: int, field: str) -> int:\n    if isinstance(value, bool) or not isinstance(value, int) or value != expected:\n        raise Cycle1TransportStopError(f"{field} must be exact integer {expected}")\n    return value\n\n\ndef _exact_https_zenodo_url''',
)
replace_once(
    STOP,
    '''    if (\n        isinstance(maximum_network_requests_per_cycle, bool)\n        or maximum_network_requests_per_cycle != 3\n    ):''',
    '''    if (\n        isinstance(maximum_network_requests_per_cycle, bool)\n        or not isinstance(maximum_network_requests_per_cycle, int)\n        or maximum_network_requests_per_cycle != 3\n    ):''',
)
replace_once(
    STOP,
    '''    if (\n        stop.get("schema_version") != SCHEMA_VERSION\n        or stop.get("status") != "stopped"\n        or stop.get("reason_code") != _REASON_CODE\n        or stop.get("cycle_index") != 1\n    ):\n        raise Cycle1TransportStopError("cycle-1 transport stop identity drifted")''',
    '''    if (\n        stop.get("schema_version") != SCHEMA_VERSION\n        or stop.get("status") != "stopped"\n        or stop.get("reason_code") != _REASON_CODE\n    ):\n        raise Cycle1TransportStopError("cycle-1 transport stop identity drifted")\n    _exact_int(stop.get("cycle_index"), 1, "cycle_index")''',
)
replace_once(
    STOP,
    '''    if stop.get("request_ordinal") != _STAGE_ORDINALS[stage]:\n        raise Cycle1TransportStopError("cycle-1 transport request ordinal drifted")''',
    '''    _exact_int(\n        stop.get("request_ordinal"),\n        _STAGE_ORDINALS[stage],\n        "request_ordinal",\n    )''',
)
replace_once(
    STOP,
    '''    if (\n        authority.get("network_policy_id") != POLICY_ID\n        or authority.get("provider") != PROVIDER\n        or authority.get("record_id") != RECORD_ID\n        or authority.get("allowed_hosts") != [ALLOWED_HOST]\n        or authority.get("maximum_network_requests_per_cycle") != 3\n    ):\n        raise Cycle1TransportStopError("cycle-1 transport authority widened or drifted")''',
    '''    if (\n        authority.get("network_policy_id") != POLICY_ID\n        or authority.get("provider") != PROVIDER\n        or authority.get("allowed_hosts") != [ALLOWED_HOST]\n    ):\n        raise Cycle1TransportStopError("cycle-1 transport authority widened or drifted")\n    _exact_int(authority.get("record_id"), RECORD_ID, "authority.record_id")\n    _exact_int(\n        authority.get("maximum_network_requests_per_cycle"),\n        3,\n        "authority.maximum_network_requests_per_cycle",\n    )''',
)

replace_once(
    VERIFIER,
    '''from .in625_zenodo_live_evidence import (\n    In625ZenodoLiveEvidenceError,\n    validate_verified_in625_zenodo_metadata,\n)''',
    '''from .in625_zenodo_live_evidence import (\n    In625ZenodoLiveEvidenceError,\n    build_verified_in625_zenodo_readme_manifest,\n    validate_verified_in625_zenodo_metadata,\n)''',
)
replace_once(
    VERIFIER,
    '''class Cycle1TransportStopVerificationError(ResearchLoopError):\n    """Raised when a cycle-1 transport stop does not match current trusted authority."""\n\n\ndef _read_json(path: Path, field: str) -> dict[str, Any]:\n    try:\n        value = json.loads(path.read_text(encoding="utf-8"))\n    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:\n        raise Cycle1TransportStopVerificationError(\n            f"{field} must be valid UTF-8 JSON"\n        ) from exc''',
    '''class Cycle1TransportStopVerificationError(ResearchLoopError):\n    """Raised when a cycle-1 transport stop does not match current trusted authority."""\n\n\ndef _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:\n    result: dict[str, Any] = {}\n    for key, value in pairs:\n        if key in result:\n            raise Cycle1TransportStopVerificationError(\n                f"duplicate JSON key is not allowed: {key}"\n            )\n        result[key] = value\n    return result\n\n\ndef _read_json(path: Path, field: str) -> dict[str, Any]:\n    try:\n        value = json.loads(\n            path.read_text(encoding="utf-8"),\n            object_pairs_hook=_reject_duplicate_pairs,\n        )\n    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:\n        raise Cycle1TransportStopVerificationError(\n            f"{field} must be valid UTF-8 JSON"\n        ) from exc''',
)
replace_once(
    VERIFIER,
    '''        readme_path = output / readme_name\n        _require(readme_path.is_file(), "archive stop lost completed README bytes")\n        readme_bytes = readme_path.read_bytes()\n        _require(\n            prior.get("readme_sha256") == hashlib.sha256(readme_bytes).hexdigest(),\n            "archive stop prior README hash differs from persisted completed README",\n        )\n        authorization = _read_json(authorization_path, "network authorization")''',
    '''        readme_path = output / readme_name\n        _require(readme_path.is_file(), "archive stop lost completed README bytes")\n        readme_bytes = readme_path.read_bytes()\n        _require(\n            prior.get("readme_sha256") == hashlib.sha256(readme_bytes).hexdigest(),\n            "archive stop prior README hash differs from persisted completed README",\n        )\n        persisted_source_manifest = _read_json(\n            source_manifest_path,\n            "source README manifest",\n        )\n        try:\n            reconstructed_source_manifest = build_verified_in625_zenodo_readme_manifest(\n                config=source_config,\n                metadata_bytes=metadata_bytes,\n                readme_bytes=readme_bytes,\n            )\n        except In625ZenodoLiveEvidenceError as exc:\n            raise Cycle1TransportStopVerificationError(\n                "archive stop source README manifest failed authoritative reconstruction"\n            ) from exc\n        _require(\n            persisted_source_manifest == reconstructed_source_manifest,\n            "archive stop source README manifest differs from authoritative reconstruction",\n        )\n        _require(\n            not (output / archive_name).exists(),\n            "archive transport stop may not retain completed archive bytes",\n        )\n        _require(\n            not (output / "network-acquisition-receipt.json").exists(),\n            "archive transport stop may not retain a completed network acquisition receipt",\n        )\n        authorization = _read_json(authorization_path, "network authorization")''',
)

needle = '      - "src/materials_data_analyzer/research_loop/in625_zenodo_live_evidence.py"\n'
workflow_text = Path(WORKFLOW).read_text(encoding="utf-8")
if workflow_text.count(needle) != 2:
    raise SystemExit("workflow: expected live-evidence dependency exactly twice")
workflow_text = workflow_text.replace(
    needle,
    needle + '      - "src/materials_data_analyzer/research_loop/zenodo_evidence_acquisition.py"\n',
)
Path(WORKFLOW).write_text(workflow_text, encoding="utf-8")

append_once(
    STOP_TEST,
    "test_authenticator_rejects_non_integer_identity_even_when_rehashed",
    '''@pytest.mark.parametrize(\n    ("container", "field", "value"),\n    [\n        ("root", "cycle_index", True),\n        ("root", "cycle_index", 1.0),\n        ("root", "request_ordinal", True),\n        ("root", "request_ordinal", 1.0),\n        ("authority", "record_id", True),\n        ("authority", "record_id", 20503603.0),\n        ("authority", "maximum_network_requests_per_cycle", True),\n        ("authority", "maximum_network_requests_per_cycle", 3.0),\n    ],\n)\ndef test_authenticator_rejects_non_integer_identity_even_when_rehashed(\n    container: str,\n    field: str,\n    value: object,\n) -> None:\n    forged = copy.deepcopy(_stop("zenodo_record_metadata"))\n    target = forged if container == "root" else forged["authority"]\n    assert isinstance(target, dict)\n    target[field] = value\n    unsigned = dict(forged)\n    unsigned.pop("stop_sha256_without_self_field")\n    forged["stop_sha256_without_self_field"] = stop_contract._canonical_sha(unsigned)\n\n    with pytest.raises(Cycle1TransportStopError, match="must be exact integer"):\n        authenticate_cycle1_transport_stop(forged)\n\n\ndef test_builder_rejects_float_request_budget() -> None:\n    with pytest.raises(Cycle1TransportStopError, match="exact three-request"):\n        build_cycle1_transport_stop(\n            mission_sha256="a" * 64,\n            network_policy_sha256="b" * 64,\n            source_config_sha256="c" * 64,\n            maximum_network_requests_per_cycle=3.0,  # type: ignore[arg-type]\n            stage="zenodo_record_metadata",\n            requested_url="https://zenodo.org/api/records/20503603",\n            transport_error_class="PublicAcquisitionTransportError",\n            transport_error_detail="HTTP acquisition failed: 504",\n        )''',
)

replace_once(
    VERIFIER_TEST,
    '''        (output / "source-readme-manifest.json").write_text("{}\\n", encoding="utf-8")''',
    '''        (output / "source-readme-manifest.json").write_text(\n            json.dumps({"fixture": "trusted-source-manifest"}) + "\\n",\n            encoding="utf-8",\n        )''',
)
replace_once(
    VERIFIER_TEST,
    '''def test_verifier_reconstructs_current_authority_for_metadata_stop''',
    '''def _patch_archive_manifest_builder(monkeypatch: pytest.MonkeyPatch) -> None:\n    monkeypatch.setattr(\n        stop_verifier,\n        "build_verified_in625_zenodo_readme_manifest",\n        lambda **_kwargs: {"fixture": "trusted-source-manifest"},\n    )\n\n\ndef test_verifier_reconstructs_current_authority_for_metadata_stop''',
)
for signature in (
    '''    _write_stop(output, stage="zenodo_archive")\n\n    monkeypatch.setattr(\n        stop_verifier,\n        "validate_in625_archive_network_authorization",''',
    '''    stop = _write_stop(output, stage="zenodo_archive")\n    stop["requested_url"] = README_URL''',
    '''    _write_stop(output, stage="zenodo_archive")\n\n    def reject(*_args: object, **_kwargs: object) -> dict[str, object]:''',
):
    if signature not in Path(VERIFIER_TEST).read_text(encoding="utf-8"):
        raise SystemExit(f"verifier test expected signature missing: {signature[:60]}")

replace_once(
    VERIFIER_TEST,
    '''    _write_stop(output, stage="zenodo_archive")\n\n    monkeypatch.setattr(\n        stop_verifier,\n        "validate_in625_archive_network_authorization",''',
    '''    _write_stop(output, stage="zenodo_archive")\n    _patch_archive_manifest_builder(monkeypatch)\n\n    monkeypatch.setattr(\n        stop_verifier,\n        "validate_in625_archive_network_authorization",''',
)
replace_once(
    VERIFIER_TEST,
    '''    stop = _write_stop(output, stage="zenodo_archive")\n    stop["requested_url"] = README_URL''',
    '''    stop = _write_stop(output, stage="zenodo_archive")\n    _patch_archive_manifest_builder(monkeypatch)\n    stop["requested_url"] = README_URL''',
)
replace_once(
    VERIFIER_TEST,
    '''    _write_stop(output, stage="zenodo_archive")\n\n    def reject(*_args: object, **_kwargs: object) -> dict[str, object]:''',
    '''    _write_stop(output, stage="zenodo_archive")\n    _patch_archive_manifest_builder(monkeypatch)\n\n    def reject(*_args: object, **_kwargs: object) -> dict[str, object]:''',
)
append_once(
    VERIFIER_TEST,
    "test_verifier_rejects_duplicate_keys_in_persisted_stop_json",
    '''def test_verifier_rejects_duplicate_keys_in_persisted_stop_json(tmp_path: Path) -> None:\n    output = tmp_path / "stop"\n    stop = _write_stop(output)\n    raw = json.dumps(stop, separators=(",", ":"))\n    raw = raw.replace("{", '{"scientific_status_changed":true,', 1)\n    (output / "cycle-1-transport-stop.json").write_text(raw, encoding="utf-8")\n\n    with pytest.raises(\n        Cycle1TransportStopVerificationError,\n        match="duplicate JSON key",\n    ):\n        verify_cycle1_transport_stop(\n            repository_root=REPOSITORY_ROOT,\n            output_root=output,\n        )\n\n\ndef test_archive_stop_rejects_forged_retained_source_manifest(\n    monkeypatch: pytest.MonkeyPatch,\n    tmp_path: Path,\n) -> None:\n    output = tmp_path / "stop"\n    _write_stop(output, stage="zenodo_archive")\n    _patch_archive_manifest_builder(monkeypatch)\n    (output / "source-readme-manifest.json").write_text(\n        json.dumps({"fixture": "forged-source-manifest"}) + "\\n",\n        encoding="utf-8",\n    )\n\n    with pytest.raises(\n        Cycle1TransportStopVerificationError,\n        match="source README manifest differs",\n    ):\n        verify_cycle1_transport_stop(\n            repository_root=REPOSITORY_ROOT,\n            output_root=output,\n        )\n\n\n@pytest.mark.parametrize(\n    ("artifact_name", "error_match"),\n    [\n        ("Dataset.zip", "completed archive bytes"),\n        ("network-acquisition-receipt.json", "completed network acquisition receipt"),\n    ],\n)\ndef test_archive_stop_rejects_impossible_completed_archive_artifacts(\n    monkeypatch: pytest.MonkeyPatch,\n    tmp_path: Path,\n    artifact_name: str,\n    error_match: str,\n) -> None:\n    output = tmp_path / "stop"\n    _write_stop(output, stage="zenodo_archive")\n    _patch_archive_manifest_builder(monkeypatch)\n    (output / artifact_name).write_bytes(b"impossible completed artifact")\n\n    with pytest.raises(Cycle1TransportStopVerificationError, match=error_match):\n        verify_cycle1_transport_stop(\n            repository_root=REPOSITORY_ROOT,\n            output_root=output,\n        )''',
)

append_once(
    ROUTE_TEST,
    "test_cycle1_workflow_tracks_metadata_normalizer_dependencies",
    '''def test_cycle1_workflow_tracks_metadata_normalizer_dependencies() -> None:\n    workflow = (\n        ROOT / ".github/workflows/cycle1-zenodo-transport-contract.yml"\n    ).read_text(encoding="utf-8")\n    for dependency in (\n        "src/materials_data_analyzer/research_loop/in625_zenodo_live_evidence.py",\n        "src/materials_data_analyzer/research_loop/zenodo_evidence_acquisition.py",\n    ):\n        assert workflow.count(f'- "{dependency}"') == 2''',
)
