from __future__ import annotations

import hashlib
import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest

from materials_data_analyzer.research_loop.nist_mds2_2923_scientific_intake import (
    DATA_HEADERS,
    NistMds22923ScientificIntakeError,
    SUMMARY_HEADERS,
    audit_mds2_2923,
    compact_micrograph_manifest,
)


def _col(index: int) -> str:
    out = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        out = chr(ord("A") + remainder) + out
    return out


def _cell(ref: str, value: object, formula: str | None = None) -> str:
    formula_xml = "" if formula is None else f"<f>{escape(formula)}</f>"
    if isinstance(value, str):
        return (
            f'<c r="{ref}" t="inlineStr">{formula_xml}<is><t>'
            f"{escape(value)}</t></is></c>"
        )
    return f'<c r="{ref}">{formula_xml}<v>{value}</v></c>'


def _sheet(
    headers: tuple[str, ...],
    rows: list[list[object]],
    formula_cell: tuple[int, int] | None = None,
) -> str:
    xml_rows = []
    all_rows = [list(headers), *rows]
    for row_no, row in enumerate(all_rows, start=1):
        cells = []
        for col_no, value in enumerate(row, start=1):
            ref = f"{_col(col_no)}{row_no}"
            formula = "1+1" if formula_cell == (row_no, col_no) else None
            cells.append(_cell(ref, value, formula))
        xml_rows.append(f'<row r="{row_no}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


def _xlsx(
    data_rows: list[list[object]],
    summary_rows: list[list[object]],
    *,
    data_formula_cell: tuple[int, int] | None = None,
) -> bytes:
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
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            _sheet(DATA_HEADERS, data_rows, formula_cell=data_formula_cell),
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            _sheet(SUMMARY_HEADERS, summary_rows),
        )
    return output.getvalue()


def _data_row(
    folder: str,
    image: str,
    sample: str,
    machine: str,
    track: int,
    spot: float,
    power: float,
    speed: float,
    width: float,
    depth: float,
    surface: str = "320 grit ",
) -> list[object]:
    return [
        folder,
        image,
        ".tiff",
        0.5,
        sample,
        "IN625",
        surface,
        machine,
        track,
        "X",
        spot,
        power,
        speed,
        width,
        depth,
    ]


def _summary_row(
    machine: str, spot: float, power: float, speed: float, count: int
) -> list[object]:
    return [
        "IN625",
        machine,
        spot,
        power,
        speed,
        count,
        1.0,
        1.0,
        1.0,
        100.0,
        1.0,
        1.0,
        1.0,
        2.0,
        50.0,
        1.0,
        1.0,
        1.0,
        2.0,
    ]


def _metadata(paths: list[str]) -> bytes:
    components = []
    for path in paths:
        body = path.encode("utf-8")
        components.append(
            {
                "@type": ["nrdp:DataFile"],
                "filepath": path,
                "downloadURL": (
                    "https://data.nist.gov/od/ds/mds2-2923/"
                    + path.replace(" ", "%20")
                ),
                "size": len(body),
                "checksum": {
                    "hash": hashlib.sha256(body).hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            }
        )
    payload = {
        "@id": "ark:/88434/mds2-2923",
        "ediid": "mds2-2923",
        "doi": "10.18434/mds2-2923",
        "components": components,
    }
    return (json.dumps(payload, sort_keys=True) + "\n").encode()


def _readme() -> bytes:
    return (
        "The laser power and scan speed are machine settings.\n"
        "Master_TrackList_Measuremetns.xlsx\n"
        "2857_README.txt : This readme file.\n"
        "Master_TrackList_Measurements.xls : Excel spreadsheet\n"
        "https://doi.org/10.18434/mds2-2716\n"
    ).encode()


def test_row_level_intake_keeps_repeated_measurements_and_summary_omissions_separate() -> None:
    rows = [
        _data_row(
            "IN625_AMMT_Set1", "A1", "A", "AMMT", 1, 50.0, 180.0, 800.0, 100.0, 40.0
        ),
        _data_row(
            "IN625_EOS_Set1",
            "E1",
            "E",
            "EOS M270",
            1,
            188.88800000000003,
            195.0,
            800.0,
            120.0,
            50.0,
        ),
        _data_row(
            "IN625_EOS_Set2",
            "E2",
            "E",
            "EOS M270",
            1,
            188.888,
            195.0,
            800.0,
            122.0,
            52.0,
            "323 grit ",
        ),
    ]
    workbook = _xlsx(
        rows, [_summary_row("EOS M270", 188.888, 195.0, 800.0, 2)]
    )
    metadata = _metadata(
        [
            "Micrographs/IN625_AMMT_Set1/A1.tif",
            "Micrographs/IN625_EOS_Set1/E1.tif",
            "Micrographs/IN625_EOS_Set2/E2.tif",
        ]
    )

    report = audit_mds2_2923(
        workbook_bytes=workbook,
        readme_bytes=_readme(),
        nerdm_metadata_bytes=metadata,
    )

    inventory = report["in625_inventory"]
    assert inventory["measurement_row_count"] == 3
    assert inventory["physical_track_count"] == 2
    assert inventory["measurements_per_physical_track_distribution"] == {
        "1": 1,
        "2": 1,
    }
    assert inventory["summary_missing_group_count"] == 1
    assert inventory["summary_missing_measurement_row_count"] == 1
    assert inventory["summary_count_mismatches"] == []
    assert inventory["source_track_metadata_conflict_count"] == 1
    assert set(inventory["source_track_metadata_conflicts"][0]["conflicts"]) == {
        "Surface Condition"
    }
    assert report["micrograph_binding"]["unique_bound_micrograph_count"] == 3
    assert report["micrograph_binding"]["workbook_extension_claim_mismatch_count"] == 3
    assert report["issue_76"]["exact_target_cells_satisfied"] == 0
    assert report["issue_76"]["eligible"] is False
    assert report["scientific_boundary"]["scientific_status_changed"] is False

    manifest = compact_micrograph_manifest(report)
    assert manifest["file_count"] == 3
    assert manifest["issue_76_eligible"] is False


def test_ambiguous_micrograph_stem_mapping_fails_closed() -> None:
    workbook = _xlsx(
        [
            _data_row(
                "IN625_AMMT_Set1", "A1", "A", "AMMT", 1, 50.0, 180.0, 800.0, 100.0, 40.0
            )
        ],
        [],
    )
    metadata = _metadata(
        [
            "Micrographs/IN625_AMMT_Set1/A1.tif",
            "Micrographs/IN625_AMMT_Set1/A1.png",
        ]
    )

    with pytest.raises(
        NistMds22923ScientificIntakeError, match="maps to 2 NERDm micrographs"
    ):
        audit_mds2_2923(
            workbook_bytes=workbook,
            readme_bytes=_readme(),
            nerdm_metadata_bytes=metadata,
        )


def test_formula_in_row_level_data_authority_is_rejected() -> None:
    workbook = _xlsx(
        [
            _data_row(
                "IN625_AMMT_Set1", "A1", "A", "AMMT", 1, 50.0, 180.0, 800.0, 100.0, 40.0
            )
        ],
        [],
        data_formula_cell=(2, 14),
    )
    metadata = _metadata(["Micrographs/IN625_AMMT_Set1/A1.tif"])

    with pytest.raises(
        NistMds22923ScientificIntakeError, match="contains formula"
    ):
        audit_mds2_2923(
            workbook_bytes=workbook,
            readme_bytes=_readme(),
            nerdm_metadata_bytes=metadata,
        )


def test_ammt_195_machine_setting_is_not_relabelled_as_issue_76_actual_power() -> None:
    workbook = _xlsx(
        [
            _data_row(
                "IN625_AMMT_Set1", "A1", "A", "AMMT", 1, 50.0, 195.0, 800.0, 100.0, 40.0
            )
        ],
        [_summary_row("AMMT", 50.0, 195.0, 800.0, 1)],
    )
    metadata = _metadata(["Micrographs/IN625_AMMT_Set1/A1.tif"])

    report = audit_mds2_2923(
        workbook_bytes=workbook,
        readme_bytes=_readme(),
        nerdm_metadata_bytes=metadata,
    )

    assert report["issue_76"]["exact_target_cells_satisfied"] == 0
    assert all(
        item["calibration_inference_performed"] is False
        for item in report["issue_76"]["target_cells"]
    )
    assert report["measurement_semantics"]["calibration_conversion_performed"] is False
