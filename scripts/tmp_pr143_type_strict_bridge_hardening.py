from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/mission_source_trust_bridge.py")
TESTS = Path("tests/test_mission_source_trust_bridge.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")

old = '''def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise MissionSourceTrustBridgeError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _normalized_mission(mission_bytes: bytes) -> dict[str, Any]:
'''
new = '''def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise MissionSourceTrustBridgeError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _same_json_value(left: object, right: object) -> bool:
    """Compare JSON-like values without Python bool/int equality aliasing."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        assert isinstance(right, dict)
        if set(left) != set(right):
            return False
        return all(_same_json_value(left[key], right[key]) for key in left)
    if isinstance(left, list):
        assert isinstance(right, list)
        return len(left) == len(right) and all(
            _same_json_value(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _require_exact_bytes(value: object, field: str) -> bytes:
    if not isinstance(value, bytes):
        raise MissionSourceTrustBridgeError(f"{field} must be exact bytes")
    return value


def _normalized_mission(mission_bytes: bytes) -> dict[str, Any]:
'''
text = replace_once(text, old, new, "type-strict-helpers")

old = '''def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
'''
new = '''def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    raw = _require_exact_bytes(raw, field)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
'''
text = replace_once(text, old, new, "json-byte-boundary")

old = '''def _validate_program_projection(
    program_state: Mapping[str, Any],
    *,
    normalized_mission: Mapping[str, Any],
    expected_mission_sha256: str,
) -> None:
    if program_state.get("schema_version") != _SUPPORTED_PROGRAM_SCHEMA_VERSION:
'''
new = '''def _validate_program_projection(
    program_state: Mapping[str, Any],
    *,
    normalized_mission: Mapping[str, Any],
    expected_mission_sha256: str,
) -> None:
    if not isinstance(program_state, Mapping):
        raise MissionSourceTrustBridgeError("program_state must be an object")
    if program_state.get("schema_version") != _SUPPORTED_PROGRAM_SCHEMA_VERSION:
'''
text = replace_once(text, old, new, "program-state-type")

old = '''    projected_mission = program_state.get("mission")
    if not isinstance(projected_mission, dict) or projected_mission != normalized_mission:
        raise MissionSourceTrustBridgeError(
            "program_state normalized mission does not match the authenticated mission bytes"
        )

    expected_pins = normalized_mission["source_trust_policy_pins"]
    projected_pins = program_state.get("source_trust_policy_pins")
    if not isinstance(projected_pins, list) or projected_pins != expected_pins:
'''
new = '''    projected_mission = program_state.get("mission")
    if not isinstance(projected_mission, dict) or not _same_json_value(
        projected_mission,
        normalized_mission,
    ):
        raise MissionSourceTrustBridgeError(
            "program_state normalized mission does not match the authenticated mission bytes"
        )

    expected_pins = normalized_mission["source_trust_policy_pins"]
    projected_pins = program_state.get("source_trust_policy_pins")
    if not isinstance(projected_pins, list) or not _same_json_value(
        projected_pins,
        expected_pins,
    ):
'''
text = replace_once(text, old, new, "type-strict-projection")

old = '''    """Qualify an acquisition record only through a pin in exact mission-rooted bytes."""
    expected_mission_sha = _sha256_text(
'''
new = '''    """Qualify an acquisition record only through a pin in exact mission-rooted bytes."""
    mission_bytes = _require_exact_bytes(mission_bytes, "mission_bytes")
    evidence_bytes = _require_exact_bytes(evidence_bytes, "evidence_bytes")
    acquisition_manifest_bytes = _require_exact_bytes(
        acquisition_manifest_bytes,
        "acquisition_manifest_bytes",
    )
    acquisition_declaration_bytes = _require_exact_bytes(
        acquisition_declaration_bytes,
        "acquisition_declaration_bytes",
    )
    source_trust_policy_bytes = _require_exact_bytes(
        source_trust_policy_bytes,
        "source_trust_policy_bytes",
    )
    expected_mission_sha = _sha256_text(
'''
text = replace_once(text, old, new, "public-byte-boundary")
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "test_exact_byte_inputs_fail_closed_with_bridge_error" not in tests:
    tests += r'''


@pytest.mark.parametrize(
    "field",
    [
        "mission_bytes",
        "evidence_bytes",
        "acquisition_manifest_bytes",
        "acquisition_declaration_bytes",
        "source_trust_policy_bytes",
    ],
)
def test_exact_byte_inputs_fail_closed_with_bridge_error(
    tmp_path: Path,
    field: str,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    values: dict[str, object] = {
        "mission_bytes": mission,
        "expected_mission_sha256": hashlib.sha256(mission).hexdigest(),
        "program_state": program,
        "policy_id": POLICY_ID,
        "evidence_bytes": evidence,
        "acquisition_manifest_bytes": manifest,
        "acquisition_declaration_bytes": declaration,
        "source_trust_policy_bytes": policy,
    }
    values[field] = "not-bytes"
    with pytest.raises(
        MissionSourceTrustBridgeError,
        match=rf"{field} must be exact bytes",
    ):
        qualify_acquisition_record_under_expected_mission_policy(**values)  # type: ignore[arg-type]


def test_non_mapping_program_state_fails_closed_with_bridge_error(tmp_path: Path) -> None:
    mission, _, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="program_state must be an object"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state="not-an-object",  # type: ignore[arg-type]
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_program_projection_comparison_is_type_strict_for_bool_int_alias(
    tmp_path: Path,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    mutated = copy.deepcopy(program)
    # Exact mission has enabled=False. Python equality treats False == 0, so a normal
    # dict comparison would accept this type substitution even though JSON semantics differ.
    mutated["mission"]["workstreams"][0]["enabled"] = 0
    with pytest.raises(MissionSourceTrustBridgeError, match="normalized mission"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=mutated,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )
'''
TESTS.write_text(tests, encoding="utf-8")
