"""Row-preserving reviewed intake for the exact Zenodo 20503603 IN625 tensile workbook.

V1 deliberately required every selected measurement field to be numeric.  The live source
showed that this is too strong for evidence intake: a time-indexed source row can legitimately
contain a blank or non-numeric value in one selected field.  V2 therefore preserves every
header-scoped, time-indexed source row and records numeric completeness explicitly instead of
silently dropping, imputing, or fabricating a value.

This remains an evidence-intake boundary, not a scientific validation boundary.  Incomplete
rows are retained as data-quality evidence.  No row or parallel-test block is declared an
independent specimen, and no cross-source/NIST comparability, model validity, hypothesis truth,
or positive closeout is established here.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, TextIO
from xml.etree import ElementTree as ET

from .kernel import ResearchLoopError
from .xlsx_structural_intake import (
    XlsxStructuralIntakeError,
    inspect_xlsx_structure,
    resolve_xlsx_relationship_target,
)

SCHEMA_VERSION = "2.0"
POLICY_SCHEMA_VERSION = "1.0"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
_MAX_ANOMALY_EXAMPLES = 64
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class In625TensileReviewedIntakeV2Error(ResearchLoopError):
    """Raised when exact row-preserving tensile intake cannot be reconstructed safely."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise In625TensileReviewedIntakeV2Error(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: Path, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625TensileReviewedIntakeV2Error(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise In625TensileReviewedIntakeV2Error(f"{field} root must be an object")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625TensileReviewedIntakeV2Error(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise In625TensileReviewedIntakeV2Error(f"{field} must be non-empty text")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise In625TensileReviewedIntakeV2Error(f"{field} must be a positive integer")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise In625TensileReviewedIntakeV2Error(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _canonical_sha(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise In625TensileReviewedIntakeV2Error(
            "tensile intake manifest must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _safe_member_name(name: str) -> str:
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise In625TensileReviewedIntakeV2Error(
            "XLSX member path is not safe POSIX"
        )
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise In625TensileReviewedIntakeV2Error(
            "XLSX member path escapes workbook root"
        )
    return path.as_posix()


def _safe_xml(raw: bytes, field: str) -> ET.Element:
    upper = raw[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise In625TensileReviewedIntakeV2Error(
            f"{field} contains prohibited DTD/entity declarations"
        )
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise In625TensileReviewedIntakeV2Error(f"{field} is malformed XML") from exc


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    max_bytes: int,
) -> bytes:
    if info.flag_bits & 0x1:
        raise In625TensileReviewedIntakeV2Error(
            f"encrypted XLSX member is not allowed: {info.filename}"
        )
    if info.file_size > max_bytes:
        raise In625TensileReviewedIntakeV2Error(
            f"XLSX member exceeds reviewed byte ceiling: {info.filename}"
        )
    with archive.open(info, "r") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) != info.file_size or len(raw) > max_bytes:
        raise In625TensileReviewedIntakeV2Error(
            f"XLSX member size drifted: {info.filename}"
        )
    return raw


def _column_index(cell_ref: str) -> int:
    match = _CELL_REF_RE.fullmatch(cell_ref)
    if match is None:
        raise In625TensileReviewedIntakeV2Error(
            f"invalid worksheet cell reference: {cell_ref!r}"
        )
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def _shared_strings(
    archive: zipfile.ZipFile,
    infos: Mapping[str, zipfile.ZipInfo],
) -> list[str]:
    info = infos.get("xl/sharedStrings.xml")
    if info is None:
        return []
    root = _safe_xml(
        _read_member(archive, info, max_bytes=32 * 1024 * 1024),
        "sharedStrings",
    )
    result: list[str] = []
    for item in root.findall(f"{{{_MAIN_NS}}}si"):
        value = "".join(
            node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")
        )
        if len(value) > 16384:
            raise In625TensileReviewedIntakeV2Error(
                "shared string exceeds reviewed character ceiling"
            )
        result.append(value)
    return result


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    if cell.find(f"{{{_MAIN_NS}}}f") is not None:
        raise In625TensileReviewedIntakeV2Error(
            "formula cells are prohibited in reviewed tensile row intake"
        )
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        node = cell.find(f"{{{_MAIN_NS}}}is")
        value = "" if node is None else "".join(
            item.text or "" for item in node.iter(f"{{{_MAIN_NS}}}t")
        )
    else:
        node = cell.find(f"{{{_MAIN_NS}}}v")
        raw = "" if node is None or node.text is None else node.text
        if cell_type == "s" and raw:
            try:
                index = int(raw)
            except ValueError as exc:
                raise In625TensileReviewedIntakeV2Error(
                    "shared-string index is not an integer"
                ) from exc
            if index < 0 or index >= len(shared):
                raise In625TensileReviewedIntakeV2Error(
                    "shared-string index is outside sharedStrings.xml"
                )
            value = shared[index]
        elif cell_type == "b":
            value = "TRUE" if raw == "1" else "FALSE" if raw == "0" else raw
        else:
            value = raw
    if len(value) > 16384:
        raise In625TensileReviewedIntakeV2Error(
            "cell value exceeds reviewed character ceiling"
        )
    return value


def _row_values(row: ET.Element, shared: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for cell in row.findall(f"{{{_MAIN_NS}}}c"):
        ref = cell.get("r")
        if not isinstance(ref, str):
            raise In625TensileReviewedIntakeV2Error(
                "worksheet cell is missing coordinate"
            )
        index = _column_index(ref)
        if index in result:
            raise In625TensileReviewedIntakeV2Error(
                "worksheet row contains duplicate column coordinate"
            )
        result[index] = _cell_text(cell, shared)
    return result


def _sheet_members(
    archive: zipfile.ZipFile,
    infos: Mapping[str, zipfile.ZipInfo],
) -> dict[str, str]:
    workbook = _safe_xml(
        _read_member(
            archive,
            infos["xl/workbook.xml"],
            max_bytes=8 * 1024 * 1024,
        ),
        "xl/workbook.xml",
    )
    rels = _safe_xml(
        _read_member(
            archive,
            infos["xl/_rels/workbook.xml.rels"],
            max_bytes=8 * 1024 * 1024,
        ),
        "xl/_rels/workbook.xml.rels",
    )
    targets: dict[str, str] = {}
    for rel in rels.findall(f"{{{_PKG_REL_NS}}}Relationship"):
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if not isinstance(rel_id, str) or not isinstance(target, str):
            raise In625TensileReviewedIntakeV2Error(
                "workbook relationship is malformed"
            )
        if rel.get("TargetMode") == "External":
            continue
        if rel_id in targets:
            raise In625TensileReviewedIntakeV2Error(
                f"duplicate workbook relationship Id: {rel_id}"
            )
        try:
            targets[rel_id] = resolve_xlsx_relationship_target(
                "xl/workbook.xml",
                target,
            )
        except XlsxStructuralIntakeError as exc:
            raise In625TensileReviewedIntakeV2Error(
                f"workbook relationship target is unsafe: {target!r}"
            ) from exc

    sheets_node = workbook.find(f"{{{_MAIN_NS}}}sheets")
    if sheets_node is None:
        raise In625TensileReviewedIntakeV2Error(
            "workbook has no worksheet collection"
        )
    result: dict[str, str] = {}
    for sheet in sheets_node.findall(f"{{{_MAIN_NS}}}sheet"):
        name = sheet.get("name")
        rel_id = sheet.get(f"{{{_REL_NS}}}id")
        if (
            not isinstance(name, str)
            or not isinstance(rel_id, str)
            or rel_id not in targets
        ):
            raise In625TensileReviewedIntakeV2Error(
                "worksheet identity is malformed"
            )
        if name in result:
            raise In625TensileReviewedIntakeV2Error(
                f"duplicate worksheet name: {name}"
            )
        member = targets[rel_id]
        if member not in infos:
            raise In625TensileReviewedIntakeV2Error(
                f"worksheet member is missing: {member}"
            )
        result[name] = member
    return result


def _number_state(
    raw: str,
    *,
    decimal_separator: str,
    field: str,
) -> tuple[str, float | None]:
    stripped = raw.strip()
    if not stripped:
        return "blank", None
    normalized = (
        stripped.replace(decimal_separator, ".")
        if decimal_separator != "."
        else stripped
    )
    try:
        value = float(normalized)
    except ValueError:
        return "non_numeric", None
    if not math.isfinite(value):
        raise In625TensileReviewedIntakeV2Error(
            f"{field} contains non-finite numeric text"
        )
    return "numeric", value


def _validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    if (
        policy.get("schema_version") != POLICY_SCHEMA_VERSION
        or policy.get("source_id") != EXPECTED_SOURCE_ID
    ):
        raise In625TensileReviewedIntakeV2Error(
            "unsupported IN625 tensile reviewed-intake policy"
        )
    workbook = _mapping(policy.get("workbook"), "policy.workbook")
    documentation = _mapping(
        policy.get("documentation"),
        "policy.documentation",
    )
    sheets = _mapping(policy.get("sheets"), "policy.sheets")
    boundaries = _mapping(
        policy.get("scientific_boundaries"),
        "policy.scientific_boundaries",
    )
    if len(sheets) != 7:
        raise In625TensileReviewedIntakeV2Error(
            "reviewed tensile policy must bind exactly seven worksheets"
        )
    for key in (
        "parallel_tests_imply_statistical_independence",
        "direct_nist_condition_comparability_established",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "positive_scientific_closeout_established",
        "automatic_scientific_promotion",
    ):
        if boundaries.get(key) is not False:
            raise In625TensileReviewedIntakeV2Error(
                f"scientific boundary {key} must remain false"
            )
    header = policy.get("measurement_header")
    columns = _mapping(
        policy.get("reviewed_numeric_columns"),
        "policy.reviewed_numeric_columns",
    )
    if (
        not isinstance(header, list)
        or len(header) != 12
        or not all(isinstance(item, str) for item in header)
    ):
        raise In625TensileReviewedIntakeV2Error(
            "reviewed measurement header must contain exactly 12 strings"
        )
    normalized_columns: dict[str, int] = {}
    for name, index in columns.items():
        if (
            not isinstance(name, str)
            or isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index >= len(header)
        ):
            raise In625TensileReviewedIntakeV2Error(
                "reviewed numeric-column mapping is malformed"
            )
        normalized_columns[name] = index
    return {
        "workbook_sha256": _sha(
            workbook.get("sha256"),
            "policy workbook SHA-256",
        ),
        "workbook_size_bytes": _positive_int(
            workbook.get("size_bytes"),
            "policy workbook size",
        ),
        "readme_sha256": _sha(
            documentation.get("sha256"),
            "policy README SHA-256",
        ),
        "readme_size_bytes": _positive_int(
            documentation.get("size_bytes"),
            "policy README size",
        ),
        "readme_encoding": _text(
            documentation.get("encoding"),
            "policy README encoding",
        ),
        "header": list(header),
        "columns": normalized_columns,
        "sheets": {
            str(key): dict(_mapping(value, f"policy.sheets.{key}"))
            for key, value in sheets.items()
        },
        "decimal_separator": _text(
            policy.get("decimal_separator"),
            "policy decimal_separator",
        ),
        "metadata_block_start_label": _text(
            policy.get("metadata_block_start_label"),
            "metadata block start label",
        ),
        "specimen_label": _text(
            policy.get("specimen_label"),
            "specimen label",
        ),
        "max_parallel_tests_per_sheet": _positive_int(
            policy.get("max_parallel_tests_per_sheet"),
            "max_parallel_tests_per_sheet",
        ),
        "expected_total_measurement_rows": _positive_int(
            policy.get("expected_total_measurement_rows"),
            "expected_total_measurement_rows",
        ),
        "max_measurement_rows_total": _positive_int(
            policy.get("max_measurement_rows_total"),
            "max_measurement_rows_total",
        ),
        "max_cells_total": _positive_int(
            policy.get("max_cells_total"),
            "max_cells_total",
        ),
    }


def _finalize_block(block: dict[str, Any], last_row: int | None) -> None:
    if block["measurement_row_count"] <= 0 or last_row is None:
        raise In625TensileReviewedIntakeV2Error(
            "reviewed tensile block contains no time-indexed source rows"
        )
    block["measurement_end_excel_row"] = last_row


def _update_quality_counter(
    quality: dict[str, dict[str, int]],
    field: str,
    state: str,
) -> None:
    bucket = quality[field]
    bucket[state] += 1


def _parse_sheet(
    *,
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    shared: list[str],
    sheet_name: str,
    semantics: Mapping[str, Any],
    policy: Mapping[str, Any],
    row_sink: TextIO | None,
    running: dict[str, Any],
) -> dict[str, Any]:
    if info.file_size > 64 * 1024 * 1024:
        raise In625TensileReviewedIntakeV2Error(
            "worksheet exceeds reviewed XML byte ceiling"
        )
    header = list(policy["header"])
    columns = dict(policy["columns"])
    decimal_separator = str(policy["decimal_separator"])
    metadata_start = str(policy["metadata_block_start_label"])
    specimen_label = str(policy["specimen_label"])

    blocks: list[dict[str, Any]] = []
    current_metadata: dict[str, Any] | None = None
    active: dict[str, Any] | None = None
    last_measurement_row: int | None = None
    cell_count = 0

    try:
        handle = archive.open(info, "r")
    except (KeyError, RuntimeError, OSError) as exc:
        raise In625TensileReviewedIntakeV2Error(
            f"cannot open worksheet {sheet_name!r}"
        ) from exc

    with handle:
        try:
            iterator = ET.iterparse(handle, events=("end",))
            for _, element in iterator:
                if element.tag != f"{{{_MAIN_NS}}}row":
                    continue
                row_number_raw = element.get("r")
                if (
                    not isinstance(row_number_raw, str)
                    or not row_number_raw.isdigit()
                ):
                    raise In625TensileReviewedIntakeV2Error(
                        "worksheet row number is malformed"
                    )
                row_number = int(row_number_raw)
                values = _row_values(element, shared)
                cell_count += len(values)
                running["cells"] += len(values)
                if running["cells"] > int(policy["max_cells_total"]):
                    raise In625TensileReviewedIntakeV2Error(
                        "reviewed tensile cell budget exceeded"
                    )

                first = values.get(0, "")
                header_values = [
                    values.get(index, "") for index in range(len(header))
                ]
                if header_values == header:
                    if active is not None:
                        _finalize_block(active, last_measurement_row)
                    if current_metadata is None:
                        raise In625TensileReviewedIntakeV2Error(
                            f"worksheet {sheet_name!r} measurement header lacks specimen metadata"
                        )
                    active = {
                        "block_index": len(blocks) + 1,
                        "header_excel_row": row_number,
                        "measurement_start_excel_row": row_number + 1,
                        "measurement_end_excel_row": None,
                        "measurement_row_count": 0,
                        "complete_numeric_row_count": 0,
                        "incomplete_numeric_row_count": 0,
                        "parallel_test_index_raw": current_metadata.get(
                            "parallel_test_index_raw"
                        ),
                        "specimen_code_raw": current_metadata.get(
                            "specimen_code_raw"
                        ),
                        "metadata_rows": list(current_metadata.get("rows", [])),
                        "numeric_ranges_structural_only": {
                            name: {"min": None, "max": None}
                            for name in columns
                        },
                    }
                    blocks.append(active)
                    last_measurement_row = None
                    element.clear()
                    continue

                time_state, time_value = _number_state(
                    first,
                    decimal_separator=decimal_separator,
                    field=f"{sheet_name} row {row_number} time",
                )
                if active is not None and time_state == "numeric":
                    assert time_value is not None
                    parsed: dict[str, float | None] = {}
                    missing: list[str] = []
                    non_numeric: list[str] = []
                    anomalous_raw: dict[str, str] = {}
                    for name, index in columns.items():
                        raw = values.get(index, "")
                        state, number = _number_state(
                            raw,
                            decimal_separator=decimal_separator,
                            field=f"{sheet_name} row {row_number} {name}",
                        )
                        parsed[name] = number
                        _update_quality_counter(
                            running["field_quality"],
                            name,
                            state,
                        )
                        if state == "blank":
                            missing.append(name)
                            anomalous_raw[name] = raw
                        elif state == "non_numeric":
                            non_numeric.append(name)
                            anomalous_raw[name] = raw
                        else:
                            assert number is not None
                            bounds = active["numeric_ranges_structural_only"][name]
                            bounds["min"] = (
                                number
                                if bounds["min"] is None
                                else min(bounds["min"], number)
                            )
                            bounds["max"] = (
                                number
                                if bounds["max"] is None
                                else max(bounds["max"], number)
                            )

                    complete = not missing and not non_numeric
                    active["measurement_row_count"] += 1
                    running["rows"] += 1
                    if complete:
                        active["complete_numeric_row_count"] += 1
                        running["complete_rows"] += 1
                    else:
                        active["incomplete_numeric_row_count"] += 1
                        running["incomplete_rows"] += 1
                        if len(running["anomaly_examples"]) < _MAX_ANOMALY_EXAMPLES:
                            running["anomaly_examples"].append(
                                {
                                    "sheet_name": sheet_name,
                                    "block_index": active["block_index"],
                                    "excel_row_number": row_number,
                                    "missing_reviewed_numeric_fields": list(missing),
                                    "non_numeric_reviewed_fields": list(non_numeric),
                                    "raw_anomalous_cell_text": dict(anomalous_raw),
                                }
                            )
                    if running["rows"] > int(policy["max_measurement_rows_total"]):
                        raise In625TensileReviewedIntakeV2Error(
                            "reviewed tensile measurement-row budget exceeded"
                        )
                    last_measurement_row = row_number
                    if row_sink is not None:
                        record = {
                            "schema_version": SCHEMA_VERSION,
                            "sheet_name": sheet_name,
                            "block_index": active["block_index"],
                            "excel_row_number": row_number,
                            "reviewed_numeric_values": parsed,
                            "missing_reviewed_numeric_fields": missing,
                            "non_numeric_reviewed_fields": non_numeric,
                            "raw_anomalous_cell_text": anomalous_raw,
                            "row_complete_for_reviewed_numeric_analysis": complete,
                            "row_is_independent_specimen": False,
                            "formula_evaluated": False,
                            "number_format_interpreted": False,
                        }
                        row_sink.write(
                            json.dumps(
                                record,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            )
                            + "\n"
                        )
                    element.clear()
                    continue

                if active is not None and any(
                    value.strip() for value in values.values()
                ):
                    _finalize_block(active, last_measurement_row)
                    active = None
                    last_measurement_row = None

                if first == metadata_start:
                    current_metadata = {
                        "parallel_test_index_raw": values.get(1),
                        "specimen_code_raw": None,
                        "rows": [],
                    }
                if current_metadata is not None and active is None:
                    current_metadata["rows"].append(
                        {
                            "excel_row_number": row_number,
                            "label_raw": first,
                            "value_raw": values.get(1, ""),
                            "unit_raw": values.get(2, ""),
                        }
                    )
                    if len(current_metadata["rows"]) > 128:
                        raise In625TensileReviewedIntakeV2Error(
                            "specimen metadata block exceeds reviewed row ceiling"
                        )
                    if first == specimen_label:
                        current_metadata["specimen_code_raw"] = values.get(1)
                element.clear()
        except ET.ParseError as exc:
            raise In625TensileReviewedIntakeV2Error(
                f"worksheet {sheet_name!r} XML is malformed"
            ) from exc

    if active is not None:
        _finalize_block(active, last_measurement_row)
    expected_blocks = _positive_int(
        semantics.get("expected_parallel_test_blocks"),
        f"policy.sheets.{sheet_name}.expected_parallel_test_blocks",
    )
    if (
        len(blocks) != expected_blocks
        or len(blocks) > int(policy["max_parallel_tests_per_sheet"])
    ):
        raise In625TensileReviewedIntakeV2Error(
            f"worksheet {sheet_name!r} parallel-test block count drifted: "
            f"observed={len(blocks)}, expected={expected_blocks}"
        )
    for block in blocks:
        if (
            not isinstance(block.get("specimen_code_raw"), str)
            or not block["specimen_code_raw"]
        ):
            raise In625TensileReviewedIntakeV2Error(
                f"worksheet {sheet_name!r} block {block['block_index']} "
                "lacks specimen-code evidence"
            )
    return {
        "sheet_name": sheet_name,
        "reviewed_condition_semantics": dict(semantics),
        "parallel_test_block_count": len(blocks),
        "measurement_row_count": sum(
            int(block["measurement_row_count"]) for block in blocks
        ),
        "complete_numeric_row_count": sum(
            int(block["complete_numeric_row_count"]) for block in blocks
        ),
        "incomplete_numeric_row_count": sum(
            int(block["incomplete_numeric_row_count"]) for block in blocks
        ),
        "worksheet_xml_uncompressed_bytes": info.file_size,
        "worksheet_cell_count_observed": cell_count,
        "blocks": blocks,
        "parallel_test_blocks_are_statistically_independent": False,
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def build_reviewed_in625_tensile_intake_v2(
    *,
    workbook_path: str | Path,
    readme_path: str | Path,
    policy_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Preserve exact real tensile rows and expose missingness without imputation."""
    workbook_file = Path(workbook_path).expanduser().resolve(strict=True)
    readme_file = Path(readme_path).expanduser().resolve(strict=True)
    policy_file = Path(policy_path).expanduser().resolve(strict=True)
    policy_raw = _load_json(
        policy_file,
        field="IN625 tensile reviewed-intake policy",
    )
    policy = _validate_policy(policy_raw)

    workbook_bytes = workbook_file.read_bytes()
    readme_bytes = readme_file.read_bytes()
    if (
        len(workbook_bytes) != policy["workbook_size_bytes"]
        or _sha256_bytes(workbook_bytes) != policy["workbook_sha256"]
    ):
        raise In625TensileReviewedIntakeV2Error(
            "tensile workbook bytes differ from reviewed policy"
        )
    if (
        len(readme_bytes) != policy["readme_size_bytes"]
        or _sha256_bytes(readme_bytes) != policy["readme_sha256"]
    ):
        raise In625TensileReviewedIntakeV2Error(
            "tensile README bytes differ from reviewed policy"
        )
    try:
        readme_text = readme_bytes.decode(
            str(policy["readme_encoding"]),
            errors="strict",
        )
    except (LookupError, UnicodeDecodeError) as exc:
        raise In625TensileReviewedIntakeV2Error(
            "reviewed tensile README encoding cannot be reproduced"
        ) from exc
    for required_text in (
        "DIN50125 (Type E)",
        "up to three parallel tests",
        *policy["sheets"].keys(),
    ):
        if required_text not in readme_text:
            raise In625TensileReviewedIntakeV2Error(
                "reviewed tensile README lost required semantic evidence: "
                f"{required_text!r}"
            )

    structure = inspect_xlsx_structure(workbook_bytes)
    if (
        structure.get("workbook_sha256") != policy["workbook_sha256"]
        or structure.get("scientific_status_changed") is not False
    ):
        raise In625TensileReviewedIntakeV2Error(
            "structural XLSX intake lost exact workbook binding"
        )

    try:
        archive = zipfile.ZipFile(io.BytesIO(workbook_bytes), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise In625TensileReviewedIntakeV2Error(
            "reviewed tensile workbook is not a valid XLSX container"
        ) from exc

    output_root = (
        None
        if output_dir is None
        else Path(output_dir).expanduser().resolve(strict=False)
    )
    if output_root is not None:
        if output_root.exists() and any(output_root.iterdir()):
            raise In625TensileReviewedIntakeV2Error(
                "reviewed tensile output directory must be absent or empty"
            )
        output_root.mkdir(parents=True, exist_ok=True)
    row_path = (
        None
        if output_root is None
        else output_root / "reviewed_tensile_rows.v2.jsonl"
    )
    row_sink: TextIO | None = None
    if row_path is not None:
        row_sink = row_path.open("x", encoding="utf-8", newline="\n")

    running: dict[str, Any] = {
        "rows": 0,
        "cells": 0,
        "complete_rows": 0,
        "incomplete_rows": 0,
        "field_quality": {
            name: {"numeric": 0, "blank": 0, "non_numeric": 0}
            for name in policy["columns"]
        },
        "anomaly_examples": [],
    }
    try:
        with archive:
            infos: dict[str, zipfile.ZipInfo] = {}
            for info in archive.infolist():
                name = _safe_member_name(info.filename)
                if name in infos:
                    raise In625TensileReviewedIntakeV2Error(
                        f"duplicate XLSX member path: {name}"
                    )
                if info.flag_bits & 0x1:
                    raise In625TensileReviewedIntakeV2Error(
                        f"encrypted XLSX member is not allowed: {name}"
                    )
                if name.lower().endswith("vbaproject.bin"):
                    raise In625TensileReviewedIntakeV2Error(
                        "macro-enabled workbook content is prohibited"
                    )
                infos[name] = info
            for required in (
                "xl/workbook.xml",
                "xl/_rels/workbook.xml.rels",
            ):
                if required not in infos:
                    raise In625TensileReviewedIntakeV2Error(
                        f"XLSX is missing required member: {required}"
                    )
            shared = _shared_strings(archive, infos)
            members = _sheet_members(archive, infos)
            if set(members) != set(policy["sheets"]):
                raise In625TensileReviewedIntakeV2Error(
                    "tensile worksheet set drifted: "
                    f"observed={sorted(members)}, expected={sorted(policy['sheets'])}"
                )
            sheet_reports = []
            for sheet_name in policy["sheets"]:
                sheet_reports.append(
                    _parse_sheet(
                        archive=archive,
                        info=infos[members[sheet_name]],
                        shared=shared,
                        sheet_name=sheet_name,
                        semantics=policy["sheets"][sheet_name],
                        policy=policy,
                        row_sink=row_sink,
                        running=running,
                    )
                )
    finally:
        if row_sink is not None:
            row_sink.close()

    if running["rows"] != int(policy["expected_total_measurement_rows"]):
        if row_path is not None:
            row_path.unlink(missing_ok=True)
        raise In625TensileReviewedIntakeV2Error(
            "total reviewed tensile row count drifted: "
            f"observed={running['rows']}, "
            f"expected={policy['expected_total_measurement_rows']}"
        )

    row_record = None
    if row_path is not None:
        row_sha, row_bytes = _hash_file(row_path)
        row_record = {
            "path": str(row_path),
            "sha256": row_sha,
            "bytes": row_bytes,
            "row_count": running["rows"],
        }
    completeness_fraction = (
        float(running["complete_rows"]) / float(running["rows"])
        if running["rows"]
        else 0.0
    )
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_id": EXPECTED_SOURCE_ID,
        "source_archive_sha256": _sha(
            policy_raw.get("source_archive_sha256"),
            "source_archive_sha256",
        ),
        "policy": {
            "path": str(policy_file),
            "sha256": _sha256_bytes(policy_file.read_bytes()),
        },
        "workbook": {
            "path": str(workbook_file),
            "sha256": policy["workbook_sha256"],
            "bytes": len(workbook_bytes),
        },
        "documentation": {
            "path": str(readme_file),
            "sha256": policy["readme_sha256"],
            "bytes": len(readme_bytes),
            "encoding": policy["readme_encoding"],
        },
        "sheet_count": len(sheet_reports),
        "parallel_test_block_count": sum(
            report["parallel_test_block_count"] for report in sheet_reports
        ),
        "measurement_row_count": running["rows"],
        "complete_numeric_measurement_row_count": running["complete_rows"],
        "incomplete_numeric_measurement_row_count": running["incomplete_rows"],
        "numeric_completeness_fraction_structural_only": completeness_fraction,
        "cell_count_observed": running["cells"],
        "reviewed_numeric_field_quality_counts": running["field_quality"],
        "bounded_incomplete_row_examples": running["anomaly_examples"],
        "bounded_incomplete_row_example_limit": _MAX_ANOMALY_EXAMPLES,
        "sheets": sheet_reports,
        "row_artifact": row_record,
        "reviewed_semantics": {
            "sheet_condition_semantics_from_source_readme": True,
            "measurement_columns_from_exact_workbook_header": True,
            "time_indexed_rows_preserved_even_when_selected_fields_are_incomplete": True,
            "missing_values_imputed": False,
            "non_numeric_values_coerced": False,
            "formula_evaluation_performed": False,
            "number_format_interpretation_performed": False,
            "parallel_test_independence_established": False,
        },
        "evidence_quality": {
            "all_reviewed_numeric_fields_complete": running["incomplete_rows"] == 0,
            "incomplete_rows_retained_as_evidence": running["incomplete_rows"] > 0,
            "numeric_completeness_fraction_is_scientific_confidence": False,
            "missingness_mechanism_established": False,
        },
        "scientific_boundaries": {
            "real_row_level_external_measurements_observed": True,
            "numeric_completeness_establishes_measurement_validity": False,
            "replicate_independence_established": False,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "automatic_scientific_promotion": False,
        },
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    if output_root is not None:
        _write_json(
            output_root / "reviewed_tensile_manifest.v2.json",
            manifest,
        )
    return manifest


__all__ = [
    "In625TensileReviewedIntakeV2Error",
    "build_reviewed_in625_tensile_intake_v2",
]
