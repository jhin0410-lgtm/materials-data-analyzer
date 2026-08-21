from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from materials_data_analyzer.research_loop.generic_semantic_lineage_proposal import (
    build_generic_semantic_lineage_proposal,
)
from materials_data_analyzer.research_loop.xlsx_bounded_row_intake import (
    XlsxBoundedRowIntakeError,
    inspect_xlsx_sheet_rows,
)


def _workbook_bytes(
    *,
    sheet_state: str = "visible",
    hidden_second_row: bool = False,
    formula: bool = False,
    merged: bool = False,
) -> bytes:
    state = "" if sheet_state == "visible" else f' state="{sheet_state}"'
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Measurements" sheetId="1"{state} r:id="rId1"/></sheets>
</workbook>'''.encode()
    rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''
    strings = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="7" uniqueCount="7">
 <si><t>sample_id</t></si>
 <si><t>acquisition_id</t></si>
 <si><t>voltage_v</t></si>
 <si><t>s1</t></si>
 <si><t>a1</t></si>
 <si><t>s2</t></si>
 <si><t>a2</t></si>
</sst>'''
    hidden = ' hidden="1"' if hidden_second_row else ""
    value_cell = (
        '<c r="C2" s="4"><f>1.0+0.2</f><v>1.2</v></c>'
        if formula
        else '<c r="C2" s="4"><v>1.2</v></c>'
    )
    merged_xml = '<mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>' if merged else ""
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <dimension ref="A1:C3"/>
 <sheetData>
  <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
  <row r="2"{hidden}><c r="A2" t="s"><v>3</v></c><c r="B2" t="s"><v>4</v></c>{value_cell}</row>
  <row r="3"><c r="A3" t="s"><v>5</v></c><c r="B3" t="s"><v>6</v></c><c r="C3"><v>1.4</v></c></row>
 </sheetData>
 {merged_xml}
</worksheet>'''.encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def test_simple_sheet_exposes_exact_rows_and_proposal_only_projection():
    raw = _workbook_bytes()
    report = inspect_xlsx_sheet_rows(raw, sheet_name="Measurements")

    assert report["workbook_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["sheet_name"] == "Measurements"
    assert report["worksheet_member"] == "xl/worksheets/sheet1.xml"
    assert report["sheet_state"] == "visible"
    assert report["row_count"] == 3
    assert report["cell_count"] == 9
    assert report["formula_cell_count"] == 0
    assert report["formula_evaluated"] is False
    assert report["number_formats_interpreted"] is False
    assert report["generic_table_projection_available"] is True
    assert report["unsafe_for_naive_table_projection_reasons"] == []

    cell = report["rows"][1]["cells"][2]
    assert cell["coordinate"] == "C2"
    assert cell["raw_stored_value"] == "1.2"
    assert cell["style_id"] == "4"
    assert cell["number_format_interpreted"] is False
    assert cell["scientific_semantics_interpreted"] is False

    projection = report["generic_table_projection"]
    assert projection["artifact_sha256"] == hashlib.sha256(raw).hexdigest()
    assert projection["first_row_header_candidate"] == [
        "sample_id",
        "acquisition_id",
        "voltage_v",
    ]
    assert projection["preview_rows"][1] == ["s1", "a1", "1.2"]
    assert projection["column_profiles"][0]["header_semantic_hints_proposal_only"] == [
        "identity_like"
    ]
    assert projection["column_profiles"][2]["header_semantic_hints_proposal_only"] == [
        "measurement_like"
    ]
    assert projection["accepted_for_analysis"] is False
    assert projection["sample_identity_inferred"] is False
    assert projection["replicate_independence_inferred"] is False
    assert report["accepted_for_analysis"] is False
    assert report["scientific_support_established"] is False
    assert report["scientific_status_changed"] is False
    assert len(report["row_intake_report_sha256"]) == 64


def test_safe_xlsx_projection_can_feed_generic_proposal_without_semantic_promotion():
    raw = _workbook_bytes()
    report = inspect_xlsx_sheet_rows(raw, sheet_name="Measurements")

    packet = build_generic_semantic_lineage_proposal(
        candidate_id="candidate:xlsx-unseen",
        structure=report["generic_table_projection"],
    )

    assert packet["evidence_artifact_sha256"] == hashlib.sha256(raw).hexdigest()
    assert packet["semantic_proposal"]["candidate_identity_columns"] == [0, 1]
    assert packet["semantic_proposal"]["candidate_measurement_columns"] == [2]
    assert packet["semantic_proposal"]["sample_identity_inferred"] is False
    assert packet["lineage_proposal"]["replicate_independence_established"] is False
    assert packet["proposal_can_instantiate_normalized_measurement"] is False
    assert packet["accepted_for_analysis"] is False
    assert packet["scientific_status_changed"] is False


def test_formula_is_never_evaluated_and_blocks_generic_projection():
    raw = _workbook_bytes(formula=True)
    report = inspect_xlsx_sheet_rows(raw, sheet_name="Measurements")

    formula_cell = report["rows"][1]["cells"][2]
    assert formula_cell["representation"] == "formula_with_cached_value"
    assert formula_cell["formula_text"] == "1.0+0.2"
    assert formula_cell["raw_stored_value"] == "1.2"
    assert formula_cell["formula_evaluated"] is False
    assert report["formula_cell_count"] == 1
    assert report["cached_formula_value_count"] == 1
    assert report["generic_table_projection_available"] is False
    assert "selected_sheet_contains_formula_cells" in report[
        "unsafe_for_naive_table_projection_reasons"
    ]
    assert report["accepted_for_analysis"] is False


def test_hidden_rows_hidden_sheet_and_merged_cells_block_naive_projection():
    hidden_row = inspect_xlsx_sheet_rows(
        _workbook_bytes(hidden_second_row=True),
        sheet_name="Measurements",
    )
    hidden_sheet = inspect_xlsx_sheet_rows(
        _workbook_bytes(sheet_state="hidden"),
        sheet_name="Measurements",
    )
    merged = inspect_xlsx_sheet_rows(
        _workbook_bytes(merged=True),
        sheet_name="Measurements",
    )

    assert hidden_row["hidden_row_numbers"] == [2]
    assert hidden_row["generic_table_projection_available"] is False
    assert "selected_sheet_contains_hidden_rows" in hidden_row[
        "unsafe_for_naive_table_projection_reasons"
    ]
    assert hidden_sheet["sheet_state"] == "hidden"
    assert hidden_sheet["generic_table_projection_available"] is False
    assert "selected_sheet_is_hidden_or_very_hidden" in hidden_sheet[
        "unsafe_for_naive_table_projection_reasons"
    ]
    assert merged["merged_cell_ranges"] == ["A1:B1"]
    assert merged["generic_table_projection_available"] is False
    assert "selected_sheet_contains_merged_cells" in merged[
        "unsafe_for_naive_table_projection_reasons"
    ]


def test_sheet_identity_and_resource_ceilings_fail_closed():
    raw = _workbook_bytes()
    with pytest.raises(XlsxBoundedRowIntakeError, match="does not exist"):
        inspect_xlsx_sheet_rows(raw, sheet_name="Missing")
    with pytest.raises(XlsxBoundedRowIntakeError, match="row ceiling"):
        inspect_xlsx_sheet_rows(raw, sheet_name="Measurements", max_rows=2)
    with pytest.raises(XlsxBoundedRowIntakeError, match="cell ceiling"):
        inspect_xlsx_sheet_rows(raw, sheet_name="Measurements", max_cells=8)
    with pytest.raises(XlsxBoundedRowIntakeError, match="column ceiling"):
        inspect_xlsx_sheet_rows(raw, sheet_name="Measurements", max_columns=2)
