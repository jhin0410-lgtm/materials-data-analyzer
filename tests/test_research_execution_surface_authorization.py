from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_RAW_TYPED_EXECUTORS = (
    "execute_nasa_audit_action",
    "execute_nasa_target_reference_action",
    "execute_nasa_protocol_stratification_action",
    "execute_nasa_external_data_requirement_action",
)


def _executable_python_surfaces() -> list[Path]:
    scripts = sorted((ROOT / "scripts").glob("*.py"))
    package = ROOT / "src/materials_data_analyzer"
    clis = sorted(package.rglob("*cli.py"))
    return [*scripts, *clis]


def test_python_executable_surfaces_do_not_call_raw_nasa_executors() -> None:
    violations: list[str] = []
    for path in _executable_python_surfaces():
        source = path.read_text(encoding="utf-8")
        for executor in _RAW_TYPED_EXECUTORS:
            if executor in source:
                violations.append(f"{path.relative_to(ROOT)}: {executor}")

    assert violations == [], (
        "NASA typed actions must be reached through the common authorization "
        "boundary from executable Python surfaces; raw executor references found: "
        + ", ".join(violations)
    )
