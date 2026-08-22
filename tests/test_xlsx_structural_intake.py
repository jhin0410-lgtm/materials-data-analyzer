from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from materials_data_analyzer.research_loop.xlsx_structural_intake import (
    XlsxStructuralIntakeError,
    inspect_xlsx_structure,
    resolve_xlsx_relationship_target,
)


def _workbook_bytes(
    *,
    malicious_name: str | None = None,
    relationship_target: str = "worksheets/sheet1.xml",
) -> bytes:
    workbook = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Measurements" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''
    rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{relationship_target}"/>
</Relationships>'''.encode("utf-8")
    strings = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
 <si><t>Laser Power (W)</t></si><si><t>Melt Pool Width (um)</t></si>
</sst>'''
    sheet = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <dimension ref="A1:B2"/>
 <sheetData>
  <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
  <row r="2"><c r="A2"><v>195</v></c><c r="B2"><v>121.5</v></c></row>
 </sheetData>
</worksheet>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        if malicious_name:
            archive.writestr(malicious_name, b"escape")
    return output.getvalue()


def test_structural_intake_lists_sheets_and_small_preview_without_scientific_upgrade():
    raw = _workbook_bytes()
    report = inspect_xlsx_structure(raw)

    assert report["workbook_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["sheet_count"] == 1
    sheet = report["sheets"][0]
    assert sheet["sheet_name"] == "Measurements"
    assert sheet["dimension"] == "A1:B2"
    assert [cell["value"] for cell in sheet["preview_rows"][0]["cells"]] == [
        "Laser Power (W)",
        "Melt Pool Width (um)",
    ]
    assert report["accepted_for_analysis"] is False
    assert report["requires_domain_mapping"] is True
    assert report["scientific_status_changed"] is False
    assert report["structural_parse_is_scientific_validation"] is False


def test_relationship_target_dot_segments_are_resolved_relative_to_source_part():
    assert (
        resolve_xlsx_relationship_target(
            "xl/workbook.xml",
            "../xl/worksheets/sheet1.xml",
        )
        == "xl/worksheets/sheet1.xml"
    )
    report = inspect_xlsx_structure(
        _workbook_bytes(relationship_target="../xl/worksheets/sheet1.xml")
    )
    assert report["sheets"][0]["worksheet_member"] == "xl/worksheets/sheet1.xml"


def test_package_absolute_relationship_target_is_normalized_safely():
    report = inspect_xlsx_structure(
        _workbook_bytes(relationship_target="/xl/worksheets/sheet1.xml")
    )
    assert report["sheets"][0]["worksheet_member"] == "xl/worksheets/sheet1.xml"


def test_relationship_target_cannot_resolve_outside_package_root():
    with pytest.raises(XlsxStructuralIntakeError, match="outside the package root"):
        inspect_xlsx_structure(
            _workbook_bytes(relationship_target="../../escape.xml")
        )


def test_external_style_uri_without_external_mode_fails_closed():
    with pytest.raises(XlsxStructuralIntakeError, match="scheme"):
        inspect_xlsx_structure(
            _workbook_bytes(relationship_target="https://example.org/sheet1.xml")
        )


def test_zip_slip_style_member_is_rejected_even_without_extraction():
    with pytest.raises(XlsxStructuralIntakeError, match="escapes"):
        inspect_xlsx_structure(_workbook_bytes(malicious_name="../escape.xml"))


def test_xlsx_uncompressed_budget_is_enforced_before_xml_semantics():
    raw = _workbook_bytes()
    with pytest.raises(XlsxStructuralIntakeError, match="uncompressed size"):
        inspect_xlsx_structure(raw, max_uncompressed_bytes=10)


def test_non_zip_bytes_fail_closed():
    with pytest.raises(XlsxStructuralIntakeError, match="valid XLSX"):
        inspect_xlsx_structure(b"not-an-xlsx")
