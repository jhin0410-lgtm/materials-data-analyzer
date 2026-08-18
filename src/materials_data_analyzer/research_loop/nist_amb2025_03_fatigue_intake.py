"""Exact-byte scientific intake for NIST AMB2025-03 Ti-6Al-4V fatigue data.

The source workbook mixes observed failures, explicit runouts, and one invalid test.
Runout semantics are carried by the source ``notes`` field; a numeric value in the
``cycles to failure (N)`` column must therefore never be promoted to an observed
failure when the same row is explicitly labelled as a runout.

This module performs no fatigue-model fitting and makes no treatment-effect claim.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "1.0"
PRODUCT_ID = "mds2-3734"
DATASET_DOI = "10.18434/mds2-3734"
CONDITION = "800HIP"
SHEET_NAME = "data"
TITLE = "800HIP12C/min"
_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_DECIMAL_TEXT_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_EXACT_RUNOUT_RE = re.compile(r"^runout(?:[ -])?([0-9][0-9,]*)(?: cycles)?$", re.I)
_MILLION_RUNOUT_RE = re.compile(r"^([0-9]+)M runout$", re.I)

HEADERS = (
    "Test #",
    "specimen ID #",
    "Data Log #",
    "diameter (mm)",
    "desired stress (MPa)",
    "desired load (N)",
    "cycles to failure (N)",
    "Operator",
    "notes",
)

_REQUIRED_README_TOKENS = (
    "Twenty-four specimens from each condition",
    "four-point rotating bending fatigue",
    "ADMET eXpert 9313",
    "test frequency 100 Hz",
    "load ratio R = -1",
    "ISO 1143",
    "rated accuracy of ±0.01mm",
    ".xlsx file contains raw fatigue data",
)


class NistAmb202503FatigueIntakeError(ValueError):
    """Raised when exact source bytes cannot support the declared fatigue intake."""


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _sheet_rows(xlsx_bytes: bytes, sheet_name: str) -> list[dict[str, Any]]:
    if not isinstance(xlsx_bytes, bytes):
        raise NistAmb202503FatigueIntakeError("workbook input must be exact bytes")
    try:
        archive = zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise NistAmb202503FatigueIntakeError("workbook is not a valid XLSX") from exc

    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise NistAmb202503FatigueIntakeError("XLSX repeats ZIP member names")
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(names):
            raise NistAmb202503FatigueIntakeError("XLSX workbook parts are missing")

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
        sheets = workbook.find(f"{{{_XLSX_NS}}}sheets")
        if sheets is None:
            raise NistAmb202503FatigueIntakeError("XLSX has no sheets")
        target: str | None = None
        for sheet in sheets:
            if sheet.attrib.get("name") == sheet_name:
                rel_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
                target = rel_map.get(rel_id or "")
                break
        if target is None:
            raise NistAmb202503FatigueIntakeError(
                f"required sheet {sheet_name!r} is missing"
            )
        member = (
            target.lstrip("/")
            if target.startswith("/")
            else "xl/" + target.lstrip("/")
        )
        if member not in names:
            raise NistAmb202503FatigueIntakeError(
                f"sheet XML for {sheet_name!r} is missing"
            )

        root = ET.fromstring(archive.read(member))
        result: list[dict[str, Any]] = []
        seen_rows: set[int] = set()
        for row in root.findall(
            f".//{{{_XLSX_NS}}}sheetData/{{{_XLSX_NS}}}row"
        ):
            try:
                row_number = int(row.attrib["r"])
            except (KeyError, ValueError) as exc:
                raise NistAmb202503FatigueIntakeError(
                    "XLSX row lacks a valid row number"
                ) from exc
            if row_number in seen_rows:
                raise NistAmb202503FatigueIntakeError(
                    f"sheet {sheet_name!r} repeats row {row_number}"
                )
            seen_rows.add(row_number)
            cells: dict[str, dict[str, Any]] = {}
            for cell in row.findall(f"{{{_XLSX_NS}}}c"):
                ref = cell.attrib.get("r", "")
                match = _CELL_RE.fullmatch(ref)
                if not match or int(match.group(2)) != row_number:
                    raise NistAmb202503FatigueIntakeError(
                        f"invalid XLSX cell reference {ref!r}"
                    )
                column = match.group(1)
                if column in cells:
                    raise NistAmb202503FatigueIntakeError(
                        f"duplicate XLSX cell {ref!r}"
                    )
                formula_node = cell.find(f"{{{_XLSX_NS}}}f")
                value_node = cell.find(f"{{{_XLSX_NS}}}v")
                cell_type = cell.attrib.get("t")
                value: Any = None
                if cell_type == "s":
                    if value_node is None or value_node.text is None:
                        raise NistAmb202503FatigueIntakeError(
                            f"shared-string cell {ref!r} has no index"
                        )
                    try:
                        value = shared[int(value_node.text)]
                    except (ValueError, IndexError) as exc:
                        raise NistAmb202503FatigueIntakeError(
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
                    "formula": formula_node.text if formula_node is not None else None,
                }
            result.append({"row": row_number, "cells": cells})
        return result


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NistAmb202503FatigueIntakeError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise NistAmb202503FatigueIntakeError(f"{field} must be finite")
    return float(format(number, ".15g"))


def _finite_source_decimal(value: object, field: str) -> tuple[float, str]:
    """Parse a source decimal while preserving whether Excel stored text or number."""

    if isinstance(value, bool):
        raise NistAmb202503FatigueIntakeError(
            f"{field} must be a numeric cell or exact decimal text"
        )
    if isinstance(value, (int, float)):
        return _finite_number(value, field), "numeric_cell"
    if (
        isinstance(value, str)
        and value == value.strip()
        and _DECIMAL_TEXT_RE.fullmatch(value)
    ):
        number = float(value)
        if not math.isfinite(number):
            raise NistAmb202503FatigueIntakeError(f"{field} text must be finite")
        return float(format(number, ".15g")), "text_decimal_cell"
    raise NistAmb202503FatigueIntakeError(
        f"{field} must be a numeric cell or exact decimal text"
    )


def _positive_int(value: object, field: str) -> int:
    number = _finite_number(value, field)
    if number <= 0 or not number.is_integer():
        raise NistAmb202503FatigueIntakeError(f"{field} must be a positive integer")
    return int(number)


def _source_identifier(value: object, field: str) -> str:
    if isinstance(value, bool) or value is None:
        raise NistAmb202503FatigueIntakeError(f"{field} must identify a source record")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NistAmb202503FatigueIntakeError(f"{field} must be finite")
        return str(int(value)) if value.is_integer() else format(value, ".15g")
    if isinstance(value, str) and value.strip() and value == value.strip():
        return value
    raise NistAmb202503FatigueIntakeError(f"{field} must be non-empty exact text/number")


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value != value.strip():
        raise NistAmb202503FatigueIntakeError(f"{field} must be exact text or blank")
    return value or None


def _classify_result(*, cycles: int | None, note: str | None) -> dict[str, Any]:
    if note is not None and "runout" in note.lower():
        exact_match = _EXACT_RUNOUT_RE.fullmatch(note)
        shorthand_match = _MILLION_RUNOUT_RE.fullmatch(note)
        exact_censor: int | None = None
        lower_bound: int | None = None
        parse_status: str
        if exact_match:
            exact_censor = int(exact_match.group(1).replace(",", ""))
            parse_status = "exact_note_integer"
        elif shorthand_match:
            lower_bound = int(shorthand_match.group(1)) * 1_000_000
            parse_status = "million_shorthand_requires_semantic_review"
        else:
            parse_status = "unrecognized_runout_note_requires_review"
        discrepancy = (
            cycles is not None
            and exact_censor is not None
            and cycles != exact_censor
        )
        return {
            "outcome": "runout",
            "event_observed": False,
            "failure_cycles": None,
            "censor_cycles_exact": exact_censor,
            "censor_cycles_lower_bound": lower_bound,
            "censor_parse_status": parse_status,
            "cycles_column_value": cycles,
            "cycles_column_conflicts_with_exact_censor_note": discrepancy,
        }

    if note is not None and note.lower().startswith("invalid test"):
        return {
            "outcome": "invalid",
            "event_observed": False,
            "failure_cycles": None,
            "censor_cycles_exact": None,
            "censor_cycles_lower_bound": None,
            "censor_parse_status": "not_applicable_invalid_test",
            "cycles_column_value": cycles,
            "cycles_column_conflicts_with_exact_censor_note": False,
        }

    if note is not None:
        return {
            "outcome": "review_required",
            "event_observed": False,
            "failure_cycles": None,
            "censor_cycles_exact": None,
            "censor_cycles_lower_bound": None,
            "censor_parse_status": "unrecognized_note_requires_review",
            "cycles_column_value": cycles,
            "cycles_column_conflicts_with_exact_censor_note": False,
        }

    if cycles is None:
        return {
            "outcome": "review_required",
            "event_observed": False,
            "failure_cycles": None,
            "censor_cycles_exact": None,
            "censor_cycles_lower_bound": None,
            "censor_parse_status": "missing_cycles_without_source_note",
            "cycles_column_value": None,
            "cycles_column_conflicts_with_exact_censor_note": False,
        }
    return {
        "outcome": "failure",
        "event_observed": True,
        "failure_cycles": cycles,
        "censor_cycles_exact": None,
        "censor_cycles_lower_bound": None,
        "censor_parse_status": "not_applicable_observed_failure",
        "cycles_column_value": cycles,
        "cycles_column_conflicts_with_exact_censor_note": False,
    }


def audit_amb2025_03_fatigue(
    *, workbook_bytes: bytes, readme_bytes: bytes
) -> dict[str, Any]:
    """Audit exact 800HIP fatigue workbook bytes without fitting a fatigue model."""

    if not isinstance(workbook_bytes, bytes) or not isinstance(readme_bytes, bytes):
        raise NistAmb202503FatigueIntakeError("source inputs must be exact bytes")
    try:
        readme = readme_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NistAmb202503FatigueIntakeError("fatigue README must be UTF-8") from exc
    missing_tokens = [token for token in _REQUIRED_README_TOKENS if token not in readme]
    if missing_tokens:
        raise NistAmb202503FatigueIntakeError(
            f"fatigue README no longer exposes required source semantics: {missing_tokens}"
        )

    rows = _sheet_rows(workbook_bytes, SHEET_NAME)
    by_number = {row["row"]: row for row in rows}
    title = by_number.get(1, {}).get("cells", {}).get("A", {}).get("value")
    if title != TITLE:
        raise NistAmb202503FatigueIntakeError("fatigue workbook title changed")
    header_row = by_number.get(2)
    if header_row is None:
        raise NistAmb202503FatigueIntakeError("fatigue workbook header row 2 is missing")
    for index, expected in enumerate(HEADERS, start=1):
        column = _column(index)
        observed = header_row["cells"].get(column, {}).get("value")
        if observed != expected:
            raise NistAmb202503FatigueIntakeError(
                f"fatigue workbook header {column} mismatch: {observed!r}"
            )

    records: list[dict[str, Any]] = []
    seen_test_numbers: set[int] = set()
    seen_specimens: set[str] = set()
    desired_load_formula_cells: list[str] = []
    core_formula_columns = {"A", "B", "C", "D", "E", "G", "H", "I"}

    for row in rows:
        if row["row"] <= 2:
            continue
        cells = row["cells"]
        if not any(
            cells.get(_column(index), {}).get("value") is not None
            for index in range(1, 10)
        ):
            continue
        for column in core_formula_columns:
            if cells.get(column, {}).get("formula") is not None:
                raise NistAmb202503FatigueIntakeError(
                    f"core fatigue authority contains formula at {column}{row['row']}"
                )
        if cells.get("F", {}).get("formula") is not None:
            desired_load_formula_cells.append(f"F{row['row']}")

        test_number = _positive_int(cells.get("A", {}).get("value"), "Test #")
        if test_number in seen_test_numbers:
            raise NistAmb202503FatigueIntakeError(
                f"fatigue workbook repeats Test # {test_number}"
            )
        seen_test_numbers.add(test_number)
        specimen_id = _source_identifier(
            cells.get("B", {}).get("value"), "specimen ID #"
        )
        if specimen_id in seen_specimens:
            raise NistAmb202503FatigueIntakeError(
                f"fatigue workbook repeats specimen ID {specimen_id!r}"
            )
        seen_specimens.add(specimen_id)
        data_log_id = _source_identifier(cells.get("C", {}).get("value"), "Data Log #")
        diameter_mm, diameter_source_storage = _finite_source_decimal(
            cells.get("D", {}).get("value"), "diameter (mm)"
        )
        stress_mpa = _finite_number(
            cells.get("E", {}).get("value"), "desired stress (MPa)"
        )
        desired_load_n = _finite_number(
            cells.get("F", {}).get("value"), "desired load (N)"
        )
        if diameter_mm <= 0 or stress_mpa <= 0 or desired_load_n <= 0:
            raise NistAmb202503FatigueIntakeError(
                f"fatigue row {row['row']} contains non-positive physical values"
            )
        raw_cycles = cells.get("G", {}).get("value")
        cycles = (
            None
            if raw_cycles is None
            else _positive_int(raw_cycles, "cycles to failure (N)")
        )
        operator = _optional_text(cells.get("H", {}).get("value"), "Operator")
        if operator is None:
            raise NistAmb202503FatigueIntakeError(
                f"fatigue row {row['row']} lacks operator provenance"
            )
        note = _optional_text(cells.get("I", {}).get("value"), "notes")
        classification = _classify_result(cycles=cycles, note=note)
        records.append(
            {
                "excel_row": row["row"],
                "test_number": test_number,
                "specimen_id_source": specimen_id,
                "data_log_id_source": data_log_id,
                "condition": CONDITION,
                "diameter_mm": diameter_mm,
                "diameter_source_storage": diameter_source_storage,
                "desired_stress_mpa": stress_mpa,
                "desired_load_n": desired_load_n,
                "operator": operator,
                "source_note": note,
                **classification,
            }
        )

    records.sort(key=lambda item: item["test_number"])
    outcomes = Counter(item["outcome"] for item in records)
    diameter_storage = Counter(item["diameter_source_storage"] for item in records)
    unresolved = [
        item
        for item in records
        if item["outcome"] in {"runout", "review_required"}
        and item["censor_parse_status"]
        not in {"exact_note_integer", "not_applicable_observed_failure"}
    ]
    discrepancies = [
        item
        for item in records
        if item["cycles_column_conflicts_with_exact_censor_note"] is True
    ]
    stress_summary: dict[str, dict[str, int]] = {}
    by_stress: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        by_stress[item["desired_stress_mpa"]].append(item)
    for stress, items in sorted(by_stress.items()):
        counts = Counter(item["outcome"] for item in items)
        key = (
            str(int(stress))
            if float(stress).is_integer()
            else format(stress, ".15g")
        )
        stress_summary[key] = {
            "specimens": len(items),
            "failures": counts["failure"],
            "runouts": counts["runout"],
            "invalid": counts["invalid"],
            "review_required": counts["review_required"],
        }

    valid_specimens = outcomes["failure"] + outcomes["runout"]
    runout_exact = sum(
        item["outcome"] == "runout"
        and item["censor_parse_status"] == "exact_note_integer"
        for item in records
    )
    runout_shorthand = sum(
        item["outcome"] == "runout"
        and item["censor_parse_status"] == "million_shorthand_requires_semantic_review"
        for item in records
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "product_id": PRODUCT_ID,
            "doi": DATASET_DOI,
            "condition": CONDITION,
            "workbook_sha256": _sha256(workbook_bytes),
            "workbook_size_bytes": len(workbook_bytes),
            "readme_sha256": _sha256(readme_bytes),
            "readme_size_bytes": len(readme_bytes),
            "sheet_name": SHEET_NAME,
            "sheet_title": TITLE,
        },
        "source_method_semantics": {
            "fatigue_mode": "four_point_rotating_bending",
            "load_ratio_R": -1,
            "test_frequency_hz": 100,
            "standard": "ISO 1143",
            "specimens_per_condition_declared": 24,
            "diameter_measurement_accuracy_mm": 0.01,
            "build_replication_established": False,
            "build_replication_reason": (
                "AMB2025-03 challenge documentation declares one PBF-L build split "
                "into post-build conditions; specimen count is not build replication."
            ),
        },
        "fatigue_inventory": {
            "test_rows": len(records),
            "unique_source_specimens": len(seen_specimens),
            "valid_failure_or_runout_specimens": valid_specimens,
            "observed_failures": outcomes["failure"],
            "runouts": outcomes["runout"],
            "invalid_tests": outcomes["invalid"],
            "review_required_rows": outcomes["review_required"],
            "desired_load_formula_cell_count": len(desired_load_formula_cells),
            "desired_load_formula_cells": desired_load_formula_cells,
            "diameter_source_storage_counts": dict(sorted(diameter_storage.items())),
            "stress_level_summary": stress_summary,
        },
        "runout_reconciliation": {
            "runout_rows": outcomes["runout"],
            "exact_integer_censor_cycles_from_notes": runout_exact,
            "million_shorthand_rows_requiring_semantic_review": runout_shorthand,
            "unresolved_or_nonexact_censor_rows": len(unresolved),
            "cycles_column_vs_exact_note_discrepancy_count": len(discrepancies),
            "discrepancies": [
                {
                    "test_number": item["test_number"],
                    "specimen_id_source": item["specimen_id_source"],
                    "cycles_column_value": item["cycles_column_value"],
                    "censor_cycles_exact": item["censor_cycles_exact"],
                    "source_note": item["source_note"],
                }
                for item in discrepancies
            ],
            "scientific_interpretation": (
                "The cycles-to-failure column is not an event-status authority. "
                "Rows explicitly labelled runout remain right-censored even when that "
                "column contains a numeric value."
            ),
        },
        "records": records,
        "analysis_eligibility": {
            "naive_uncensored_cycles_regression": {
                "eligible": False,
                "reason": "explicit runouts would be misclassified as observed failures",
            },
            "condition_specific_censored_sn_analysis": {
                "eligible": len(unresolved) == 0 and outcomes["review_required"] == 0,
                "reason": (
                    "eligible only after every runout has exact censor-time semantics"
                    if unresolved or outcomes["review_required"]
                    else "all event/censor outcomes have exact source-bound semantics"
                ),
            },
            "hip_vs_vac_fatigue_treatment_comparison": {
                "eligible": False,
                "reason": "the acquired public fatigue workbook contains 800HIP outcomes only",
            },
            "build_generalized_treatment_effect": {
                "eligible": False,
                "reason": "one source build does not establish independent build replication",
            },
        },
        "detected_weaknesses": [
            {
                "code": "runout_semantics_split_across_columns",
                "severity": "critical_for_fatigue_modeling",
                "evidence": (
                    f"{outcomes['runout']} explicit runouts; {len(discrepancies)} exact "
                    "runouts disagree with the numeric cycles column"
                ),
            },
            {
                "code": "one_runout_uses_million_shorthand",
                "severity": "blocks_exact_censor_time_contract",
                "evidence": (
                    f"{runout_shorthand} runout row uses M shorthand rather than an exact "
                    "integer cycle count"
                ),
            },
            {
                "code": "diameter_storage_type_mixed",
                "severity": "source_data_quality_provenance",
                "evidence": (
                    f"{diameter_storage['text_decimal_cell']} diameter cells are stored as "
                    f"exact decimal text and {diameter_storage['numeric_cell']} as numeric cells"
                ),
            },
            {
                "code": "single_build_origin",
                "severity": "limits_external_treatment_inference",
                "evidence": "specimen replication is nested within one PBF-L build",
            },
            {
                "code": "vac_fatigue_outcomes_not_in_current_public_file",
                "severity": "blocks_fatigue_treatment_comparison",
                "evidence": "current public fatigue calibration file is fatigue_800hip.xlsx",
            },
        ],
        "bounded_next_action": {
            "action_type": "runout_censor_semantics_audit",
            "objective": (
                "Resolve the one non-integer runout shorthand and preserve exact right-"
                "censor times before any censored S-N or survival-style analysis."
            ),
            "model_training_authorized": False,
            "scientific_status_change_authorized": False,
        },
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    report["report_sha256"] = _sha256(_json_bytes(report))
    return report


__all__ = [
    "CONDITION",
    "DATASET_DOI",
    "HEADERS",
    "NistAmb202503FatigueIntakeError",
    "PRODUCT_ID",
    "SCHEMA_VERSION",
    "audit_amb2025_03_fatigue",
]
