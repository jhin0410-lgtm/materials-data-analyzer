"""Exact-byte structural intake for binary spreadsheet candidates.

The intake layer is intentionally weaker than scientific interpretation.  It binds a
candidate workbook to an independently supplied SHA-256 and inspects only container /
worksheet structure under strict byte budgets.  It does not infer sample identity,
units, replicate independence, measurement semantics, or scientific support.
"""
from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from .kernel import ResearchLoopError

BINARY_WORKBOOK_STRUCTURAL_INTAKE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_XLSX_MEMBERS = 4096
DEFAULT_MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_XML_MEMBER_BYTES = 32 * 1024 * 1024
_OLE_COMPOUND_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
_SHA256_HEX = frozenset("0123456789abcdef")


class BinaryWorkbookStructuralIntakeError(ResearchLoopError):
    """Raised when a workbook cannot preserve its exact-byte structural boundary."""


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in _SHA256_HEX for char in value)
    ):
        raise BinaryWorkbookStructuralIntakeError(f"{field} must be lowercase SHA-256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BinaryWorkbookStructuralIntakeError(f"{field} must be a positive integer")
    return value


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise BinaryWorkbookStructuralIntakeError(f"could not read workbook: {path}") from exc
    return size, digest.hexdigest()


def _safe_member_name(name: str) -> str:
    if not name or name != name.strip() or "\\" in name or "\x00" in name:
        raise BinaryWorkbookStructuralIntakeError("XLSX member name is unsafe")
    member = PurePosixPath(name)
    if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
        raise BinaryWorkbookStructuralIntakeError("XLSX member path may not escape archive root")
    return member.as_posix()


def _read_bounded_xml(
    archive: zipfile.ZipFile,
    info_by_name: dict[str, zipfile.ZipInfo],
    name: str,
    *,
    max_xml_member_bytes: int,
) -> bytes:
    info = info_by_name.get(name)
    if info is None or info.is_dir():
        raise BinaryWorkbookStructuralIntakeError(f"required XLSX XML member is missing: {name}")
    if info.file_size > max_xml_member_bytes:
        raise BinaryWorkbookStructuralIntakeError(f"XLSX XML member exceeds byte budget: {name}")
    with archive.open(info, "r") as stream:
        body = stream.read(max_xml_member_bytes + 1)
    if len(body) != info.file_size or len(body) > max_xml_member_bytes:
        raise BinaryWorkbookStructuralIntakeError(f"XLSX XML member expanded beyond declared size: {name}")
    return body


def _xml_root(body: bytes, field: str) -> ET.Element:
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise BinaryWorkbookStructuralIntakeError(f"invalid XML in {field}") from exc


def _worksheet_path(target: str) -> str:
    if not target or target != target.strip() or "\\" in target:
        raise BinaryWorkbookStructuralIntakeError("XLSX worksheet relationship target is unsafe")
    raw = PurePosixPath(target)
    if raw.is_absolute() or ".." in raw.parts:
        raise BinaryWorkbookStructuralIntakeError("XLSX worksheet relationship escapes workbook root")
    if raw.parts and raw.parts[0] == "xl":
        return raw.as_posix()
    return (PurePosixPath("xl") / raw).as_posix()


def inspect_xlsx_workbook_structure(
    workbook_path: str | Path,
    *,
    expected_sha256: str,
    max_members: int = DEFAULT_MAX_XLSX_MEMBERS,
    max_total_uncompressed_bytes: int = DEFAULT_MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES,
    max_xml_member_bytes: int = DEFAULT_MAX_XML_MEMBER_BYTES,
) -> dict[str, Any]:
    """Inspect a SHA-pinned XLSX container without interpreting cell values."""
    expected_sha = _sha(expected_sha256, "expected_sha256")
    max_members = _positive_int(max_members, "max_members")
    max_total = _positive_int(max_total_uncompressed_bytes, "max_total_uncompressed_bytes")
    max_xml = _positive_int(max_xml_member_bytes, "max_xml_member_bytes")
    path = Path(workbook_path).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".xlsx" or not path.is_file():
        raise BinaryWorkbookStructuralIntakeError("XLSX candidate must be an existing .xlsx file")
    size, actual_sha = _hash_file(path)
    if actual_sha != expected_sha:
        raise BinaryWorkbookStructuralIntakeError("XLSX bytes differ from expected SHA-256")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > max_members:
                raise BinaryWorkbookStructuralIntakeError("XLSX member-count budget exceeded")
            info_by_name: dict[str, zipfile.ZipInfo] = {}
            total = 0
            for info in infos:
                name = _safe_member_name(info.filename)
                if name in info_by_name:
                    raise BinaryWorkbookStructuralIntakeError("XLSX contains duplicate normalized member names")
                if info.flag_bits & 0x1:
                    raise BinaryWorkbookStructuralIntakeError("encrypted XLSX members are not allowed")
                mode = (info.external_attr >> 16) & 0o170000
                if stat.S_ISLNK(mode):
                    raise BinaryWorkbookStructuralIntakeError("XLSX symlink members are not allowed")
                if info.file_size < 0:
                    raise BinaryWorkbookStructuralIntakeError("XLSX member size is invalid")
                total += info.file_size
                if total > max_total:
                    raise BinaryWorkbookStructuralIntakeError("XLSX expanded-size budget exceeded")
                info_by_name[name] = info

            content_types = _read_bounded_xml(
                archive, info_by_name, "[Content_Types].xml", max_xml_member_bytes=max_xml
            )
            lower_types = content_types.lower()
            if b"vbaproject" in lower_types or b"macroenabled" in lower_types:
                raise BinaryWorkbookStructuralIntakeError("macro-enabled workbook content is not allowed")
            workbook_xml = _read_bounded_xml(
                archive, info_by_name, "xl/workbook.xml", max_xml_member_bytes=max_xml
            )
            rels_xml = _read_bounded_xml(
                archive, info_by_name, "xl/_rels/workbook.xml.rels", max_xml_member_bytes=max_xml
            )
            workbook_root = _xml_root(workbook_xml, "xl/workbook.xml")
            rels_root = _xml_root(rels_xml, "xl/_rels/workbook.xml.rels")

            rels: dict[str, str] = {}
            for rel in rels_root:
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target")
                rel_type = rel.attrib.get("Type", "")
                if rid and target and rel_type.endswith("/worksheet"):
                    if rid in rels:
                        raise BinaryWorkbookStructuralIntakeError("duplicate worksheet relationship id")
                    rels[rid] = _worksheet_path(target)

            office_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            relationship_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            sheets_parent = workbook_root.find(f"{{{office_ns}}}sheets")
            if sheets_parent is None:
                raise BinaryWorkbookStructuralIntakeError("XLSX workbook has no sheets collection")
            sheets: list[dict[str, Any]] = []
            seen_sheet_names: set[str] = set()
            for sheet in sheets_parent.findall(f"{{{office_ns}}}sheet"):
                name = sheet.attrib.get("name")
                rid = sheet.attrib.get(relationship_attr)
                sheet_id = sheet.attrib.get("sheetId")
                if not name or not rid or not sheet_id:
                    raise BinaryWorkbookStructuralIntakeError("XLSX sheet metadata is incomplete")
                if name in seen_sheet_names:
                    raise BinaryWorkbookStructuralIntakeError("XLSX sheet names must be unique")
                seen_sheet_names.add(name)
                worksheet_name = rels.get(rid)
                if worksheet_name is None:
                    raise BinaryWorkbookStructuralIntakeError("XLSX worksheet relationship is missing")
                worksheet_xml = _read_bounded_xml(
                    archive, info_by_name, worksheet_name, max_xml_member_bytes=max_xml
                )
                worksheet_root = _xml_root(worksheet_xml, worksheet_name)
                dimension = worksheet_root.find(f"{{{office_ns}}}dimension")
                rows = worksheet_root.findall(f".//{{{office_ns}}}row")
                cells = worksheet_root.findall(f".//{{{office_ns}}}c")
                formulas = worksheet_root.findall(f".//{{{office_ns}}}f")
                sheets.append(
                    {
                        "name": name,
                        "sheet_id": sheet_id,
                        "worksheet_member": worksheet_name,
                        "dimension_ref": None if dimension is None else dimension.attrib.get("ref"),
                        "row_element_count": len(rows),
                        "cell_element_count": len(cells),
                        "formula_element_count": len(formulas),
                    }
                )
    except zipfile.BadZipFile as exc:
        raise BinaryWorkbookStructuralIntakeError("candidate is not a valid XLSX ZIP container") from exc

    return {
        "schema_version": BINARY_WORKBOOK_STRUCTURAL_INTAKE_SCHEMA_VERSION,
        "artifact_path": str(path),
        "artifact_size_bytes": size,
        "artifact_sha256": actual_sha,
        "format": "xlsx_open_xml",
        "sheet_count": len(sheets),
        "sheets": sheets,
        "container_member_count": len(infos),
        "container_total_uncompressed_bytes": total,
        "exact_byte_binding_verified": True,
        "macro_enabled_content_allowed": False,
        "cell_values_interpreted": False,
        "formulas_evaluated": False,
        "sample_identity_inferred": False,
        "measurement_semantics_interpreted": False,
        "accepted_for_analysis": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }


def inspect_legacy_xls_binding(
    workbook_path: str | Path,
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    """Bind a legacy XLS candidate without pretending stdlib can decode BIFF semantics."""
    expected_sha = _sha(expected_sha256, "expected_sha256")
    path = Path(workbook_path).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".xls" or not path.is_file():
        raise BinaryWorkbookStructuralIntakeError("XLS candidate must be an existing .xls file")
    size, actual_sha = _hash_file(path)
    if actual_sha != expected_sha:
        raise BinaryWorkbookStructuralIntakeError("XLS bytes differ from expected SHA-256")
    try:
        prefix = path.read_bytes()[: len(_OLE_COMPOUND_MAGIC)]
    except OSError as exc:
        raise BinaryWorkbookStructuralIntakeError("could not inspect XLS compound-file signature") from exc
    if prefix != _OLE_COMPOUND_MAGIC:
        raise BinaryWorkbookStructuralIntakeError("legacy XLS candidate lacks OLE compound-file signature")
    return {
        "schema_version": BINARY_WORKBOOK_STRUCTURAL_INTAKE_SCHEMA_VERSION,
        "artifact_path": str(path),
        "artifact_size_bytes": size,
        "artifact_sha256": actual_sha,
        "format": "legacy_xls_ole_compound",
        "exact_byte_binding_verified": True,
        "binary_structure_decoded": False,
        "cell_values_interpreted": False,
        "sample_identity_inferred": False,
        "measurement_semantics_interpreted": False,
        "accepted_for_analysis": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
        "limitation": "Legacy BIFF workbook structure remains hash-bound only until a separately reviewed decoder is authorized.",
    }


__all__ = [
    "BINARY_WORKBOOK_STRUCTURAL_INTAKE_SCHEMA_VERSION",
    "BinaryWorkbookStructuralIntakeError",
    "inspect_legacy_xls_binding",
    "inspect_xlsx_workbook_structure",
]
