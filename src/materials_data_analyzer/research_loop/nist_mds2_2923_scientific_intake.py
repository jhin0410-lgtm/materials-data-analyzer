"""Source-specific scientific intake for NIST PDR mds2-2923.

The workbook ``Data`` sheet is the row-level authority. ``Summary`` is audited only as
a derived view. The adapter never converts machine-setting power into calibrated
actual power, pools machines, or promotes this source into Issue #76.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any, Mapping
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "1.0"
PRODUCT_ID = "mds2-2923"
MATERIAL = "IN625"
_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")

DATA_HEADERS = (
    "Folder Name",
    "Image Name",
    "Image file format",
    "Pixel Size (µm)",
    "Sample Name",
    "Material",
    "Surface Condition",
    "Machine",
    "Track No.",
    "Scan Direction",
    "Est. Spot Diameter (D4σ = Dg)",
    "Laser Power (W)",
    "Laser Scan Speed (mm/s)",
    "Width (µm)",
    "Depth (µm)",
)
SUMMARY_HEADERS = (
    "Material",
    "Machine",
    "Estimated D4σ Spot Diameter (µm)",
    "Laser Power (W)",
    "Scan Speed (mm/s)",
    "no. of measurements",
    "t-value (p = 1- 0.68/2 )",
    "Optical resolution (µm)",
    "User selection (µm)",
    "Average Width (µm)",
    "Std. dev. Width (µm)",
    "Standard uncertainty of the mean width (µm)",
    "Width: Variability along track (µm)",
    "Width: Combined, Expanded uncertainty (µm); U (k=2)",
    "Average Depth (µm)",
    "Std. dev. Depth (µm)",
    " Standard uncertainty of the mean depth (µm)",
    "Depth: Variability along track (µm)",
    "Depth: Combined, Expanded uncertainty (µm); U (k-2)",
)
ISSUE_76_TARGETS = (
    {
        "machine": "AMMT",
        "actual_power_w": 137.9,
        "scan_speed_mm_s": 800.0,
        "minimum_tracks": 3,
    },
    {
        "machine": "AMMT",
        "actual_power_w": 137.9,
        "scan_speed_mm_s": 1200.0,
        "minimum_tracks": 3,
    },
    {
        "machine": "AMMT",
        "actual_power_w": 179.2,
        "scan_speed_mm_s": 400.0,
        "minimum_tracks": 3,
    },
)


class NistMds22923ScientificIntakeError(ValueError):
    """Raised when source-specific intake cannot be proven from exact bytes."""


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _excel_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NistMds22923ScientificIntakeError(
            f"expected numeric Excel value, got {value!r}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise NistMds22923ScientificIntakeError("Excel number must be finite")
    # Excel comparisons/calculations are defined at 15 significant decimal digits.
    return float(format(number, ".15g"))


def _json_object(raw: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise NistMds22923ScientificIntakeError(
                    f"NERDm metadata repeats JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistMds22923ScientificIntakeError(
            "NERDm metadata must be UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistMds22923ScientificIntakeError(
            "NERDm metadata root must be an object"
        )
    return value


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _sheet_rows(xlsx_bytes: bytes, sheet_name: str) -> list[dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise NistMds22923ScientificIntakeError(
            "workbook is not a valid XLSX"
        ) from exc

    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise NistMds22923ScientificIntakeError(
                "XLSX repeats ZIP member names"
            )
        if not {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}.issubset(names):
            raise NistMds22923ScientificIntakeError(
                "XLSX workbook parts are missing"
            )

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{_XLSX_NS}}}si"):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.iter(f"{{{_XLSX_NS}}}t")
                    )
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
        target: str | None = None
        sheets = workbook.find(f"{{{_XLSX_NS}}}sheets")
        if sheets is None:
            raise NistMds22923ScientificIntakeError("XLSX has no sheets")
        for sheet in sheets:
            if sheet.attrib.get("name") == sheet_name:
                rel_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
                target = rel_map.get(rel_id or "")
                break
        if target is None:
            raise NistMds22923ScientificIntakeError(
                f"required sheet {sheet_name!r} is missing"
            )
        member = (
            target.lstrip("/")
            if target.startswith("/")
            else "xl/" + target.lstrip("/")
        )
        if member not in names:
            raise NistMds22923ScientificIntakeError(
                f"sheet XML for {sheet_name!r} is missing"
            )

        root = ET.fromstring(archive.read(member))
        rows: list[dict[str, Any]] = []
        seen_rows: set[int] = set()
        for row in root.findall(
            f".//{{{_XLSX_NS}}}sheetData/{{{_XLSX_NS}}}row"
        ):
            row_number = int(row.attrib["r"])
            if row_number in seen_rows:
                raise NistMds22923ScientificIntakeError(
                    f"sheet {sheet_name!r} repeats row {row_number}"
                )
            seen_rows.add(row_number)
            cells: dict[str, dict[str, Any]] = {}
            for cell in row.findall(f"{{{_XLSX_NS}}}c"):
                ref = cell.attrib.get("r", "")
                match = _CELL_RE.fullmatch(ref)
                if not match or int(match.group(2)) != row_number:
                    raise NistMds22923ScientificIntakeError(
                        f"invalid XLSX cell reference {ref!r}"
                    )
                column = match.group(1)
                if column in cells:
                    raise NistMds22923ScientificIntakeError(
                        f"duplicate XLSX cell {ref!r}"
                    )
                formula_node = cell.find(f"{{{_XLSX_NS}}}f")
                value_node = cell.find(f"{{{_XLSX_NS}}}v")
                cell_type = cell.attrib.get("t")
                value: Any = None
                if cell_type == "s":
                    if value_node is None or value_node.text is None:
                        raise NistMds22923ScientificIntakeError(
                            f"shared-string cell {ref!r} has no index"
                        )
                    try:
                        value = shared[int(value_node.text)]
                    except (ValueError, IndexError) as exc:
                        raise NistMds22923ScientificIntakeError(
                            f"bad shared-string index at {ref!r}"
                        ) from exc
                elif cell_type == "inlineStr":
                    value = "".join(
                        node.text or ""
                        for node in cell.findall(f".//{{{_XLSX_NS}}}t")
                    )
                elif cell_type == "str":
                    value = value_node.text if value_node is not None else ""
                elif cell_type == "b":
                    value = value_node is not None and value_node.text == "1"
                elif value_node is not None and value_node.text is not None:
                    try:
                        number = float(value_node.text)
                    except ValueError:
                        value = value_node.text
                    else:
                        value = int(number) if number.is_integer() else number
                cells[column] = {
                    "value": value,
                    "formula": (
                        formula_node.text if formula_node is not None else None
                    ),
                }
            rows.append({"row": row_number, "cells": cells})
        return rows


def _records(
    rows: list[dict[str, Any]],
    headers: tuple[str, ...],
    *,
    sheet_name: str,
    reject_formulas: bool,
) -> list[dict[str, Any]]:
    if not rows or rows[0]["row"] != 1:
        raise NistMds22923ScientificIntakeError(
            f"{sheet_name!r} must have header row 1"
        )
    columns = {
        _column(index): header for index, header in enumerate(headers, start=1)
    }
    for column, header in columns.items():
        observed = rows[0]["cells"].get(column, {}).get("value")
        if observed != header:
            raise NistMds22923ScientificIntakeError(
                f"{sheet_name!r} header {column} mismatch"
            )

    result: list[dict[str, Any]] = []
    for row in rows[1:]:
        record: dict[str, Any] = {"excel_row": row["row"]}
        populated = False
        for column, header in columns.items():
            cell = row["cells"].get(
                column, {"value": None, "formula": None}
            )
            if reject_formulas and cell["formula"] is not None:
                raise NistMds22923ScientificIntakeError(
                    f"row-level Data authority contains formula at "
                    f"{column}{row['row']}"
                )
            record[header] = cell["value"]
            populated = populated or cell["value"] is not None
        if populated:
            result.append(record)
    return result


def _data_group(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["Material"],
        row["Machine"],
        _excel_number(row["Est. Spot Diameter (D4σ = Dg)"]),
        _excel_number(row["Laser Power (W)"]),
        _excel_number(row["Laser Scan Speed (mm/s)"]),
    )


def _summary_group(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["Material"],
        row["Machine"],
        _excel_number(row["Estimated D4σ Spot Diameter (µm)"]),
        _excel_number(row["Laser Power (W)"]),
        _excel_number(row["Scan Speed (mm/s)"]),
    )


def _track_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (row["Machine"], row["Sample Name"], row["Track No."])


def _track_id(key: tuple[Any, ...]) -> str:
    return (
        "nist-mds2-2923:physical-track:"
        + _sha256(_json_bytes(list(key)))[:20]
    )


def _validate_in625_row(row: Mapping[str, Any]) -> None:
    for field in (
        "Folder Name",
        "Image Name",
        "Image file format",
        "Sample Name",
        "Material",
        "Surface Condition",
        "Machine",
        "Scan Direction",
    ):
        if not isinstance(row[field], str) or not row[field]:
            raise NistMds22923ScientificIntakeError(
                f"Data row {row['excel_row']} has invalid {field}"
            )
    for field in (
        "Pixel Size (µm)",
        "Track No.",
        "Est. Spot Diameter (D4σ = Dg)",
        "Laser Power (W)",
        "Laser Scan Speed (mm/s)",
        "Width (µm)",
        "Depth (µm)",
    ):
        _excel_number(row[field])
    if row["Image file format"] != ".tiff":
        raise NistMds22923ScientificIntakeError(
            f"Data row {row['excel_row']} changes the expected source format claim"
        )


def _datafiles(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    identifiers = [
        value
        for field in ("@id", "ediid", "doi")
        if isinstance((value := metadata.get(field)), str)
    ]
    if not any(PRODUCT_ID.lower() in value.lower() for value in identifiers):
        raise NistMds22923ScientificIntakeError(
            "metadata does not bind mds2-2923"
        )
    components = metadata.get("components")
    if not isinstance(components, list):
        raise NistMds22923ScientificIntakeError(
            "NERDm components must be a list"
        )

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            continue
        types = component.get("@type")
        if not isinstance(types, list) or "nrdp:DataFile" not in types:
            continue
        path = component.get("filepath")
        url = component.get("downloadURL")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(url, str)
            or not url
        ):
            continue
        if path in seen:
            raise NistMds22923ScientificIntakeError(
                f"NERDm repeats DataFile {path!r}"
            )
        seen.add(path)
        size = component.get("size")
        if isinstance(size, str) and size.isdigit():
            size = int(size)
        checksum = component.get("checksum")
        algorithm = (
            checksum.get("algorithm") if isinstance(checksum, dict) else None
        )
        tag = algorithm.get("tag") if isinstance(algorithm, dict) else algorithm
        digest = checksum.get("hash") if isinstance(checksum, dict) else None
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(tag, str)
            or tag.lower().replace("-", "") != "sha256"
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            raise NistMds22923ScientificIntakeError(
                f"NERDm DataFile {path!r} lacks exact size/SHA-256"
            )
        result.append(
            {
                "filepath": path,
                "download_url": url,
                "size_bytes": size,
                "sha256": digest,
            }
        )
    return result


def _source_anomalies(readme: str) -> list[dict[str, str]]:
    checks = (
        (
            "readme_workbook_name_typo",
            "Master_TrackList_Measuremetns.xlsx",
            "README narrative misspells the workbook filename.",
        ),
        (
            "readme_manifest_id_mismatch",
            "2857_README.txt : This readme file.",
            "README manifest calls itself 2857_README.txt.",
        ),
        (
            "readme_manifest_workbook_extension_mismatch",
            "Master_TrackList_Measurements.xls :",
            "README manifest says .xls while NERDm authority is .xlsx.",
        ),
        (
            "readme_citation_doi_mismatch",
            "https://doi.org/10.18434/mds2-2716",
            "README citation DOI conflicts with mds2-2923 repository identity.",
        ),
    )
    return [
        {"code": code, "observed": token, "interpretation": interpretation}
        for code, token, interpretation in checks
        if token in readme
    ]


def audit_mds2_2923(
    *,
    workbook_bytes: bytes,
    readme_bytes: bytes,
    nerdm_metadata_bytes: bytes,
) -> dict[str, Any]:
    """Build a bounded row-level IN625 intake report from exact authoritative bytes."""

    if not all(
        isinstance(value, bytes)
        for value in (workbook_bytes, readme_bytes, nerdm_metadata_bytes)
    ):
        raise NistMds22923ScientificIntakeError(
            "source inputs must be exact bytes"
        )
    try:
        readme = readme_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NistMds22923ScientificIntakeError("README must be UTF-8") from exc
    metadata = _json_object(nerdm_metadata_bytes)

    data = _records(
        _sheet_rows(workbook_bytes, "Data"),
        DATA_HEADERS,
        sheet_name="Data",
        reject_formulas=True,
    )
    summary = _records(
        _sheet_rows(workbook_bytes, "Summary"),
        SUMMARY_HEADERS,
        sheet_name="Summary",
        reject_formulas=False,
    )
    in625 = [row for row in data if row["Material"] == MATERIAL]
    if not in625:
        raise NistMds22923ScientificIntakeError("Data contains no IN625 rows")
    for row in in625:
        _validate_in625_row(row)

    tracks: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in in625:
        tracks[_track_key(row)].append(row)

    conflict_fields = (
        "Material",
        "Pixel Size (µm)",
        "Surface Condition",
        "Scan Direction",
        "Est. Spot Diameter (D4σ = Dg)",
        "Laser Power (W)",
        "Laser Scan Speed (mm/s)",
    )
    track_conflicts = []
    fatal_fields = set(conflict_fields) - {"Surface Condition"}
    for key, rows in tracks.items():
        conflicts: dict[str, list[Any]] = {}
        for field in conflict_fields:
            values: list[Any] = []
            for row in rows:
                value = row[field]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = _excel_number(value)
                if value not in values:
                    values.append(value)
            if len(values) > 1:
                conflicts[field] = values
        if fatal_fields.intersection(conflicts):
            raise NistMds22923ScientificIntakeError(
                f"physical-track fields conflict for {key!r}: {conflicts}"
            )
        if conflicts:
            track_conflicts.append(
                {
                    "physical_track_id": _track_id(key),
                    "source_key": {
                        "machine": key[0],
                        "sample_name": key[1],
                        "track_no": key[2],
                    },
                    "excel_rows": [row["excel_row"] for row in rows],
                    "conflicts": conflicts,
                }
            )

    data_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in in625:
        data_groups[_data_group(row)].append(row)
    summary_map: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in (item for item in summary if item["Material"] == MATERIAL):
        key = _summary_group(row)
        if key in summary_map:
            raise NistMds22923ScientificIntakeError(
                f"Summary repeats group {key!r}"
            )
        summary_map[key] = row

    missing_summary = []
    count_mismatches = []
    for key, rows in sorted(
        data_groups.items(), key=lambda item: tuple(map(str, item[0]))
    ):
        if key not in summary_map:
            missing_summary.append(
                {
                    "material": key[0],
                    "machine": key[1],
                    "spot_diameter_um": key[2],
                    "laser_power_w_machine_setting": key[3],
                    "scan_speed_mm_s_machine_setting": key[4],
                    "measurement_count": len(rows),
                    "excel_rows": [row["excel_row"] for row in rows],
                }
            )
        elif _excel_number(summary_map[key]["no. of measurements"]) != float(
            len(rows)
        ):
            count_mismatches.append(
                {
                    "group": list(key),
                    "data_measurement_count": len(rows),
                    "summary_measurement_count": summary_map[key][
                        "no. of measurements"
                    ],
                    "summary_excel_row": summary_map[key]["excel_row"],
                }
            )
    extra_summary = [
        {"group": list(key), "summary_excel_row": row["excel_row"]}
        for key, row in summary_map.items()
        if key not in data_groups
    ]

    datafiles = _datafiles(metadata)
    by_folder_stem: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for component in datafiles:
        if component["filepath"].startswith("Micrographs/"):
            path = PurePosixPath(component["filepath"])
            by_folder_stem[(path.parent.name, path.stem)].append(component)

    measurements = []
    bound_paths: set[str] = set()
    extension_mismatches = 0
    for row in in625:
        lookup = (row["Folder Name"], row["Image Name"])
        matches = by_folder_stem.get(lookup, [])
        if len(matches) != 1:
            raise NistMds22923ScientificIntakeError(
                f"Data row {row['excel_row']} maps to {len(matches)} NERDm micrographs"
            )
        component = matches[0]
        if component["filepath"] in bound_paths:
            raise NistMds22923ScientificIntakeError(
                f"multiple Data rows map to {component['filepath']!r}"
            )
        bound_paths.add(component["filepath"])
        if PurePosixPath(component["filepath"]).suffix != row["Image file format"]:
            extension_mismatches += 1
        key = _track_key(row)
        measurements.append(
            {
                "measurement_id": f"nist-mds2-2923:data-row:{row['excel_row']}",
                "workbook_excel_row": row["excel_row"],
                "physical_track_id": _track_id(key),
                "source_track_identity": {
                    "machine": row["Machine"],
                    "sample_name": row["Sample Name"],
                    "track_no": row["Track No."],
                },
                "folder_name": row["Folder Name"],
                "image_name": row["Image Name"],
                "workbook_image_format_claim": row["Image file format"],
                "nerdm_micrograph_filepath": component["filepath"],
                "nerdm_micrograph_sha256": component["sha256"],
                "nerdm_micrograph_size_bytes": component["size_bytes"],
                "nerdm_micrograph_download_url": component["download_url"],
                "pixel_size_um": _excel_number(row["Pixel Size (µm)"]),
                "material": row["Material"],
                "surface_condition_source": row["Surface Condition"],
                "surface_condition_normalized": row["Surface Condition"].strip(),
                "machine": row["Machine"],
                "track_no": row["Track No."],
                "scan_direction": row["Scan Direction"],
                "estimated_or_measured_spot_diameter_um": _excel_number(
                    row["Est. Spot Diameter (D4σ = Dg)"]
                ),
                "laser_power_w_machine_setting": _excel_number(
                    row["Laser Power (W)"]
                ),
                "scan_speed_mm_s_machine_setting": _excel_number(
                    row["Laser Scan Speed (mm/s)"]
                ),
                "width_um": _excel_number(row["Width (µm)"]),
                "depth_um": _excel_number(row["Depth (µm)"]),
            }
        )

    support: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in in625:
        key = (
            row["Machine"],
            _excel_number(row["Laser Power (W)"]),
            _excel_number(row["Laser Scan Speed (mm/s)"]),
        )
        item = support.setdefault(
            key,
            {"rows": 0, "tracks": set(), "spots": set(), "surfaces": set()},
        )
        item["rows"] += 1
        item["tracks"].add(_track_id(_track_key(row)))
        item["spots"].add(
            _excel_number(row["Est. Spot Diameter (D4σ = Dg)"])
        )
        item["surfaces"].add(row["Surface Condition"].strip())
    support_rows = [
        {
            "machine": key[0],
            "laser_power_w_machine_setting": key[1],
            "scan_speed_mm_s_machine_setting": key[2],
            "measurement_count": support[key]["rows"],
            "independent_physical_track_count": len(support[key]["tracks"]),
            "spot_diameter_level_count": len(support[key]["spots"]),
            "surface_conditions_normalized": sorted(support[key]["surfaces"]),
        }
        for key in sorted(
            support, key=lambda value: (str(value[0]), value[1], value[2])
        )
    ]

    issue_76 = []
    for target in ISSUE_76_TARGETS:
        matching = {
            item["physical_track_id"]
            for item in measurements
            if item["machine"] == target["machine"]
            and item["laser_power_w_machine_setting"] == target["actual_power_w"]
            and item["scan_speed_mm_s_machine_setting"]
            == target["scan_speed_mm_s"]
        }
        issue_76.append(
            {
                **target,
                "exact_source_setting_track_count": len(matching),
                "acceptance_met": len(matching) >= target["minimum_tracks"],
                "calibration_inference_performed": False,
            }
        )

    machine_measurements = Counter(item["machine"] for item in measurements)
    machine_tracks = Counter(key[0] for key in tracks)
    repeat_distribution = Counter(len(rows) for rows in tracks.values())
    all_in625_micrographs = [
        item
        for item in datafiles
        if item["filepath"].startswith("Micrographs/IN625")
    ]
    if len(all_in625_micrographs) < len(measurements):
        raise NistMds22923ScientificIntakeError(
            "NERDm IN625 inventory is smaller than Data measurements"
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "product_id": PRODUCT_ID,
            "doi": "10.18434/mds2-2923",
            "workbook_sha256": _sha256(workbook_bytes),
            "workbook_size_bytes": len(workbook_bytes),
            "readme_sha256": _sha256(readme_bytes),
            "readme_size_bytes": len(readme_bytes),
            "nerdm_metadata_sha256": _sha256(nerdm_metadata_bytes),
            "source_anomalies": _source_anomalies(readme),
        },
        "measurement_semantics": {
            "laser_power": "machine_setting_as_stated_by_README",
            "scan_speed": "machine_setting_as_stated_by_README",
            "spot_diameter": {
                "AMMT": "measured",
                "EOS M270": "estimated",
                "EOS M290": "estimated",
            },
            "width_depth": "optical_cross_section_measurements_defined_by_README",
            "calibration_conversion_performed": False,
        },
        "in625_inventory": {
            "measurement_row_count": len(measurements),
            "physical_track_count": len(tracks),
            "machine_measurement_counts": dict(sorted(machine_measurements.items())),
            "machine_physical_track_counts": dict(sorted(machine_tracks.items())),
            "measurements_per_physical_track_distribution": {
                str(key): value for key, value in sorted(repeat_distribution.items())
            },
            "source_track_metadata_conflict_count": len(track_conflicts),
            "source_track_metadata_conflicts": track_conflicts,
            "data_process_spot_group_count": len(data_groups),
            "summary_process_spot_group_count": len(summary_map),
            "summary_missing_group_count": len(missing_summary),
            "summary_missing_measurement_row_count": sum(
                item["measurement_count"] for item in missing_summary
            ),
            "summary_missing_groups": missing_summary,
            "summary_count_mismatches": count_mismatches,
            "summary_extra_groups": extra_summary,
        },
        "micrograph_binding": {
            "nerdm_datafile_count": len(datafiles),
            "nerdm_in625_micrograph_count": len(all_in625_micrographs),
            "data_referenced_micrograph_count": len(measurements),
            "unique_bound_micrograph_count": len(bound_paths),
            "bound_micrograph_total_size_bytes": sum(
                item["nerdm_micrograph_size_bytes"] for item in measurements
            ),
            "workbook_extension_claim_mismatch_count": extension_mismatches,
            "mapping_basis": (
                "exact workbook Folder Name + Image Name stem to unique NERDm DataFile"
            ),
            "filename_only_identity_used": False,
        },
        "machine_power_speed_support": support_rows,
        "issue_76": {
            "eligible": False,
            "target_cells": issue_76,
            "exact_target_cells_satisfied": sum(
                item["acceptance_met"] for item in issue_76
            ),
            "reason": (
                "mds2-2923 power/speed are machine settings; no source-specific basis "
                "relabels them as calibrated-actual AMMT powers required by #76."
            ),
        },
        "scientific_boundary": {
            "adjacent_machine_stratified_descriptive_intake_prepared": True,
            "cross_machine_pooling_eligible": False,
            "predictive_modeling_eligible_from_this_audit": False,
            "causal_inference_eligible_from_this_audit": False,
            "optimization_eligible_from_this_audit": False,
            "human_scientific_review_decision_created": False,
            "scientific_support_established": False,
            "scientific_status_changed": False,
        },
        "measurements": measurements,
    }
    report["report_sha256_without_self_field"] = _sha256(_json_bytes(report))
    return report


def compact_micrograph_manifest(report: Mapping[str, Any]) -> dict[str, Any]:
    measurements = report.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        raise NistMds22923ScientificIntakeError("report has no measurements")
    files = [
        {
            "measurement_id": item["measurement_id"],
            "physical_track_id": item["physical_track_id"],
            "filepath": item["nerdm_micrograph_filepath"],
            "sha256": item["nerdm_micrograph_sha256"],
            "size_bytes": item["nerdm_micrograph_size_bytes"],
        }
        for item in measurements
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "product_id": PRODUCT_ID,
        "workbook_sha256": report["source"]["workbook_sha256"],
        "nerdm_metadata_sha256": report["source"]["nerdm_metadata_sha256"],
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
        "scientific_status_changed": False,
        "issue_76_eligible": False,
    }


__all__ = [
    "DATA_HEADERS",
    "ISSUE_76_TARGETS",
    "NistMds22923ScientificIntakeError",
    "PRODUCT_ID",
    "SCHEMA_VERSION",
    "SUMMARY_HEADERS",
    "audit_mds2_2923",
    "compact_micrograph_manifest",
]
