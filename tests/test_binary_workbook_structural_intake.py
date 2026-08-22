from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.binary_workbook_structural_intake import (
    BinaryWorkbookStructuralIntakeError,
    inspect_legacy_xls_binding,
    inspect_xlsx_workbook_structure,
)


def _xlsx(path: Path, *, macro: bool = False) -> str:
    content_type = (
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
        if macro
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Override PartName="/xl/workbook.xml" ContentType="{content_type}"/>
</Types>''',
        )
        archive.writestr(
            "xl/workbook.xml",
            '''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Tensile" sheetId="1" r:id="rId1"/></sheets>
</workbook>''',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>''',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <dimension ref="A1:B2"/>
 <sheetData>
  <row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>2</v></c></row>
  <row r="2"><c r="A2"><f>SUM(A1:A1)</f><v>1</v></c><c r="B2"><v>3</v></c></row>
 </sheetData>
</worksheet>''',
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_xlsx_structure_is_hash_bound_without_value_or_scientific_interpretation(tmp_path: Path) -> None:
    path = tmp_path / "Tensile tests.xlsx"
    digest = _xlsx(path)
    report = inspect_xlsx_workbook_structure(path, expected_sha256=digest)
    assert report["artifact_sha256"] == digest
    assert report["sheet_count"] == 1
    assert report["sheets"] == [
        {
            "name": "Tensile",
            "sheet_id": "1",
            "worksheet_member": "xl/worksheets/sheet1.xml",
            "dimension_ref": "A1:B2",
            "row_element_count": 2,
            "cell_element_count": 4,
            "formula_element_count": 1,
        }
    ]
    assert report["cell_values_interpreted"] is False
    assert report["formulas_evaluated"] is False
    assert report["accepted_for_analysis"] is False
    assert report["scientific_support_established"] is False
    assert report["scientific_status_changed"] is False


def test_xlsx_hash_drift_and_macro_content_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "candidate.xlsx"
    digest = _xlsx(path)
    with pytest.raises(BinaryWorkbookStructuralIntakeError, match="expected SHA-256"):
        inspect_xlsx_workbook_structure(path, expected_sha256="0" * 64)
    macro_path = tmp_path / "macro.xlsx"
    macro_digest = _xlsx(macro_path, macro=True)
    with pytest.raises(BinaryWorkbookStructuralIntakeError, match="macro-enabled"):
        inspect_xlsx_workbook_structure(macro_path, expected_sha256=macro_digest)
    assert digest != macro_digest


def test_legacy_xls_is_bound_but_not_semantically_decoded(tmp_path: Path) -> None:
    path = tmp_path / "wear_data.xls"
    path.write_bytes(bytes.fromhex("d0cf11e0a1b11ae1") + b"legacy-biff-placeholder")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report = inspect_legacy_xls_binding(path, expected_sha256=digest)
    assert report["artifact_sha256"] == digest
    assert report["format"] == "legacy_xls_ole_compound"
    assert report["binary_structure_decoded"] is False
    assert report["accepted_for_analysis"] is False
    assert report["scientific_status_changed"] is False


def test_legacy_xls_rejects_non_ole_bytes(tmp_path: Path) -> None:
    path = tmp_path / "wear_data.xls"
    path.write_bytes(b"not-an-ole-workbook")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(BinaryWorkbookStructuralIntakeError, match="OLE compound-file"):
        inspect_legacy_xls_binding(path, expected_sha256=digest)
