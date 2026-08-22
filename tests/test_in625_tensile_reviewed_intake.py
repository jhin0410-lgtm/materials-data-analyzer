from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from materials_data_analyzer.research_loop.in625_tensile_reviewed_intake import (
    In625TensileReviewedIntakeError,
    build_reviewed_in625_tensile_intake,
)

SHEETS = ["CM", "AM-AB-H", "AM-AB-V", "AM-SR-H", "AM-SR-V", "AM-ST-H", "AM-ST-V"]
HEADER = [
    "Time sec",
    "Extension mm",
    "Strain 1 %",
    "Load N",
    "Tensile stress MPa",
    "Cycle Count ",
    "Total Cycle Count ",
    "Repetitions Count ",
    "Segment ID ",
    "Marked Data ",
    "PIP Count ",
    "Tensile extension mm",
]


def _col(index: int) -> str:
    result = ""
    value = index + 1
    while value:
        value, rem = divmod(value - 1, 26)
        result = chr(ord("A") + rem) + result
    return result


def _inline_cell(row: int, col: int, value: str, *, formula: str | None = None) -> str:
    coordinate = f"{_col(col)}{row}"
    formula_xml = "" if formula is None else f"<f>{escape(formula)}</f>"
    return (
        f'<c r="{coordinate}" t="inlineStr">{formula_xml}'
        f"<is><t>{escape(value)}</t></is></c>"
    )


def _sheet_xml(*, sheet_name: str, header: list[str] | None = None, formula: bool = False) -> str:
    header = HEADER if header is None else header
    rows = [
        '<row r="1">' + _inline_cell(1, 0, "Specimen") + _inline_cell(1, 1, "1") + "</row>",
        '<row r="2">'
        + _inline_cell(2, 0, "Oznaka vzorca / Specimen")
        + _inline_cell(2, 1, f"{sheet_name}-1")
        + "</row>",
        '<row r="3">'
        + "".join(_inline_cell(3, index, value) for index, value in enumerate(header))
        + "</row>",
    ]
    data = ["0,00", "0,10", "0,20", "10,0", "100,0", "0", "0", "0", "644", "0", "0", "0,02"]
    data_cells = []
    for index, value in enumerate(data):
        data_cells.append(
            _inline_cell(4, index, value, formula="1+1" if formula and index == 4 else None)
        )
    rows.append('<row r="4">' + "".join(data_cells) + "</row>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="A1:L4"/><sheetData>' + "".join(rows) + "</sheetData></worksheet>"
    )


def _write_workbook(path: Path, *, changed_header: bool = False, formula: bool = False) -> bytes:
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    for index in range(1, 8):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append("</Types>")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(
            f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
            for index, name in enumerate(SHEETS, start=1)
        )
        + "</sheets></workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, 8)
        )
        + "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        for index, name in enumerate(SHEETS, start=1):
            header = list(HEADER)
            if changed_header and index == 1:
                header[4] = "Stress MPa"
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _sheet_xml(sheet_name=name, header=header, formula=formula and index == 1),
            )
    return path.read_bytes()


def _policy(workbook: bytes, readme: bytes) -> dict[str, object]:
    semantics = {
        "CM": ("conventional_manufacturing", "solution_annealed", None),
        "AM-AB-H": ("additive_manufacturing", "as_built", "horizontal"),
        "AM-AB-V": ("additive_manufacturing", "as_built", "vertical"),
        "AM-SR-H": ("additive_manufacturing", "stress_relief_annealed", "horizontal"),
        "AM-SR-V": ("additive_manufacturing", "stress_relief_annealed", "vertical"),
        "AM-ST-H": ("additive_manufacturing", "solution_annealed", "horizontal"),
        "AM-ST-V": ("additive_manufacturing", "solution_annealed", "vertical"),
    }
    return {
        "schema_version": "1.0",
        "source_id": "zenodo-20503603-in625-lpbf-publication-supplement",
        "source_archive_sha256": "0" * 64,
        "workbook": {
            "archive_member_path": "Dataset/Mechanical testing/Tensile tests/Tensile tests.xlsx",
            "sha256": hashlib.sha256(workbook).hexdigest(),
            "size_bytes": len(workbook),
        },
        "documentation": {
            "archive_member_path": "Dataset/Mechanical testing/Tensile tests/README-Tensile tests.txt",
            "sha256": hashlib.sha256(readme).hexdigest(),
            "size_bytes": len(readme),
            "encoding": "cp1250",
        },
        "reviewed_scope": {
            "material": "IN625",
            "experiment": "room_temperature_uniaxial_tensile_test",
            "standard_reference_text": "DIN50125 (Type E)",
            "parallel_test_statement": "up to three parallel tests for each specimen",
            "row_independence_established": False,
            "cross_source_comparability_established": False,
        },
        "measurement_header": HEADER,
        "reviewed_numeric_columns": {
            "time_s": 0,
            "extension_mm": 1,
            "strain_percent": 2,
            "load_n": 3,
            "tensile_stress_mpa": 4,
            "tensile_extension_mm": 11,
        },
        "decimal_separator": ",",
        "metadata_block_start_label": "Specimen",
        "specimen_label": "Oznaka vzorca / Specimen",
        "max_parallel_tests_per_sheet": 3,
        "expected_total_measurement_rows": 7,
        "max_measurement_rows_total": 100,
        "max_cells_total": 1000,
        "sheets": {
            name: {
                "manufacturing_route": values[0],
                "condition": values[1],
                "heat_treatment_text": None,
                "build_orientation": values[2],
                "expected_parallel_test_blocks": 1,
            }
            for name, values in semantics.items()
        },
        "scientific_boundaries": {
            "sheet_semantics_reviewed_from_source_readme": True,
            "measurement_header_semantics_reviewed_from_workbook": True,
            "row_level_values_observed": True,
            "parallel_tests_imply_statistical_independence": False,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "automatic_scientific_promotion": False,
        },
    }


def _write_case(tmp_path: Path, *, changed_header: bool = False, formula: bool = False, bad_readme: bool = False):
    workbook_path = tmp_path / "Tensile tests.xlsx"
    workbook = _write_workbook(workbook_path, changed_header=changed_header, formula=formula)
    readme_text = "Mechanical testing - Tensile tests\nDIN50125 (Type E)\nup to three parallel tests\n"
    if not bad_readme:
        readme_text += "\n".join(SHEETS)
    readme = readme_text.encode("cp1250")
    readme_path = tmp_path / "README-Tensile tests.txt"
    readme_path.write_bytes(readme)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_policy(workbook, readme), ensure_ascii=False), encoding="utf-8")
    return workbook_path, readme_path, policy_path


def test_reviewed_tensile_intake_emits_real_rows_without_independence_claim(tmp_path: Path) -> None:
    workbook, readme, policy = _write_case(tmp_path)
    output = tmp_path / "out"
    manifest = build_reviewed_in625_tensile_intake(
        workbook_path=workbook,
        readme_path=readme,
        policy_path=policy,
        output_dir=output,
    )
    assert manifest["sheet_count"] == 7
    assert manifest["parallel_test_block_count"] == 7
    assert manifest["measurement_row_count"] == 7
    assert manifest["row_artifact"]["row_count"] == 7
    assert manifest["reviewed_semantics"]["parallel_test_independence_established"] is False
    assert manifest["scientific_boundaries"]["real_row_level_external_measurements_observed"] is True
    assert manifest["scientific_boundaries"]["direct_nist_condition_comparability_established"] is False
    rows = (output / "reviewed_tensile_rows.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(rows[0])
    assert first["reviewed_numeric_values"]["tensile_stress_mpa"] == 100.0
    assert first["row_is_independent_specimen"] is False


def test_reviewed_tensile_intake_rejects_formula_cells(tmp_path: Path) -> None:
    workbook, readme, policy = _write_case(tmp_path, formula=True)
    with pytest.raises(In625TensileReviewedIntakeError, match="formula"):
        build_reviewed_in625_tensile_intake(
            workbook_path=workbook,
            readme_path=readme,
            policy_path=policy,
        )


def test_reviewed_tensile_intake_rejects_header_drift(tmp_path: Path) -> None:
    workbook, readme, policy = _write_case(tmp_path, changed_header=True)
    with pytest.raises(In625TensileReviewedIntakeError, match="block count drifted"):
        build_reviewed_in625_tensile_intake(
            workbook_path=workbook,
            readme_path=readme,
            policy_path=policy,
        )


def test_reviewed_tensile_intake_rejects_readme_semantic_loss(tmp_path: Path) -> None:
    workbook, readme, policy = _write_case(tmp_path, bad_readme=True)
    with pytest.raises(In625TensileReviewedIntakeError, match="semantic evidence"):
        build_reviewed_in625_tensile_intake(
            workbook_path=workbook,
            readme_path=readme,
            policy_path=policy,
        )


def test_reviewed_tensile_intake_rejects_workbook_byte_substitution(tmp_path: Path) -> None:
    workbook, readme, policy = _write_case(tmp_path)
    workbook.write_bytes(workbook.read_bytes() + b"x")
    with pytest.raises(In625TensileReviewedIntakeError, match="workbook bytes differ"):
        build_reviewed_in625_tensile_intake(
            workbook_path=workbook,
            readme_path=readme,
            policy_path=policy,
        )
