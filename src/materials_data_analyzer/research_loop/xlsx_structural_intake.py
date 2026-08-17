"""Fail-closed structural intake for acquired XLSX workbooks.

This module inspects exact workbook bytes without assigning materials-science semantics.
It is intentionally limited to archive integrity, workbook/sheet identity, dimensions, and
small cell previews useful for a later domain mapping. A structurally valid workbook is
*not* accepted as scientific evidence merely because it parses successfully.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from .kernel import ResearchLoopError

XLSX_STRUCTURAL_INTAKE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_XLSX_ENTRIES = 4000
DEFAULT_MAX_XLSX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_XML_MEMBER_BYTES = 64 * 1024 * 1024
DEFAULT_PREVIEW_ROWS = 3
DEFAULT_PREVIEW_CELLS_PER_ROW = 32

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


class XlsxStructuralIntakeError(ResearchLoopError):
    """Raised when XLSX structural intake cannot be performed safely."""


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XlsxStructuralIntakeError(f"{field} must be a positive integer")
    return value


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise XlsxStructuralIntakeError("XLSX member path is not safe POSIX")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise XlsxStructuralIntakeError("XLSX member path escapes the workbook root")
    return path.as_posix()


def _safe_xml(raw: bytes, *, field: str) -> ET.Element:
    upper = raw[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise XlsxStructuralIntakeError(f"{field} contains prohibited DTD/entity declarations")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise XlsxStructuralIntakeError(f"{field} is malformed XML") from exc


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    max_bytes: int,
) -> bytes:
    if info.flag_bits & 0x1:
        raise XlsxStructuralIntakeError(f"encrypted XLSX member is not allowed: {info.filename}")
    if info.file_size > max_bytes:
        raise XlsxStructuralIntakeError(
            f"XLSX member exceeds structural intake byte ceiling: {info.filename}"
        )
    with archive.open(info, "r") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes or len(raw) != info.file_size:
        raise XlsxStructuralIntakeError(
            f"XLSX member size is inconsistent or exceeds limit: {info.filename}"
        )
    return raw


def _column_index(cell_ref: str) -> int:
    match = _CELL_REF_RE.fullmatch(cell_ref)
    if not match:
        raise XlsxStructuralIntakeError(f"invalid worksheet cell reference: {cell_ref!r}")
    letters = match.group(1)
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def _shared_strings(
    archive: zipfile.ZipFile,
    infos: Mapping[str, zipfile.ZipInfo],
    *,
    max_xml_member_bytes: int,
) -> list[str]:
    info = infos.get("xl/sharedStrings.xml")
    if info is None:
        return []
    root = _safe_xml(
        _read_member(archive, info, max_bytes=max_xml_member_bytes),
        field="xl/sharedStrings.xml",
    )
    strings: list[str] = []
    for si in root.findall(f"{{{_MAIN_NS}}}si"):
        text = "".join(node.text or "" for node in si.iter(f"{{{_MAIN_NS}}}t"))
        strings.append(text)
    return strings


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str | None:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        node = cell.find(f"{{{_MAIN_NS}}}is")
        if node is None:
            return None
        return "".join(item.text or "" for item in node.iter(f"{{{_MAIN_NS}}}t"))
    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return None
    value = value_node.text
    if cell_type == "s":
        try:
            index = int(value)
        except ValueError as exc:
            raise XlsxStructuralIntakeError("shared-string cell index is not an integer") from exc
        if index < 0 or index >= len(shared_strings):
            raise XlsxStructuralIntakeError("shared-string cell index is outside sharedStrings.xml")
        return shared_strings[index]
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE" if value == "0" else value
    return value


def _worksheet_preview(
    raw: bytes,
    shared_strings: list[str],
    *,
    preview_rows: int,
    preview_cells_per_row: int,
) -> dict[str, Any]:
    root = _safe_xml(raw, field="worksheet")
    dimension_node = root.find(f"{{{_MAIN_NS}}}dimension")
    dimension = dimension_node.get("ref") if dimension_node is not None else None
    previews: list[dict[str, Any]] = []
    sheet_data = root.find(f"{{{_MAIN_NS}}}sheetData")
    if sheet_data is not None:
        for row in sheet_data.findall(f"{{{_MAIN_NS}}}row")[:preview_rows]:
            values: dict[int, str | None] = {}
            for cell in row.findall(f"{{{_MAIN_NS}}}c")[:preview_cells_per_row]:
                ref = cell.get("r")
                if not isinstance(ref, str):
                    continue
                values[_column_index(ref)] = _cell_text(cell, shared_strings)
            previews.append(
                {
                    "row_number": int(row.get("r", "0")) if str(row.get("r", "0")).isdigit() else None,
                    "cells": [
                        {"column_index": index, "value": values[index]}
                        for index in sorted(values)
                    ],
                }
            )
    return {"dimension": dimension, "preview_rows": previews}


def inspect_xlsx_structure(
    workbook_bytes: bytes,
    *,
    max_entries: int = DEFAULT_MAX_XLSX_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_XLSX_UNCOMPRESSED_BYTES,
    max_xml_member_bytes: int = DEFAULT_MAX_XML_MEMBER_BYTES,
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    preview_cells_per_row: int = DEFAULT_PREVIEW_CELLS_PER_ROW,
) -> dict[str, Any]:
    """Inspect exact XLSX bytes and return a bounded, non-semantic workbook inventory."""
    if not isinstance(workbook_bytes, bytes) or not workbook_bytes:
        raise XlsxStructuralIntakeError("workbook_bytes must be non-empty exact bytes")
    max_entries = _positive_int(max_entries, "max_entries")
    max_uncompressed_bytes = _positive_int(max_uncompressed_bytes, "max_uncompressed_bytes")
    max_xml_member_bytes = _positive_int(max_xml_member_bytes, "max_xml_member_bytes")
    preview_rows = _positive_int(preview_rows, "preview_rows")
    preview_cells_per_row = _positive_int(preview_cells_per_row, "preview_cells_per_row")

    try:
        archive = zipfile.ZipFile(io.BytesIO(workbook_bytes), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise XlsxStructuralIntakeError("artifact is not a valid XLSX/ZIP container") from exc
    with archive:
        infos_list = archive.infolist()
        if not infos_list or len(infos_list) > max_entries:
            raise XlsxStructuralIntakeError("XLSX member count exceeds structural intake limit")
        infos: dict[str, zipfile.ZipInfo] = {}
        total_uncompressed = 0
        for info in infos_list:
            name = _safe_member_name(info.filename)
            if name in infos:
                raise XlsxStructuralIntakeError(f"duplicate XLSX member path: {name}")
            if info.flag_bits & 0x1:
                raise XlsxStructuralIntakeError(f"encrypted XLSX member is not allowed: {name}")
            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed_bytes:
                raise XlsxStructuralIntakeError("XLSX total uncompressed size exceeds intake limit")
            infos[name] = info

        for required in ("[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
            if required not in infos:
                raise XlsxStructuralIntakeError(f"XLSX is missing required member: {required}")

        workbook_root = _safe_xml(
            _read_member(archive, infos["xl/workbook.xml"], max_bytes=max_xml_member_bytes),
            field="xl/workbook.xml",
        )
        rels_root = _safe_xml(
            _read_member(
                archive,
                infos["xl/_rels/workbook.xml.rels"],
                max_bytes=max_xml_member_bytes,
            ),
            field="xl/_rels/workbook.xml.rels",
        )
        rel_targets: dict[str, str] = {}
        for rel in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            rel_id = rel.get("Id")
            target = rel.get("Target")
            mode = rel.get("TargetMode")
            if not isinstance(rel_id, str) or not isinstance(target, str):
                raise XlsxStructuralIntakeError("workbook relationship is missing Id/Target")
            if mode == "External":
                continue
            if target.startswith("/"):
                normalized = _safe_member_name(target.lstrip("/"))
            else:
                normalized = _safe_member_name(str(PurePosixPath("xl") / target))
            if rel_id in rel_targets:
                raise XlsxStructuralIntakeError(f"duplicate workbook relationship Id: {rel_id}")
            rel_targets[rel_id] = normalized

        shared = _shared_strings(
            archive,
            infos,
            max_xml_member_bytes=max_xml_member_bytes,
        )
        sheets_node = workbook_root.find(f"{{{_MAIN_NS}}}sheets")
        if sheets_node is None:
            raise XlsxStructuralIntakeError("workbook has no sheets collection")
        sheet_inventory: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for index, sheet in enumerate(sheets_node.findall(f"{{{_MAIN_NS}}}sheet")):
            name = sheet.get("name")
            rel_id = sheet.get(f"{{{_REL_NS}}}id")
            if not isinstance(name, str) or not name:
                raise XlsxStructuralIntakeError("worksheet has an invalid name")
            if name in seen_names:
                raise XlsxStructuralIntakeError(f"duplicate worksheet name: {name}")
            seen_names.add(name)
            if not isinstance(rel_id, str) or rel_id not in rel_targets:
                raise XlsxStructuralIntakeError(f"worksheet {name!r} has no internal relationship")
            member = rel_targets[rel_id]
            info = infos.get(member)
            if info is None:
                raise XlsxStructuralIntakeError(
                    f"worksheet {name!r} relationship target is missing: {member}"
                )
            preview = _worksheet_preview(
                _read_member(archive, info, max_bytes=max_xml_member_bytes),
                shared,
                preview_rows=preview_rows,
                preview_cells_per_row=preview_cells_per_row,
            )
            sheet_inventory.append(
                {
                    "sheet_index": index,
                    "sheet_name": name,
                    "worksheet_member": member,
                    **preview,
                }
            )

    return {
        "schema_version": XLSX_STRUCTURAL_INTAKE_SCHEMA_VERSION,
        "workbook_sha256": hashlib.sha256(workbook_bytes).hexdigest(),
        "workbook_size_bytes": len(workbook_bytes),
        "zip_member_count": len(infos_list),
        "zip_total_uncompressed_bytes": total_uncompressed,
        "sheet_count": len(sheet_inventory),
        "sheets": sheet_inventory,
        "shared_string_count": len(shared),
        "accepted_for_analysis": False,
        "scientific_status_changed": False,
        "requires_domain_mapping": True,
        "structural_parse_is_scientific_validation": False,
        "limitations": [
            "Cell previews are structural inventory only and do not establish column semantics or units.",
            "Workbook parsing does not establish sample identity, calibration, machine identity, material state, or replicate independence.",
            "A domain-specific mapping and scientific intake contract must accept the workbook before analysis."
        ],
    }


def structural_intake_acquired_xlsx(
    *,
    receipt: Mapping[str, Any],
    package_directory: str | Path,
    evidence_gap: object,
) -> dict[str, Any]:
    """Inspect one acquired XLSX package while preserving the acquisition SHA binding."""
    artifact_path = receipt.get("artifact_path")
    expected_sha = receipt.get("artifact_sha256")
    if not isinstance(artifact_path, str) or Path(artifact_path).suffix.lower() != ".xlsx":
        raise XlsxStructuralIntakeError("receipt artifact_path must identify an .xlsx artifact")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise XlsxStructuralIntakeError("receipt artifact_sha256 is invalid")
    relative = PurePosixPath(artifact_path)
    if relative.is_absolute() or "." in relative.parts or ".." in relative.parts or "\\" in artifact_path:
        raise XlsxStructuralIntakeError("receipt artifact_path is not safe relative POSIX")
    root = Path(package_directory).resolve(strict=True)
    target = root.joinpath(*relative.parts)
    if target.is_symlink():
        raise XlsxStructuralIntakeError("acquired XLSX artifact may not be a symlink")
    resolved = target.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise XlsxStructuralIntakeError("acquired XLSX resolves outside package directory") from exc
    raw = resolved.read_bytes()
    observed_sha = hashlib.sha256(raw).hexdigest()
    if observed_sha != expected_sha:
        raise XlsxStructuralIntakeError("acquired XLSX no longer matches receipt SHA-256")
    structure = inspect_xlsx_structure(raw)
    return {
        "decision": "requires_domain_scientific_mapping",
        "accepted_for_analysis": False,
        "scientific_status_changed": False,
        "artifact_sha256": observed_sha,
        "package_directory": root.as_posix(),
        "evidence_gap": evidence_gap,
        "workbook_structure": structure,
        "reason_codes": ["structural_intake_complete_domain_semantics_unresolved"],
    }


__all__ = [
    "DEFAULT_MAX_XML_MEMBER_BYTES",
    "DEFAULT_MAX_XLSX_ENTRIES",
    "DEFAULT_MAX_XLSX_UNCOMPRESSED_BYTES",
    "XLSX_STRUCTURAL_INTAKE_SCHEMA_VERSION",
    "XlsxStructuralIntakeError",
    "inspect_xlsx_structure",
    "structural_intake_acquired_xlsx",
]
