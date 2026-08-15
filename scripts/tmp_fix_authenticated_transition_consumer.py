from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_transition_consumer.py")
TESTS = Path("tests/test_authenticated_transition_consumer.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '"The completed result tests the target proposition without itself granting scientific authority.",',
        '''(
            "The completed result was introduced to test this target; execution success alone "
            "does not establish scientific support, contradiction, or falsification."
        ),''',
        "tests-edge-rationale",
    )
    SOURCE.write_text(source, encoding="utf-8")

    tests = TESTS.read_text(encoding="utf-8")
    tests = replace_once(
        tests,
        'match="result_artifact_snapshots\\[0\\] checksum",',
        'match=r"result_artifact_snapshots\\[0\\] checksum",',
        "raw-regex",
    )
    TESTS.write_text(tests, encoding="utf-8")


if __name__ == "__main__":
    main()
