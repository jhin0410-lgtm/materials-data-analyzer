"""Exact-byte bounded XLSX row intake without Excel semantic inference.

The reader exposes one explicitly selected worksheet as provenance-bearing raw cell
records.  It never evaluates formulas, never interprets number formats as dates/units,
and only emits a generic table projection when workbook structure is safe enough for a
naive rectangular representation.  That projection is still proposal-only.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from .kernel import ResearchLoopError
from .xlsx_structural_intake import (
    DEFAULT_MAX_XML_MEMBER_BYTES,
    DEFAULT_MAX_XLSX_ENTRIES,
    DEFAULT_MAX_XLSX_UNCOMPRESSED_BYTES,
    inspect_xlsx_structure,
)

XLSX_BOUNDED_ROW_INTAKE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_XLSX_ROWS = 50_000
DEFAULT_MAX_XLSX_COLUMNS = 256
DEFAULT_MAX_XLSX_CELLS = 500_000
DEFAULT_MAX_XLSX_CELL_CHARACTERS = 16_384
DEFAULT_PROFILE_UNIQUE_VALUES = 10_000
DEFAULT_PREVIEW_ROWS = 5

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_HINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("identity_like", re.compile(r"(?:^|[^a-z])(sample|specimen|coupon|cell|track|image|file|id)(?:[^a-z]|$)", re.I)),
    ("replicate_like", re.compile(r"(?:replicate|repeat|trial|run)(?:[^a-z]|$)", re.I)),
    ("time_like", re.compile(r"(?:^|[^a-z])(time|timestamp|cycle)(?:[^a-z]|$)", re.I)),
    ("frequency_like", re.compile(r"(?:frequency|freq|hz)(?:[^a-z]|$)", re.I)),
    ("temperature_like", re.compile(r"(?:temperature|temp)(?:[^a-z]|$)", re.I)),
    ("measurement_like", re.compile(r"(?:voltage|current|power|width|depth|height|stress|strain|resistance|impedance)(?:[^a-z]|$)", re.I)),
)


class XlsxBoundedRowIntakeError(ResearchLoopError):
    """Raised when exact XLSX rows cannot be exposed without unsafe interpretation."""


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XlsxBoundedRowIntakeError(f"{field} must be a positive integer")
    return value


def _canonical_sha(value: object) -> str:
    try:
        body = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise XlsxBoundedRowIntakeError(
            "XLSX row intake report must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(body).hexdigest()


def _safe_xml(raw: bytes, field: str) -> ET.Element:
    upper = raw[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise XlsxBoundedRowIntakeError(f"{field} contains prohibited DTD/entity declarations")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise XlsxBoundedRowIntakeError(f"{field} is malformed XML") from exc


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise XlsxBoundedRowIntakeError("XLSX member path is not safe POSIX")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise XlsxBoundedRowIntakeError("XLSX member path escapes the workbook root")
    return path.as_posix()


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    max_bytes: int,
) -> bytes:
    if info.flag_bits & 0x1:
        raise XlsxBoundedRowIntakeError(f"encrypted XLSX member is not allowed: {info.filename}")
    if info.file_size > max_bytes:
        raise XlsxBoundedRowIntakeError(
            f"XLSX member exceeds bounded row-intake byte ceiling: {info.filename}"
        )
    with archive.open(info, "r") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes or len(raw) != info.file_size:
        raise XlsxBoundedRowIntakeError(
            f"XLSX member size is inconsistent or exceeds limit: {info.filename}"
        )
    return raw


def _column_index(cell_ref: str) -> int:
    match = _CELL_REF_RE.fullmatch(cell_ref)
    if not match:
        raise XlsxBoundedRowIntakeError(f"invalid worksheet cell reference: {cell_ref!r}")
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def _load_shared_strings(
    archive: zipfile.ZipFile,
    infos: Mapping[str, zipfile.ZipInfo],
    *,
    max_xml_member_bytes: int,
    max_cell_characters: int,
) -> list[str]:
    info = infos.get("xl/sharedStrings.xml")
    if info is None:
        return []
    root = _safe_xml(
        _read_member(archive, info, max_bytes=max_xml_member_bytes),
        "xl/sharedStrings.xml",
    )
    result: list[str] = []
    for si in root.findall(f"{{{_MAIN_NS}}}si"):
        value = "".join(node.text or "" for node in si.iter(f"{{{_MAIN_NS}}}t"))
        if len(value) > max_cell_characters:
            raise XlsxBoundedRowIntakeError("shared string exceeds cell character ceiling")
        result.append(value)
    return result


def _workbook_sheet_map(
    archive: zipfile.ZipFile,
    infos: Mapping[str, zipfile.ZipInfo],
    *,
    max_xml_member_bytes: int,
) -> dict[str, dict[str, str]]:
    workbook = _safe_xml(
        _read_member(archive, infos["xl/workbook.xml"], max_bytes=max_xml_member_bytes),
        "xl/workbook.xml",
    )
    rels = _safe_xml(
        _read_member(
            archive,
            infos["xl/_rels/workbook.xml.rels"],
            max_bytes=max_xml_member_bytes,
        ),
        "xl/_rels/workbook.xml.rels",
    )
    targets: dict[str, str] = {}
    for rel in rels.findall(f"{{{_PKG_REL_NS}}}Relationship"):
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if not isinstance(rel_id, str) or not isinstance(target, str):
            raise XlsxBoundedRowIntakeError("workbook relationship is missing Id/Target")
        if rel.get("TargetMode") == "External":
            continue
        targets[rel_id] = _safe_member_name(
            target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
        )
    sheets_node = workbook.find(f"{{{_MAIN_NS}}}sheets")
    if sheets_node is None:
        raise XlsxBoundedRowIntakeError("workbook has no sheets collection")
    result: dict[str, dict[str, str]] = {}
    for sheet in sheets_node.findall(f"{{{_MAIN_NS}}}sheet"):
        name = sheet.get("name")
        rel_id = sheet.get(f"{{{_REL_NS}}}id")
        if not isinstance(name, str) or not isinstance(rel_id, str) or rel_id not in targets:
            raise XlsxBoundedRowIntakeError("worksheet identity or relationship is invalid")
        result[name] = {
            "worksheet_member": targets[rel_id],
            "sheet_state": sheet.get("state", "visible"),
        }
    return result


def _cell_record(
    cell: ET.Element,
    *,
    shared_strings: Sequence[str],
    max_cell_characters: int,
) -> dict[str, Any]:
    ref = cell.get("r")
    if not isinstance(ref, str):
        raise XlsxBoundedRowIntakeError("worksheet cell is missing coordinate")
    column_index = _column_index(ref)
    cell_type = cell.get("t")
    style_id = cell.get("s")
    formula_node = cell.find(f"{{{_MAIN_NS}}}f")
    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    raw_value = value_node.text if value_node is not None else None
    formula_text = formula_node.text if formula_node is not None else None
    if formula_text is not None and len(formula_text) > max_cell_characters:
        raise XlsxBoundedRowIntakeError("formula text exceeds cell character ceiling")
    if raw_value is not None and len(raw_value) > max_cell_characters:
        raise XlsxBoundedRowIntakeError("cell raw value exceeds character ceiling")

    display_text: str | None = None
    representation = "blank_or_missing_value"
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_MAIN_NS}}}is")
        display_text = (
            None
            if inline is None
            else "".join(item.text or "" for item in inline.iter(f"{{{_MAIN_NS}}}t"))
        )
        representation = "inline_string"
    elif raw_value is not None and cell_type == "s":
        try:
            index = int(raw_value)
        except ValueError as exc:
            raise XlsxBoundedRowIntakeError("shared-string cell index is not an integer") from exc
        if index < 0 or index >= len(shared_strings):
            raise XlsxBoundedRowIntakeError("shared-string index is outside sharedStrings.xml")
        display_text = shared_strings[index]
        representation = "shared_string"
    elif raw_value is not None and cell_type == "b":
        display_text = "TRUE" if raw_value == "1" else "FALSE" if raw_value == "0" else raw_value
        representation = "boolean_raw"
    elif raw_value is not None:
        display_text = raw_value
        representation = "raw_scalar"

    if display_text is not None and len(display_text) > max_cell_characters:
        raise XlsxBoundedRowIntakeError("cell text exceeds character ceiling")
    if formula_node is not None:
        representation = "formula_with_cached_value" if raw_value is not None else "formula_without_cached_value"

    return {
        "coordinate": ref,
        "column_index": column_index,
        "cell_type_attribute": cell_type,
        "style_id": style_id,
        "representation": representation,
        "display_text_structural_only": display_text,
        "raw_stored_value": raw_value,
        "formula_text": formula_text,
        "formula_evaluated": False,
        "number_format_interpreted": False,
        "scientific_semantics_interpreted": False,
    }


def _header_hints(value: str) -> list[str]:
    return [name for name, pattern in _HINT_PATTERNS if pattern.search(value)]


def _finite_number(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        number = float(stripped)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _profile_column(
    rows: Sequence[Sequence[str]],
    *,
    column_index: int,
    header_candidate: str,
    unique_cap: int,
) -> dict[str, Any]:
    blank_count = 0
    numeric_count = 0
    text_count = 0
    numeric_min: float | None = None
    numeric_max: float | None = None
    unique: set[str] = set()
    unique_capped = False
    nonblank_count = 0
    value_counts: Counter[str] = Counter()
    for row in rows:
        value = row[column_index] if column_index < len(row) else ""
        if value.strip() == "":
            blank_count += 1
            continue
        nonblank_count += 1
        if len(unique) < unique_cap:
            unique.add(value)
        elif value not in unique:
            unique_capped = True
        if len(value_counts) < unique_cap or value in value_counts:
            value_counts[value] += 1
        number = _finite_number(value)
        if number is None:
            text_count += 1
        else:
            numeric_count += 1
            numeric_min = number if numeric_min is None else min(numeric_min, number)
            numeric_max = number if numeric_max is None else max(numeric_max, number)
    unique_count: int | None = None if unique_capped else len(unique)
    most_common_count = value_counts.most_common(1)[0][1] if value_counts else 0
    return {
        "column_index": column_index,
        "header_candidate": header_candidate,
        "header_semantic_hints_proposal_only": _header_hints(header_candidate),
        "observed_data_row_count": len(rows),
        "nonblank_count": nonblank_count,
        "blank_count": blank_count,
        "numeric_count": numeric_count,
        "text_count": text_count,
        "numeric_min_structural_only": numeric_min,
        "numeric_max_structural_only": numeric_max,
        "unique_count": unique_count,
        "unique_count_capped": unique_capped,
        "constant_nonblank_signal": nonblank_count > 0 and unique_count == 1,
        "most_common_value_fraction": (
            most_common_count / nonblank_count if nonblank_count else None
        ),
        "row_values_are_independent_specimens": False,
    }


def _generic_table_projection(
    *,
    workbook_sha256: str,
    rows: list[dict[str, Any]],
    max_columns: int,
    preview_rows: int,
    unique_value_cap: int,
) -> dict[str, Any]:
    if len(rows) < 2:
        raise XlsxBoundedRowIntakeError("selected worksheet has fewer than two populated rows")
    max_seen = max(
        (cell["column_index"] for row in rows for cell in row["cells"]),
        default=-1,
    )
    width = max_seen + 1
    if width < 2 or width > max_columns:
        raise XlsxBoundedRowIntakeError("selected worksheet exposes unsupported table width")
    rectangular_rows: list[list[str]] = []
    for row in rows:
        values = [""] * width
        for cell in row["cells"]:
            text = cell["display_text_structural_only"]
            values[int(cell["column_index"])] = "" if text is None else str(text)
        rectangular_rows.append(values)
    header = rectangular_rows[0]
    data_rows = rectangular_rows[1:]
    profiles = [
        _profile_column(
            data_rows,
            column_index=index,
            header_candidate=header[index],
            unique_cap=unique_value_cap,
        )
        for index in range(width)
    ]
    return {
        "schema_version": XLSX_BOUNDED_ROW_INTAKE_SCHEMA_VERSION,
        "artifact_sha256": workbook_sha256,
        "artifact_size_bytes": None,
        "encoding": "xlsx_xml_structural_projection",
        "parsed_row_count": len(rectangular_rows),
        "data_row_count_if_first_row_is_header": len(data_rows),
        "minimum_column_count": width,
        "maximum_column_count": width,
        "rectangular": True,
        "row_width_counts": {str(width): len(rectangular_rows)},
        "first_row_header_candidate": header,
        "preview_rows": rectangular_rows[:preview_rows],
        "column_profiles": profiles,
        "accepted_for_analysis": False,
        "requires_domain_mapping": True,
        "structural_parse_is_scientific_validation": False,
        "measurement_semantics_interpreted": False,
        "units_interpreted": False,
        "sample_identity_inferred": False,
        "replicate_independence_inferred": False,
        "calibration_semantics_interpreted": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
        "limitations": [
            "The selected sheet projection is structural only; first-row labels are header candidates, not trusted scientific metadata.",
            "Excel styles and number formats are not interpreted as dates, units, categories, or scientific semantics.",
            "Rows and repeated values are never independent specimens by default.",
        ],
    }


def inspect_xlsx_sheet_rows(
    workbook_bytes: bytes,
    *,
    sheet_name: str,
    max_entries: int = DEFAULT_MAX_XLSX_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_XLSX_UNCOMPRESSED_BYTES,
    max_xml_member_bytes: int = DEFAULT_MAX_XML_MEMBER_BYTES,
    max_rows: int = DEFAULT_MAX_XLSX_ROWS,
    max_columns: int = DEFAULT_MAX_XLSX_COLUMNS,
    max_cells: int = DEFAULT_MAX_XLSX_CELLS,
    max_cell_characters: int = DEFAULT_MAX_XLSX_CELL_CHARACTERS,
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    unique_value_cap: int = DEFAULT_PROFILE_UNIQUE_VALUES,
) -> dict[str, Any]:
    """Inspect all bounded raw cells from one selected worksheet without evaluation."""
    for field, value in (
        ("max_entries", max_entries),
        ("max_uncompressed_bytes", max_uncompressed_bytes),
        ("max_xml_member_bytes", max_xml_member_bytes),
        ("max_rows", max_rows),
        ("max_columns", max_columns),
        ("max_cells", max_cells),
        ("max_cell_characters", max_cell_characters),
        ("preview_rows", preview_rows),
        ("unique_value_cap", unique_value_cap),
    ):
        _positive_int(value, field)
    if not isinstance(workbook_bytes, bytes) or not workbook_bytes:
        raise XlsxBoundedRowIntakeError("workbook_bytes must be non-empty exact bytes")
    if not isinstance(sheet_name, str) or not sheet_name.strip() or sheet_name != sheet_name.strip():
        raise XlsxBoundedRowIntakeError("sheet_name must be non-empty trimmed text")

    structural_inventory = inspect_xlsx_structure(
        workbook_bytes,
        max_entries=max_entries,
        max_uncompressed_bytes=max_uncompressed_bytes,
        max_xml_member_bytes=max_xml_member_bytes,
        preview_rows=1,
        preview_cells_per_row=max_columns,
    )
    workbook_sha = hashlib.sha256(workbook_bytes).hexdigest()
    if structural_inventory["workbook_sha256"] != workbook_sha:
        raise XlsxBoundedRowIntakeError("workbook SHA binding failed")

    try:
        archive = zipfile.ZipFile(io.BytesIO(workbook_bytes), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise XlsxBoundedRowIntakeError("artifact is not a valid XLSX/ZIP container") from exc
    with archive:
        infos_list = archive.infolist()
        if len(infos_list) > max_entries:
            raise XlsxBoundedRowIntakeError("XLSX member count exceeds bounded row-intake limit")
        infos: dict[str, zipfile.ZipInfo] = {}
        total_uncompressed = 0
        for info in infos_list:
            name = _safe_member_name(info.filename)
            if name in infos:
                raise XlsxBoundedRowIntakeError(f"duplicate XLSX member path: {name}")
            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed_bytes:
                raise XlsxBoundedRowIntakeError("XLSX total uncompressed size exceeds row-intake limit")
            infos[name] = info
        for required in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
            if required not in infos:
                raise XlsxBoundedRowIntakeError(f"XLSX is missing required member: {required}")
        sheet_map = _workbook_sheet_map(
            archive,
            infos,
            max_xml_member_bytes=max_xml_member_bytes,
        )
        if sheet_name not in sheet_map:
            raise XlsxBoundedRowIntakeError("selected worksheet does not exist")
        selected = sheet_map[sheet_name]
        member = selected["worksheet_member"]
        info = infos.get(member)
        if info is None:
            raise XlsxBoundedRowIntakeError("selected worksheet member is missing")
        shared = _load_shared_strings(
            archive,
            infos,
            max_xml_member_bytes=max_xml_member_bytes,
            max_cell_characters=max_cell_characters,
        )
        root = _safe_xml(
            _read_member(archive, info, max_bytes=max_xml_member_bytes),
            member,
        )

        merged_ranges = [
            item.get("ref")
            for parent in root.findall(f"{{{_MAIN_NS}}}mergeCells")
            for item in parent.findall(f"{{{_MAIN_NS}}}mergeCell")
            if isinstance(item.get("ref"), str)
        ]
        sheet_data = root.find(f"{{{_MAIN_NS}}}sheetData")
        rows: list[dict[str, Any]] = []
        cell_count = 0
        formula_cell_count = 0
        cached_formula_value_count = 0
        hidden_row_numbers: list[int] = []
        seen_row_numbers: set[int] = set()
        if sheet_data is not None:
            for row_node in sheet_data.findall(f"{{{_MAIN_NS}}}row"):
                if len(rows) >= max_rows:
                    raise XlsxBoundedRowIntakeError("worksheet exceeds row ceiling")
                raw_number = row_node.get("r")
                if not isinstance(raw_number, str) or not raw_number.isdigit() or int(raw_number) <= 0:
                    raise XlsxBoundedRowIntakeError("worksheet row number is invalid")
                row_number = int(raw_number)
                if row_number in seen_row_numbers:
                    raise XlsxBoundedRowIntakeError("worksheet contains duplicate row number")
                seen_row_numbers.add(row_number)
                hidden = row_node.get("hidden") in {"1", "true", "TRUE"}
                if hidden:
                    hidden_row_numbers.append(row_number)
                cells: list[dict[str, Any]] = []
                for cell_node in row_node.findall(f"{{{_MAIN_NS}}}c"):
                    cell_count += 1
                    if cell_count > max_cells:
                        raise XlsxBoundedRowIntakeError("worksheet exceeds cell ceiling")
                    record = _cell_record(
                        cell_node,
                        shared_strings=shared,
                        max_cell_characters=max_cell_characters,
                    )
                    if record["column_index"] >= max_columns:
                        raise XlsxBoundedRowIntakeError("worksheet exceeds column ceiling")
                    if record["formula_text"] is not None:
                        formula_cell_count += 1
                        if record["raw_stored_value"] is not None:
                            cached_formula_value_count += 1
                    cells.append(record)
                rows.append(
                    {
                        "row_number": row_number,
                        "hidden": hidden,
                        "cells": cells,
                    }
                )

    unsafe_reasons: list[str] = []
    if selected["sheet_state"] != "visible":
        unsafe_reasons.append("selected_sheet_is_hidden_or_very_hidden")
    if hidden_row_numbers:
        unsafe_reasons.append("selected_sheet_contains_hidden_rows")
    if merged_ranges:
        unsafe_reasons.append("selected_sheet_contains_merged_cells")
    if formula_cell_count:
        unsafe_reasons.append("selected_sheet_contains_formula_cells")
    if any(not row["cells"] for row in rows):
        unsafe_reasons.append("selected_sheet_contains_empty_explicit_rows")

    projection: dict[str, Any] | None = None
    projection_error: str | None = None
    if not unsafe_reasons:
        try:
            projection = _generic_table_projection(
                workbook_sha256=workbook_sha,
                rows=rows,
                max_columns=max_columns,
                preview_rows=preview_rows,
                unique_value_cap=unique_value_cap,
            )
        except XlsxBoundedRowIntakeError as exc:
            projection_error = str(exc)
            unsafe_reasons.append("generic_rectangular_projection_failed")

    report: dict[str, Any] = {
        "schema_version": XLSX_BOUNDED_ROW_INTAKE_SCHEMA_VERSION,
        "workbook_sha256": workbook_sha,
        "workbook_size_bytes": len(workbook_bytes),
        "sheet_name": sheet_name,
        "worksheet_member": member,
        "sheet_state": selected["sheet_state"],
        "row_count": len(rows),
        "cell_count": cell_count,
        "formula_cell_count": formula_cell_count,
        "cached_formula_value_count": cached_formula_value_count,
        "formula_evaluated": False,
        "number_formats_interpreted": False,
        "merged_cell_ranges": merged_ranges,
        "hidden_row_numbers": hidden_row_numbers,
        "rows": rows,
        "generic_table_projection_available": projection is not None,
        "generic_table_projection": projection,
        "projection_error": projection_error,
        "unsafe_for_naive_table_projection_reasons": sorted(set(unsafe_reasons)),
        "accepted_for_analysis": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
        "limitations": [
            "Formula text and cached values are exposed diagnostically only; formulas are never evaluated.",
            "Style IDs and raw scalar values are not interpreted as dates, units, categories, calibration, or scientific semantics.",
            "Merged cells, hidden rows/sheets, or formula cells block the generic rectangular projection.",
            "Row count is not an independent experimental-unit count.",
        ],
    }
    report["row_intake_report_sha256"] = _canonical_sha(report)
    return report


__all__ = [
    "DEFAULT_MAX_XLSX_CELL_CHARACTERS",
    "DEFAULT_MAX_XLSX_CELLS",
    "DEFAULT_MAX_XLSX_COLUMNS",
    "DEFAULT_MAX_XLSX_ROWS",
    "XLSX_BOUNDED_ROW_INTAKE_SCHEMA_VERSION",
    "XlsxBoundedRowIntakeError",
    "inspect_xlsx_sheet_rows",
]
