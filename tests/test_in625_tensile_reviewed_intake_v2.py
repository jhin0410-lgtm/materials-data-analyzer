from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from materials_data_analyzer.research_loop.in625_tensile_reviewed_intake_v2 import (
    In625TensileReviewedIntakeV2Error,
    build_reviewed_in625_tensile_intake_v2,
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


def _column(index: int) -> str:
    result = ""
    value = index + 1
    while value:
        value, rem = divmod(value - 1, 26)
        result = chr(ord("A") + rem) + result
    return result


def _cell(row: int, column: int, value: str, *, formula: bool = False) -> str:
    coordinate = f"{_column(column)}{row}"
    formula_xml = "<f>1+1</f>" if formula else ""
    return (
        f'<c r="{coordinate}" t="inlineStr">{formula_xml}'
        f"<is><t>{escape(value)}</t></is></c>"
    )


def _sheet_xml(
    name: str,
    *,
    partial_row: bool = False,
    formula: bool = False,
) -> str:
    rows = [
        '<row r="1">' + _cell(1, 0, "Specimen") + _cell(1, 1, "1") + "</row>",
        '<row r="2">'
        + _cell(2, 0, "Oznaka vzorca / Specimen")
        + _cell(2, 1, f"{name}-1")
        + "</row>",
        '<row r="3">'
        + "".join(_cell(3, index, value) for index, value in enumerate(HEADER))
        + "</row>",
    ]
    complete = [
        "0,00",
        "0,10",
        "0,20",
        "10,0",
        "100,0",
        "0",
        "0",
        "0",
        "644",
        "0",
        "0",
        "0,02",
    ]
    rows.append(
        '<row r="4">'
        + "".join(
            _cell(4, index, value, formula=formula and index == 4)
            for index, value in enumerate(complete)
        )
        + "</row>"
    )
    if partial_row:
        partial = [
            "0,01",
            "0,11",
            "0,21",
            "",
            "instrument-note",
            "0",
            "0",
            "0",
            "644",
            "0",
            "0",
            "0,03",
        ]
        rows.append(
            '<row r="5">'
            + "".join(_cell(5, index, value) for index, value in enumerate(partial))
            + "</row>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="A1:L5"/><sheetData>'
        + "".join(rows)
        + "</sheetData></worksheet>"
    )


def _write_workbook(
    path: Path,
    *,
    partial_first_sheet: bool = False,
    formula: bool = False,
) -> bytes:
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
    # Use a producer-valid dot-segment form to exercise the shared OPC resolver.
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="../xl/worksheets/sheet{index}.xml"/>'
            for index in range(1, 8)
        )
        + "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        for index, name in enumerate(SHEETS, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _sheet_xml(
                    name,
                    partial_row=partial_first_sheet and index == 1,
                    formula=formula and index == 1,
                ),
            )
    return path.read_bytes()


def _policy(workbook: bytes, readme: bytes, *, rows: int) -> dict[str, object]:
    conditions = {
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
        "expected_total_measurement_rows": rows,
        "max_measurement_rows_total": 100,
        "max_cells_total": 2000,
        "sheets": {
            name: {
                "manufacturing_route": condition[0],
                "condition": condition[1],
                "heat_treatment_text": None,
                "build_orientation": condition[2],
                "expected_parallel_test_blocks": 1,
            }
            for name, condition in conditions.items()
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


def _case(
    tmp_path: Path,
    *,
    partial: bool = False,
    formula: bool = False,
):
    workbook_path = tmp_path / "Tensile tests.xlsx"
    workbook = _write_workbook(
        workbook_path,
        partial_first_sheet=partial,
        formula=formula,
    )
    readme = (
        "Mechanical testing - Tensile tests\n"
        "DIN50125 (Type E)\n"
        "up to three parallel tests\n"
        + "\n".join(SHEETS)
    ).encode("cp1250")
    readme_path = tmp_path / "README-Tensile tests.txt"
    readme_path.write_bytes(readme)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(_policy(workbook, readme, rows=8 if partial else 7)),
        encoding="utf-8",
    )
    return workbook_path, readme_path, policy_path


def test_v2_preserves_complete_rows_without_scientific_upgrade(tmp_path: Path) -> None:
    workbook, readme, policy = _case(tmp_path)
    output = tmp_path / "out"
    manifest = build_reviewed_in625_tensile_intake_v2(
        workbook_path=workbook,
        readme_path=readme,
        policy_path=policy,
        output_dir=output,
    )
    assert manifest["measurement_row_count"] == 7
    assert manifest["complete_numeric_measurement_row_count"] == 7
    assert manifest["incomplete_numeric_measurement_row_count"] == 0
    assert manifest["evidence_quality"]["all_reviewed_numeric_fields_complete"] is True
    assert manifest["reviewed_semantics"]["missing_values_imputed"] is False
    assert manifest["scientific_boundaries"]["replicate_independence_established"] is False
    assert manifest["scientific_boundaries"]["direct_nist_condition_comparability_established"] is False


def test_v2_retains_blank_and_nonnumeric_selected_fields_as_quality_evidence(tmp_path: Path) -> None:
    workbook, readme, policy = _case(tmp_path, partial=True)
    output = tmp_path / "out"
    manifest = build_reviewed_in625_tensile_intake_v2(
        workbook_path=workbook,
        readme_path=readme,
        policy_path=policy,
        output_dir=output,
    )
    assert manifest["measurement_row_count"] == 8
    assert manifest["complete_numeric_measurement_row_count"] == 7
    assert manifest["incomplete_numeric_measurement_row_count"] == 1
    assert manifest["reviewed_numeric_field_quality_counts"]["load_n"]["blank"] == 1
    assert manifest["reviewed_numeric_field_quality_counts"]["tensile_stress_mpa"]["non_numeric"] == 1
    assert manifest["evidence_quality"]["incomplete_rows_retained_as_evidence"] is True
    example = manifest["bounded_incomplete_row_examples"][0]
    assert example["missing_reviewed_numeric_fields"] == ["load_n"]
    assert example["non_numeric_reviewed_fields"] == ["tensile_stress_mpa"]

    rows = [
        json.loads(line)
        for line in (output / "reviewed_tensile_rows.v2.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    partial = next(row for row in rows if not row["row_complete_for_reviewed_numeric_analysis"])
    assert partial["reviewed_numeric_values"]["load_n"] is None
    assert partial["reviewed_numeric_values"]["tensile_stress_mpa"] is None
    assert partial["raw_anomalous_cell_text"]["tensile_stress_mpa"] == "instrument-note"
    assert partial["row_is_independent_specimen"] is False


def test_v2_still_rejects_formula_cells(tmp_path: Path) -> None:
    workbook, readme, policy = _case(tmp_path, formula=True)
    with pytest.raises(In625TensileReviewedIntakeV2Error, match="formula"):
        build_reviewed_in625_tensile_intake_v2(
            workbook_path=workbook,
            readme_path=readme,
            policy_path=policy,
        )
