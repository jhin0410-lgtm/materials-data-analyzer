from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/research_program.py")
TESTS = Path("tests/test_research_program_source_trust_policy_pins.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")
text = replace_once(
    text,
    'MISSION_SCHEMA_VERSION = "1.0"\n',
    'MISSION_SCHEMA_VERSION = "1.1"\nLEGACY_MISSION_SCHEMA_VERSION = "1.0"\n',
    "mission-version-constants",
)
text = replace_once(
    text,
    '''    if mission["schema_version"] != MISSION_SCHEMA_VERSION:
        raise ResearchProgramError(
            f"unsupported mission schema_version: {mission['schema_version']!r}"
        )

    policy = _require_exact_keys(
''',
    '''    mission_schema_version = mission["schema_version"]
    if mission_schema_version not in {
        LEGACY_MISSION_SCHEMA_VERSION,
        MISSION_SCHEMA_VERSION,
    }:
        raise ResearchProgramError(
            f"unsupported mission schema_version: {mission_schema_version!r}"
        )
    if (
        "source_trust_policy_pins" in mission
        and mission_schema_version != MISSION_SCHEMA_VERSION
    ):
        raise ResearchProgramError(
            "source_trust_policy_pins requires mission schema_version 1.1"
        )

    policy = _require_exact_keys(
''',
    "mission-version-validation",
)
text = replace_once(
    text,
    '''        "schema_version": MISSION_SCHEMA_VERSION,
        "mission_id": _nonempty_text(mission["mission_id"], "mission_id"),
''',
    '''        "schema_version": mission_schema_version,
        "mission_id": _nonempty_text(mission["mission_id"], "mission_id"),
''',
    "preserve-input-version",
)
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
tests = tests.replace(
    '''def test_mission_normalizes_first_class_policy_pins() -> None:
    mission = _mission()
    mission["source_trust_policy_pins"] = [_pin()]
''',
    '''def test_mission_normalizes_first_class_policy_pins() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin()]
''',
)
for marker in [
    'test_policy_pin_rejects_uppercase_sha',
    'test_policy_pin_rejects_surrounding_policy_id_whitespace',
    'test_policy_pin_rejects_unknown_fields',
    'test_policy_pin_rejects_duplicate_policy_ids',
    'test_policy_pin_rejects_duplicate_policy_shas',
    'test_policy_pin_field_cannot_be_empty_when_explicitly_present',
    'test_program_exports_normalized_policy_pins_and_exact_mission_sha',
    'test_changing_policy_pin_changes_exact_mission_binding',
]:
    anchor = f'def {marker}'
    start = tests.index(anchor)
    mission_pos = tests.index('    mission = _mission()\n', start)
    insertion = mission_pos + len('    mission = _mission()\n')
    if tests[insertion:insertion + len('    mission["schema_version"] = "1.1"\n')] != '    mission["schema_version"] = "1.1"\n':
        tests = tests[:insertion] + '    mission["schema_version"] = "1.1"\n' + tests[insertion:]

if "def test_legacy_schema_cannot_smuggle_policy_pins" not in tests:
    tests += r'''


def test_legacy_schema_cannot_smuggle_policy_pins() -> None:
    mission = _mission()
    mission["source_trust_policy_pins"] = [_pin()]
    with pytest.raises(ResearchProgramError, match="requires mission schema_version 1.1"):
        validate_research_mission(mission)


def test_current_schema_without_policy_pins_remains_valid() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    normalized = validate_research_mission(mission)
    assert normalized["schema_version"] == "1.1"
    assert "source_trust_policy_pins" not in normalized
'''
TESTS.write_text(tests, encoding="utf-8")
