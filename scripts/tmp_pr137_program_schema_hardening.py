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
    'PROGRAM_SCHEMA_VERSION = "1.0"\n',
    'PROGRAM_SCHEMA_VERSION = "1.1"\n',
    "program-schema-version",
)
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "def test_program_shape_change_uses_schema_1_1" not in tests:
    tests += r'''


def test_program_shape_change_uses_schema_1_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(_mission()), encoding="utf-8")
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    program = build_research_program(mission_path, repository_root=tmp_path)
    assert program["schema_version"] == "1.1"
    assert "source_trust_policy_pins" in program
'''
TESTS.write_text(tests, encoding="utf-8")
