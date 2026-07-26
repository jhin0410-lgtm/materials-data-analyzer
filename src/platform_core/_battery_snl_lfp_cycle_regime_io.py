from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence
import zipfile

MAX_ROWS = 8
CAPACITY_CHECK_CANDIDATE_ROWS = 3
BULK_CANDIDATE_ROWS = 5
MAX_LINE_BYTES = 65536
EXPECTED_CYCLE_HEADER_CHECKSUM = "02c4b1f087f1133349cfb60f52443c75099c1d5742a266b4b2889701a344d88c"
SELECTED_COLUMNS = (
    ("Cycle_Index", "cycle_index", None),
    ("Min_Current (A)", "min_current_a", "A"),
    ("Max_Current (A)", "max_current_a", "A"),
    ("Min_Voltage (V)", "min_voltage_v", "V"),
    ("Max_Voltage (V)", "max_voltage_v", "V"),
    ("Charge_Capacity (Ah)", "charge_capacity_ah", "Ah"),
    ("Discharge_Capacity (Ah)", "discharge_capacity_ah", "Ah"),
)
CONTRAST_FIELDS = (
    "min_current_a",
    "max_current_a",
    "min_voltage_v",
    "max_voltage_v",
    "charge_capacity_ah",
    "discharge_capacity_ah",
)
CONTROL_CONTRAST_FIELDS = (
    "min_current_a",
    "max_current_a",
    "min_voltage_v",
    "max_voltage_v",
)


def canonical_checksum(payload: Any) -> str:
    core = dict(payload) if isinstance(payload, Mapping) else payload
    if isinstance(core, dict):
        core.pop("deterministic_result_checksum", None)
    text = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_entry_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(
        name
        and "\x00" not in name
        and "\\" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and not re.match(r"^[A-Za-z]:", name)
    )


def parse_csv_line(raw: bytes, max_line_bytes: int) -> list[str]:
    if len(raw) > max_line_bytes:
        raise ValueError("CSV line exceeds bounded byte limit")
    if b"\x00" in raw:
        raise ValueError("NUL byte found in CSV line")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV line is not valid UTF-8") from exc
    try:
        rows = list(csv.reader([text], delimiter=",", strict=True))
    except csv.Error as exc:
        raise ValueError("CSV line parse failure") from exc
    if len(rows) != 1:
        raise ValueError("one physical line must contain one CSV record")
    return [cell.strip() for cell in rows[0]]


def decimal_value(value: str, field: str) -> Decimal:
    if value == "":
        raise ValueError(f"empty selected value: {field}")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"non-decimal selected value: {field}") from exc
    if not number.is_finite():
        raise ValueError(f"non-finite selected value: {field}")
    return number


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def cycle_regime_contrast(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    check_rows = rows[:CAPACITY_CHECK_CANDIDATE_ROWS]
    bulk_rows = rows[CAPACITY_CHECK_CANDIDATE_ROWS:MAX_ROWS]
    fields = []
    for field in CONTRAST_FIELDS:
        check_values = [
            decimal_value(str(item["selected_values"][field]), field)
            for item in check_rows
        ]
        bulk_values = [
            decimal_value(str(item["selected_values"][field]), field)
            for item in bulk_rows
        ]
        check_min, check_max = min(check_values), max(check_values)
        bulk_min, bulk_max = min(bulk_values), max(bulk_values)
        direction = "overlap"
        if check_max < bulk_min:
            direction = "capacity_check_candidate_below_bulk_candidate"
        elif bulk_max < check_min:
            direction = "capacity_check_candidate_above_bulk_candidate"
        fields.append(
            {
                "field": field,
                "capacity_check_candidate_range": {
                    "minimum": decimal_text(check_min),
                    "maximum": decimal_text(check_max),
                },
                "bulk_candidate_range": {
                    "minimum": decimal_text(bulk_min),
                    "maximum": decimal_text(bulk_max),
                },
                "non_overlapping": direction != "overlap",
                "direction": direction,
            }
        )
    nonoverlap = [item["field"] for item in fields if item["non_overlapping"]]
    control_nonoverlap = [
        item["field"]
        for item in fields
        if item["field"] in CONTROL_CONTRAST_FIELDS and item["non_overlapping"]
    ]
    return {
        "method": "exact_decimal_group_ranges_without_fitted_thresholds",
        "field_contrasts": fields,
        "non_overlapping_field_count": len(nonoverlap),
        "non_overlapping_fields": nonoverlap,
        "control_non_overlapping_field_count": len(control_nonoverlap),
        "control_non_overlapping_fields": control_nonoverlap,
        "contrast_status": (
            "bounded_regime_contrast_observed"
            if control_nonoverlap
            else "bounded_regime_contrast_not_observed"
        ),
        "threshold_fitted_or_inferred": False,
        "candidate_labels_promoted": False,
    }


def failure_observation(
    info_name: str,
    protocol_family: str,
    status: str,
    *,
    bytes_read: int = 0,
    rows_read: int = 0,
    header_checksum: str | None = None,
    row_widths: list[int] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry_name": info_name,
        "protocol_family": protocol_family,
        "read_status": status,
        "bytes_read": bytes_read,
        "sample_data_rows_read": rows_read,
        "selected_measurement_values_retained": False,
        "full_file_read": False,
    }
    if header_checksum is not None:
        result["header_checksum"] = header_checksum
    if row_widths is not None:
        result["sample_row_widths"] = row_widths
    if error is not None:
        result["error"] = error
    return result


def read_cycle_sample(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    representative: Mapping[str, Any],
    max_line_bytes: int,
) -> dict[str, Any]:
    protocol = str(representative["protocol_family"])
    bytes_read = 0
    raw_rows: list[list[str]] = []
    with archive.open(info, "r") as handle:
        header_line = handle.readline(max_line_bytes + 1)
        bytes_read += len(header_line)
        if not header_line:
            return failure_observation(
                info.filename, protocol, "empty_file", bytes_read=bytes_read
            )
        try:
            header = parse_csv_line(header_line, max_line_bytes)
            for _ in range(MAX_ROWS):
                line = handle.readline(max_line_bytes + 1)
                if not line:
                    break
                bytes_read += len(line)
                raw_rows.append(parse_csv_line(line, max_line_bytes))
        except ValueError as exc:
            return failure_observation(
                info.filename,
                protocol,
                "bounded_parse_error",
                bytes_read=bytes_read,
                rows_read=len(raw_rows),
                error=str(exc),
            )

    header_checksum = canonical_checksum(header)
    if header_checksum != EXPECTED_CYCLE_HEADER_CHECKSUM:
        return failure_observation(
            info.filename,
            protocol,
            "cycle_header_checksum_mismatch",
            bytes_read=bytes_read,
            rows_read=len(raw_rows),
            header_checksum=header_checksum,
        )
    if len(raw_rows) != MAX_ROWS:
        return failure_observation(
            info.filename,
            protocol,
            "insufficient_bounded_cycle_rows",
            bytes_read=bytes_read,
            rows_read=len(raw_rows),
            header_checksum=header_checksum,
        )

    widths = [len(row) for row in raw_rows]
    if any(width != len(header) for width in widths):
        return failure_observation(
            info.filename,
            protocol,
            "bounded_row_width_mismatch",
            bytes_read=bytes_read,
            rows_read=len(raw_rows),
            header_checksum=header_checksum,
            row_widths=widths,
        )

    indexes = {name: header.index(name) for name, _, _ in SELECTED_COLUMNS if name in header}
    if set(indexes) != {name for name, _, _ in SELECTED_COLUMNS}:
        return failure_observation(
            info.filename,
            protocol,
            "selected_column_missing",
            bytes_read=bytes_read,
            rows_read=len(raw_rows),
            header_checksum=header_checksum,
        )

    selected_rows = []
    cycle_numbers: list[Decimal] = []
    try:
        for position, row in enumerate(raw_rows, start=1):
            selected: dict[str, str] = {}
            for header_name, field, _unit in SELECTED_COLUMNS:
                raw_value = row[indexes[header_name]]
                number = decimal_value(raw_value, field)
                if field == "cycle_index" and number != number.to_integral_value():
                    raise ValueError("cycle_index is not an integer")
                selected[field] = raw_value
            cycle_numbers.append(decimal_value(selected["cycle_index"], "cycle_index"))
            selected_rows.append(
                {
                    "row_position": position,
                    "source_sequence_candidate": (
                        "capacity_check_candidate"
                        if position <= CAPACITY_CHECK_CANDIDATE_ROWS
                        else "bulk_cycle_candidate"
                    ),
                    "selected_values": selected,
                    "candidate_assignment_promoted": False,
                }
            )
    except ValueError as exc:
        return failure_observation(
            info.filename,
            protocol,
            "selected_value_contract_mismatch",
            bytes_read=bytes_read,
            rows_read=len(raw_rows),
            header_checksum=header_checksum,
            error=str(exc),
        )

    increasing = all(left < right for left, right in zip(cycle_numbers, cycle_numbers[1:]))
    contrast = cycle_regime_contrast(selected_rows)
    return {
        "entry_name": info.filename,
        "file_kind": "cycle_data",
        "protocol_family": protocol,
        "read_status": (
            "bounded_cycle_regime_evidence_recorded"
            if increasing
            else "bounded_cycle_index_contract_mismatch"
        ),
        "bytes_read": bytes_read,
        "header_checksum": header_checksum,
        "sample_data_rows_read": len(raw_rows),
        "sample_row_widths": widths,
        "cycle_index_strictly_increasing": increasing,
        "selected_field_contract": [
            {"header": header_name, "field": field, "unit": unit}
            for header_name, field, unit in SELECTED_COLUMNS
        ],
        "selected_cycle_rows": selected_rows,
        "cycle_regime_contrast": contrast,
        "selected_measurement_values_retained": True,
        "selected_values_preserved_as_exact_decimal_strings": True,
        "candidate_assignment_promoted": False,
        "full_file_read": False,
    }
