from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

import pytest

from materials_data_analyzer.research_loop.nist_amb2025_03_fatigue_intake import (
    HEADERS,
    NistAmb202503FatigueIntakeError,
    audit_amb2025_03_fatigue,
)


README = (
    "Fatigue Testing Twenty-four specimens from each condition were tested in "
    "four-point rotating bending fatigue (RBF) using an ADMET eXpert 9313 "
    "(test frequency 100 Hz, load ratio R = -1) fatigue testing machine according "
    "to ISO 1143. The diameter of each specimen was measured prior to testing "
    "using calipers, which have a rated accuracy of ±0.01mm.\n\n"
    "The .xlsx file contains raw fatigue data and can be opened using Microsoft Excel"
).encode("utf-8")


def _cell(ref: str, value: object, *, formula: str | None = None) -> str:
    if value is None and formula is None:
        return ""
    formula_xml = f"<f>{escape(formula)}</f>" if formula is not None else ""
    if isinstance(value, str):
        return (
            f'<c r="{ref}" t="inlineStr">{formula_xml}'
            f"<is><t>{escape(value)}</t></is></c>"
        )
    return f'<c r="{ref}">{formula_xml}<v>{value}</v></c>'


def _xlsx(rows: list[list[object]], *, formula_f3: bool = False) -> bytes:
    row_xml: list[str] = []
    for row_number, values in enumerate(rows, start=1):
        cells = []
        for index, value in enumerate(values, start=1):
            column = chr(ord("A") + index - 1)
            formula = "E3*2" if formula_f3 and row_number == 3 and column == "F" else None
            rendered = _cell(f"{column}{row_number}", value, formula=formula)
            if rendered:
                cells.append(rendered)
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="data" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _rows() -> list[list[object]]:
    return [
        ["800HIP12C/min"],
        list(HEADERS),
        [1, "18", "2.1", 4.09, 750, 100.7, None, "Op", "10M runout"],
        [2, "42", "2.2", 4.10, 925, 125.1, 10_000_000, "Op", "runout 10,347,875 cycles"],
        [3, "114", "2.3", 4.14, 1100, 153.2, 28_467, "Op", None],
        [4, "54", "2.4", 4.13, 1050, 145.2, None, "Op", "invalid test, load application error, stopped test manually"],
    ]


def test_runout_notes_override_cycles_column_event_semantics() -> None:
    report = audit_amb2025_03_fatigue(
        workbook_bytes=_xlsx(_rows(), formula_f3=True), readme_bytes=README
    )

    assert report["fatigue_inventory"]["observed_failures"] == 1
    assert report["fatigue_inventory"]["runouts"] == 2
    assert report["fatigue_inventory"]["invalid_tests"] == 1
    assert report["fatigue_inventory"]["desired_load_formula_cell_count"] == 1
    assert report["runout_reconciliation"]["exact_integer_censor_cycles_from_notes"] == 1
    assert report["runout_reconciliation"]["million_shorthand_rows_requiring_semantic_review"] == 1
    assert report["runout_reconciliation"]["cycles_column_vs_exact_note_discrepancy_count"] == 1
    assert report["analysis_eligibility"]["naive_uncensored_cycles_regression"]["eligible"] is False
    assert report["analysis_eligibility"]["condition_specific_censored_sn_analysis"]["eligible"] is False
    assert report["scientific_status_changed"] is False

    runout = next(item for item in report["records"] if item["specimen_id_source"] == "42")
    assert runout["event_observed"] is False
    assert runout["cycles_column_value"] == 10_000_000
    assert runout["censor_cycles_exact"] == 10_347_875


def test_observed_failure_requires_no_runout_or_invalid_note() -> None:
    report = audit_amb2025_03_fatigue(
        workbook_bytes=_xlsx(_rows()), readme_bytes=README
    )
    failure = next(item for item in report["records"] if item["specimen_id_source"] == "114")
    invalid = next(item for item in report["records"] if item["specimen_id_source"] == "54")
    assert failure["outcome"] == "failure"
    assert failure["event_observed"] is True
    assert failure["failure_cycles"] == 28_467
    assert invalid["outcome"] == "invalid"
    assert invalid["event_observed"] is False


def test_core_event_semantics_may_not_be_formula_derived() -> None:
    rows = _rows()
    workbook = _xlsx(rows)
    # Build a second workbook where the cycles authority itself is a formula.
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(workbook), "r") as source, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            body = source.read(name)
            if name == "xl/worksheets/sheet1.xml":
                text = body.decode("utf-8")
                text = text.replace('<c r="G5"><v>28467</v></c>', '<c r="G5"><f>10000+18467</f><v>28467</v></c>')
                body = text.encode("utf-8")
            target.writestr(name, body)

    with pytest.raises(NistAmb202503FatigueIntakeError, match="core fatigue authority contains formula"):
        audit_amb2025_03_fatigue(workbook_bytes=output.getvalue(), readme_bytes=README)


def test_header_mutation_fails_closed() -> None:
    rows = _rows()
    rows[1][6] = "lifetime"
    with pytest.raises(NistAmb202503FatigueIntakeError, match="header G mismatch"):
        audit_amb2025_03_fatigue(workbook_bytes=_xlsx(rows), readme_bytes=README)
