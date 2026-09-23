from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest

from materials_data_analyzer.research_loop.evidence_expectation_trust import (
    validate_authenticated_evidence_packet,
)
from materials_data_analyzer.research_loop.evidence_packet import (
    EvidencePacketError,
    canonical_sha256,
)
from materials_data_analyzer.research_loop.in625_competency_evidence import (
    MDS2_BENCHMARK_ADAPTER_ID,
    In625CompetencyEvidenceError,
    build_mds2_2923_ammt_195_800_evidence_packets,
    build_mds2_2923_ammt_195_800_validation_material,
)
from materials_data_analyzer.research_loop.nist_mds2_2923_scientific_intake import (
    DATA_HEADERS,
    SUMMARY_HEADERS,
)


# These bytes are a parser/contract fixture only. They are never evidence for #254.
# The real benchmark must receive production-acquired mds2-2923 bytes whose hashes are
# authenticated by the existing live acquisition/intake chain.


def _col(index: int) -> str:
    out = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        out = chr(ord("A") + remainder) + out
    return out


def _cell(ref: str, value: object) -> str:
    if isinstance(value, str):
        return (
            f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        )
    return f'<c r="{ref}"><v>{value}</v></c>'


def _sheet(headers: tuple[str, ...], rows: list[list[object]]) -> str:
    payload = []
    for row_no, values in enumerate([list(headers), *rows], start=1):
        cells = [
            _cell(f"{_col(col_no)}{row_no}", value)
            for col_no, value in enumerate(values, start=1)
        ]
        payload.append(f'<row r="{row_no}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(payload)}</sheetData></worksheet>'
    )


def _xlsx(data_rows: list[list[object]], summary_rows: list[list[object]]) -> bytes:
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
            _sheet(DATA_HEADERS, data_rows),
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            _sheet(SUMMARY_HEADERS, summary_rows),
        )
    return output.getvalue()


def _data_row(index: int, spot: float) -> list[object]:
    return [
        "IN625_AMMT_Set1",
        f"A{index:02d}",
        ".tiff",
        0.5,
        f"Sample-{index:02d}",
        "IN625",
        "320 grit ",
        "AMMT",
        index,
        "X",
        spot,
        195.0,
        800.0,
        100.0 + index,
        40.0 + index / 10.0,
    ]


def _summary_row(spot: float, count: int) -> list[object]:
    return [
        "IN625",
        "AMMT",
        spot,
        195.0,
        800.0,
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


def _fixture() -> tuple[bytes, bytes, bytes]:
    spots = [50.0, 75.0, 100.0, 125.0, 150.0, 200.0, 256.0]
    rows = [_data_row(index, spots[(index - 1) % len(spots)]) for index in range(1, 19)]
    counts = {spot: 0 for spot in spots}
    for row in rows:
        counts[float(row[10])] += 1
    summary = [_summary_row(spot, counts[spot]) for spot in spots]
    workbook = _xlsx(rows, summary)

    components = []
    for index in range(1, 19):
        path = f"Micrographs/IN625_AMMT_Set1/A{index:02d}.tif"
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
    metadata = (
        json.dumps(
            {
                "@id": "ark:/88434/mds2-2923",
                "ediid": "mds2-2923",
                "doi": "10.18434/mds2-2923",
                "components": components,
            },
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    readme = (
        "The laser power and scan speed are machine settings.\n"
        "Cross-sectional width and depth are optical measurements.\n"
    ).encode("utf-8")
    return workbook, readme, metadata


def _rehash(packet: dict[str, object]) -> dict[str, object]:
    value = copy.deepcopy(packet)
    value.pop("packet_sha256", None)
    value["packet_sha256"] = canonical_sha256(value)
    return value


def test_contract_fixture_builds_eighteen_distinct_row_authority_packets() -> None:
    workbook, readme, metadata = _fixture()
    packets = build_mds2_2923_ammt_195_800_evidence_packets(
        workbook_bytes=workbook,
        readme_bytes=readme,
        nerdm_metadata_bytes=metadata,
    )

    assert len(packets) == 18
    assert len({packet["packet_sha256"] for packet in packets}) == 18
    assert len(
        {
            next(
                identity["value"]
                for identity in packet["subject"]["identities"]
                if identity["namespace"] == "mds2_physical_track_id"
            )
            for packet in packets
        }
    ) == 18

    first = packets[0]
    assert first["provider"]["adapter_id"] == MDS2_BENCHMARK_ADAPTER_ID
    assert first["authority"] == {
        "empirical_evidence_created": True,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "planning_metadata_only": False,
        "row_level_measurement_authority": True,
        "authority_source": "domain_verifier",
    }
    process = {
        item["name"]: item for item in first["contexts"]["process"]["attributes"]
    }
    assert process["laser_power_machine_setting"]["value"] == 195.0
    assert process["scan_speed_machine_setting"]["value"] == 800.0
    assert "actual_laser_power" not in process
    assert first["calibration"] == {"status": "unknown", "records": []}
    assert first["uncertainty"][0]["status"] == "unknown"
    assert first["comparability"]["comparison_performed"] is False
    assert "calibrated actual laser power" in first["scientific_validity"]["excluded_scope"]


def test_contract_fixture_validation_material_replays_exact_source_bytes() -> None:
    workbook, readme, metadata = _fixture()
    material = build_mds2_2923_ammt_195_800_validation_material(
        workbook_bytes=workbook,
        readme_bytes=readme,
        nerdm_metadata_bytes=metadata,
    )
    assert len(material) == 18
    item = material[0]
    assert "trusted_expectation_sha256" not in item

    replayed = validate_authenticated_evidence_packet(
        item["packet"],
        artifacts=item["artifacts"],
        expected=item["expected"],
        trusted_expectation_sha256=canonical_sha256(item["expected"]),
    )
    assert replayed == item["packet"]


def test_machine_setting_cannot_be_rehashed_into_calibrated_actual_power() -> None:
    workbook, readme, metadata = _fixture()
    item = build_mds2_2923_ammt_195_800_validation_material(
        workbook_bytes=workbook,
        readme_bytes=readme,
        nerdm_metadata_bytes=metadata,
    )[0]
    forged = copy.deepcopy(item["packet"])
    process = forged["contexts"]["process"]["attributes"]
    power = next(
        attribute
        for attribute in process
        if attribute["name"] == "laser_power_machine_setting"
    )
    power["name"] = "actual_laser_power"
    forged = _rehash(forged)

    with pytest.raises(
        EvidencePacketError,
        match="authenticated packet SHA-256 expectation drifted",
    ):
        validate_authenticated_evidence_packet(
            forged,
            artifacts=item["artifacts"],
            expected=item["expected"],
            trusted_expectation_sha256=canonical_sha256(item["expected"]),
        )


def test_wrong_subset_fails_closed_instead_of_synthesizing_missing_rows() -> None:
    workbook, readme, metadata = _fixture()
    # Replace the exact source machine-setting token in the workbook bytes by building
    # a fixture with only 17 target rows and one 180 W row.
    spots = [50.0, 75.0, 100.0, 125.0, 150.0, 200.0, 256.0]
    rows = [_data_row(index, spots[(index - 1) % len(spots)]) for index in range(1, 19)]
    rows[-1][11] = 180.0
    counts: dict[float, int] = {spot: 0 for spot in spots}
    for row in rows:
        if row[11] == 195.0:
            counts[float(row[10])] += 1
    summary = [_summary_row(spot, count) for spot, count in counts.items() if count]
    workbook = _xlsx(rows, summary)

    with pytest.raises(In625CompetencyEvidenceError, match="row count drifted"):
        build_mds2_2923_ammt_195_800_evidence_packets(
            workbook_bytes=workbook,
            readme_bytes=readme,
            nerdm_metadata_bytes=metadata,
        )
