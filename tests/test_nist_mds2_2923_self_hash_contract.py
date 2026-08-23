from __future__ import annotations

import hashlib
import io
import json
import zipfile
from xml.sax.saxutils import escape

from materials_data_analyzer.research_loop.nist_mds2_2923_scientific_intake import (
    DATA_HEADERS,
    SUMMARY_HEADERS,
    audit_mds2_2923,
)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _cell(ref: str, value: object) -> str:
    if isinstance(value, str):
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{ref}"><v>{value}</v></c>'


def _sheet(headers: tuple[str, ...], rows: list[list[object]]) -> str:
    xml_rows: list[str] = []
    for row_number, row in enumerate([list(headers), *rows], start=1):
        cells = "".join(
            _cell(f"{_column(column_number)}{row_number}", value)
            for column_number, value in enumerate(row, start=1)
        )
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


def _workbook() -> bytes:
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Data" sheetId="1" r:id="rId1"/>'
        '<sheet name="Summary" sheetId="2" r:id="rId2"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet2.xml"/>'
        '</Relationships>'
    )
    data_row: list[object] = [
        "IN625_AMMT_Set1",
        "A1",
        ".tiff",
        0.5,
        "A",
        "IN625",
        "320 grit ",
        "AMMT",
        1,
        "X",
        50.0,
        195.0,
        800.0,
        100.0,
        40.0,
    ]
    summary_row: list[object] = [
        "IN625",
        "AMMT",
        50.0,
        195.0,
        800.0,
        1,
        1.0,
        1.0,
        1.0,
        100.0,
        1.0,
        1.0,
        1.0,
        2.0,
        40.0,
        1.0,
        1.0,
        1.0,
        2.0,
    ]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet(DATA_HEADERS, [data_row]))
        archive.writestr("xl/worksheets/sheet2.xml", _sheet(SUMMARY_HEADERS, [summary_row]))
    return output.getvalue()


def _metadata() -> bytes:
    path = "Micrographs/IN625_AMMT_Set1/A1.tiff"
    payload = {
        "@id": "ark:/88434/mds2-2923",
        "ediid": "mds2-2923",
        "doi": "10.18434/mds2-2923",
        "components": [
            {
                "@type": ["nrdp:DataFile"],
                "filepath": path,
                "downloadURL": f"https://data.nist.gov/od/ds/mds2-2923/{path}",
                "size": 1,
                "checksum": {
                    "hash": hashlib.sha256(b"x").hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            }
        ],
    }
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def test_scientific_intake_self_hash_uses_repository_canonical_json_and_survives_roundtrip() -> None:
    report = audit_mds2_2923(
        workbook_bytes=_workbook(),
        readme_bytes=b"The laser power and scan speed are machine settings.\n",
        nerdm_metadata_bytes=_metadata(),
    )
    supplied = report["report_sha256_without_self_field"]
    unsigned = dict(report)
    unsigned.pop("report_sha256_without_self_field")

    assert supplied == _canonical_sha(unsigned)
    roundtripped = json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))
    roundtrip_supplied = roundtripped.pop("report_sha256_without_self_field")
    assert roundtrip_supplied == supplied
    assert roundtrip_supplied == _canonical_sha(roundtripped)
