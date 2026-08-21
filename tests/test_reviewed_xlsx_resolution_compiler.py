from __future__ import annotations

import copy
import io
import zipfile

import pytest

from materials_data_analyzer.research_loop.generic_semantic_lineage_proposal import (
    build_generic_semantic_lineage_proposal,
)
from materials_data_analyzer.research_loop.reviewed_resolution_compiler import (
    build_reviewed_resolution_contract,
)
from materials_data_analyzer.research_loop.reviewed_xlsx_resolution_compiler import (
    ReviewedXlsxResolutionCompilerError,
    compile_reviewed_xlsx_resolution,
)
from materials_data_analyzer.research_loop.scientific_review_release import (
    build_review_decision,
)
from materials_data_analyzer.research_loop.xlsx_bounded_row_intake import (
    inspect_xlsx_sheet_rows,
)


def _workbook_bytes(
    *,
    formula: bool = False,
    hidden_row: bool = False,
    hidden_sheet: bool = False,
    merged: bool = False,
    second_value: str = "1.4",
) -> bytes:
    state = ' state="hidden"' if hidden_sheet else ""
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
 <si><t>sample_id</t></si><si><t>acquisition_id</t></si><si><t>value</t></si>
 <si><t>s1</t></si><si><t>a1</t></si><si><t>s2</t></si><si><t>a2</t></si>
</sst>'''
    row_hidden = ' hidden="1"' if hidden_row else ""
    first_value = (
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
  <row r="2"{row_hidden}><c r="A2" t="s"><v>3</v></c><c r="B2" t="s"><v>4</v></c>{first_value}</row>
  <row r="3"><c r="A3" t="s"><v>5</v></c><c r="B3" t="s"><v>6</v></c><c r="C3" s="7"><v>{second_value}</v></c></row>
 </sheetData>{merged_xml}
</worksheet>'''.encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _context(raw: bytes):
    report = inspect_xlsx_sheet_rows(raw, sheet_name="Measurements")
    structure = report["generic_table_projection"]
    proposal = build_generic_semantic_lineage_proposal(
        candidate_id="candidate:unseen-xlsx",
        structure=structure,
    )
    semantic = {
        "source_id": "source:xlsx-fixture",
        "material": {
            "kind": "identity",
            "material_name": "Example Ceramic",
            "declared_identifier": "EXAMPLE-CERAMIC",
            "identity_basis": "source_declared_label",
        },
        "sample_id_column": 0,
        "sample_identity_authority": "authoritative_source_column",
        "property_name": "explicitly_resolved_property",
        "value_column": 2,
        "unit": "resolved-unit",
        "method": "resolved-method",
        "instrument_model": "resolved-instrument",
        "calibration_status": "not_reported_no_claim",
        "calibration_id": None,
        "process_signature": None,
        "standard_uncertainty": {"mode": "none"},
    }
    lineage = {
        "specimen_id_column": 0,
        "specimen_identity_authority": "authoritative_source_column",
        "acquisition_id_column": 1,
        "acquisition_identity_authority": "authoritative_source_column",
        "lab_id_column": None,
        "material_lot_id_column": None,
        "build_or_synthesis_id_column": None,
        "process_run_id_column": None,
    }
    resolution = build_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        semantic_resolution=semantic,
        lineage_resolution=lineage,
    )
    decision = build_review_decision(
        resolution["resolution_review_request"],
        reviewer_id="reviewer:xlsx-fixture",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Fixture approval for the exact XLSX resolved mapping only.",
    )
    return report, proposal, resolution, decision


def test_simple_unseen_xlsx_reaches_strict_normalization_without_source_specific_parser():
    raw = _workbook_bytes()
    report, proposal, resolution, decision = _context(raw)

    manifest = compile_reviewed_xlsx_resolution(
        workbook_bytes=raw,
        xlsx_row_report=report,
        proposal=proposal,
        resolution_contract=resolution,
        review_decision=decision,
    )

    assert manifest["human_review_blocker_released"] is True
    assert manifest["normalized_record_count"] == 2
    assert manifest["rejected_row_count"] == 0
    assert manifest["all_source_rows_normalized"] is True
    assert [item["record_locator"] for item in manifest["records"]] == [
        "xlsx:sheet=Measurements;row=2;sample_cell=A2;value_cell=C2",
        "xlsx:sheet=Measurements;row=3;sample_cell=A3;value_cell=C3",
    ]
    first = manifest["records"][0]
    assert first["measurement"]["sample_id"] == "s1"
    assert first["measurement"]["value"] == pytest.approx(1.2)
    assert first["measurement"]["unit"] == "resolved-unit"
    assert first["lineage"]["specimen_id"] == "s1"
    assert first["lineage"]["acquisition_id"] == "a1"
    assert manifest["effective_independent_unit"]["unique_specimens"] == 2
    assert manifest["effective_independent_unit"]["naive_row_count_is_independence_count"] is False
    assert manifest["formula_cells_admitted"] is False
    assert manifest["cached_formula_values_admitted"] is False
    assert manifest["number_formats_interpreted"] is False
    assert manifest["styles_used_as_scientific_semantics"] is False
    assert manifest["accepted_for_analysis"] is False
    assert manifest["scientific_support_established"] is False
    assert manifest["cross_source_comparability_established"] is False
    assert manifest["hypothesis_support_established"] is False
    assert manifest["scientific_status_changed"] is False
    assert len(manifest["normalized_evidence_manifest_sha256"]) == 64


def test_workbook_selected_sheet_resolution_and_review_mutation_fail_closed():
    raw = _workbook_bytes()
    report, proposal, resolution, decision = _context(raw)

    mutated_raw = _workbook_bytes(second_value="1.5")
    with pytest.raises(ReviewedXlsxResolutionCompilerError, match="bytes differ"):
        compile_reviewed_xlsx_resolution(
            workbook_bytes=mutated_raw,
            xlsx_row_report=report,
            proposal=proposal,
            resolution_contract=resolution,
            review_decision=decision,
        )

    mutated_report = copy.deepcopy(report)
    mutated_report["worksheet_member"] = "xl/worksheets/other.xml"
    with pytest.raises(ReviewedXlsxResolutionCompilerError, match="bytes differ"):
        compile_reviewed_xlsx_resolution(
            workbook_bytes=raw,
            xlsx_row_report=mutated_report,
            proposal=proposal,
            resolution_contract=resolution,
            review_decision=decision,
        )

    mutated_resolution = copy.deepcopy(resolution)
    mutated_resolution["semantic_resolution_contract"]["resolution"]["unit"] = "changed-unit"
    with pytest.raises(ReviewedXlsxResolutionCompilerError, match="resolution verification failed"):
        compile_reviewed_xlsx_resolution(
            workbook_bytes=raw,
            xlsx_row_report=report,
            proposal=proposal,
            resolution_contract=mutated_resolution,
            review_decision=decision,
        )

    mutated_decision = copy.deepcopy(decision)
    mutated_decision["review_notes"] = "Changed after exact review."
    with pytest.raises(ReviewedXlsxResolutionCompilerError, match="review release verification failed"):
        compile_reviewed_xlsx_resolution(
            workbook_bytes=raw,
            xlsx_row_report=report,
            proposal=proposal,
            resolution_contract=resolution,
            review_decision=mutated_decision,
        )


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"formula": True}, "formula"),
        ({"hidden_row": True}, "hidden"),
        ({"hidden_sheet": True}, "hidden"),
        ({"merged": True}, "merged"),
    ],
)
def test_unsafe_excel_representation_never_reaches_reviewed_normalization(kwargs, reason):
    raw = _workbook_bytes(**kwargs)
    report = inspect_xlsx_sheet_rows(raw, sheet_name="Measurements")

    assert report["generic_table_projection_available"] is False
    assert any(reason in item for item in report["unsafe_for_naive_table_projection_reasons"])
    assert report["accepted_for_analysis"] is False
    assert report["scientific_status_changed"] is False


def test_numeric_style_ids_do_not_create_date_unit_or_other_scientific_semantics():
    raw = _workbook_bytes()
    report, proposal, resolution, decision = _context(raw)
    assert report["rows"][1]["cells"][2]["style_id"] == "4"
    assert report["rows"][2]["cells"][2]["style_id"] == "7"
    assert report["number_formats_interpreted"] is False

    manifest = compile_reviewed_xlsx_resolution(
        workbook_bytes=raw,
        xlsx_row_report=report,
        proposal=proposal,
        resolution_contract=resolution,
        review_decision=decision,
    )
    assert manifest["number_formats_interpreted"] is False
    assert manifest["styles_used_as_scientific_semantics"] is False


def test_invalid_numeric_xlsx_row_is_explicitly_rejected_not_coerced():
    raw = _workbook_bytes(second_value="not-a-number")
    report, proposal, resolution, decision = _context(raw)

    manifest = compile_reviewed_xlsx_resolution(
        workbook_bytes=raw,
        xlsx_row_report=report,
        proposal=proposal,
        resolution_contract=resolution,
        review_decision=decision,
    )

    assert manifest["normalized_record_count"] == 1
    assert manifest["rejected_row_count"] == 1
    assert manifest["all_source_rows_normalized"] is False
    assert manifest["rejected_rows"][0]["record_locator"] == "xlsx:sheet=Measurements;row=3"
    assert manifest["accepted_for_analysis"] is False
    assert manifest["scientific_support_established"] is False
