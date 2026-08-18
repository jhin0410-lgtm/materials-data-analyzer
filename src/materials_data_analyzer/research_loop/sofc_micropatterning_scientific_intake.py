"""Exact scientific intake for the public SOFC ceramic-micropatterning archive.

Raw CSV measurements remain the canonical measurement layer. XLSX summary, fitting,
DRT, and image-analysis workbooks are treated as derived representations and are
reconciled against raw evidence where the source bytes permit. Filenames and row counts
never become sample or replicate identity.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import statistics
import zipfile
from collections.abc import Mapping
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "1.0"
IV_SUMMARY = "Current density-voltage/I-V-P summary.xlsx"
UV_RAW = "UV intensity/UV intensity data.csv"
UV_SUMMARY = "UV intensity/UV intensity summary.xlsx"
PROFILE = "Sintered pattern cell for SOFC operation/profile of single 50um dot for SOFC operation.csv"
FIT_FLAT = "Impedance/A-R configration (In paper)/fitting value flat cell.xlsx"
FIT_PATTERN = "Impedance/A-R configration (In paper)/fitting value patten cell.xlsx"
DRT_SUMMARY = "Impedance/DRT analysys for A-R/DRT curve summary.xlsx"
POROSITY = "Test pattern after sintering/Porosity cal/Porosity.xlsx"

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")

IV_FILES = {
    (600, "flat"): "Current density-voltage/I-V 600 flat cell.csv",
    (600, "pattern"): "Current density-voltage/I-V 600 pattern cell.csv",
    (700, "flat"): "Current density-voltage/I-V 700 flat cell.csv",
    (700, "pattern"): "Current density-voltage/I-V 700 pattern cell.csv",
    (800, "flat"): "Current density-voltage/I-V 800 flat cell.csv",
    (800, "pattern"): "Current density-voltage/I-V 800 pattern cell.csv",
}
OCV_FILES = {
    (temperature, structure): f"OCV/OCV {temperature} {structure} cell.csv"
    for temperature in (600, 700, 800)
    for structure in ("flat", "pattern")
}
IMPEDANCE_FILES = {
    (configuration, temperature, structure): (
        f"Impedance/{configuration}/{temperature} {label} impedance {structure} cell.csv"
    )
    for configuration, label in (
        ("A-C configration", "A-C"),
        ("A-R configration (In paper)", "A-R"),
        ("C-R configration", "C-R"),
    )
    for temperature in (600, 700, 800)
    for structure in ("flat", "pattern")
}


class SofcMicropatterningScientificIntakeError(ValueError):
    """Raised when exact source bytes cannot support the declared scientific intake."""


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_sha(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _archive_members(archive_bytes: bytes) -> dict[str, bytes]:
    if not isinstance(archive_bytes, bytes):
        raise SofcMicropatterningScientificIntakeError("archive input must be exact bytes")
    required = {
        *IV_FILES.values(),
        *OCV_FILES.values(),
        *IMPEDANCE_FILES.values(),
        IV_SUMMARY,
        UV_RAW,
        UV_SUMMARY,
        PROFILE,
        FIT_FLAT,
        FIT_PATTERN,
        DRT_SUMMARY,
        POROSITY,
    }
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise SofcMicropatterningScientificIntakeError("archive repeats member names")
            missing = sorted(required - set(names))
            if missing:
                raise SofcMicropatterningScientificIntakeError(
                    f"required SOFC intake members are missing: {missing}"
                )
            return {name: archive.read(name) for name in required}
    except zipfile.BadZipFile as exc:
        raise SofcMicropatterningScientificIntakeError("SOFC source is not a valid ZIP") from exc


def _csv_rows(body: bytes, field: str) -> list[list[str]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SofcMicropatterningScientificIntakeError(f"{field} is not UTF-8 CSV") from exc
    return list(csv.reader(io.StringIO(text)))


def _decimal(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise SofcMicropatterningScientificIntakeError(f"{field} must be decimal")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SofcMicropatterningScientificIntakeError(f"{field} is not decimal") from exc
    if not math.isfinite(number):
        raise SofcMicropatterningScientificIntakeError(f"{field} must be finite")
    return number


def _col_index(col: str) -> int:
    value = 0
    for char in col:
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def _col_name(index: int) -> str:
    value = ""
    while index:
        index, rem = divmod(index - 1, 26)
        value = chr(ord("A") + rem) + value
    return value


def _xlsx_rows(body: bytes) -> list[list[Any]]:
    """Read first worksheet cached values from exact XLSX OOXML parts."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(body), "r")
    except zipfile.BadZipFile as exc:
        raise SofcMicropatterningScientificIntakeError("selected member is not valid XLSX") from exc
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise SofcMicropatterningScientificIntakeError("XLSX repeats ZIP member names")
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            raise SofcMicropatterningScientificIntakeError("XLSX workbook parts are missing")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{_NS}}}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{{{_NS}}}t")))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
        sheets = workbook.find(f"{{{_NS}}}sheets")
        if sheets is None or len(sheets) < 1:
            raise SofcMicropatterningScientificIntakeError("XLSX has no worksheet")
        rel_id = sheets[0].attrib.get(f"{{{_REL_NS}}}id")
        target = rel_map.get(rel_id or "")
        if not target:
            raise SofcMicropatterningScientificIntakeError("first worksheet target is missing")
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target.lstrip("/")
        if member not in names:
            raise SofcMicropatterningScientificIntakeError("worksheet XML is missing")
        root = ET.fromstring(archive.read(member))
        parsed: dict[int, dict[str, Any]] = {}
        max_col = 0
        max_row = 0
        for row in root.findall(f".//{{{_NS}}}sheetData/{{{_NS}}}row"):
            row_number = int(row.attrib["r"])
            if row_number in parsed:
                raise SofcMicropatterningScientificIntakeError("XLSX repeats row number")
            cells: dict[str, Any] = {}
            for cell in row.findall(f"{{{_NS}}}c"):
                ref = cell.attrib.get("r", "")
                match = _CELL_RE.fullmatch(ref)
                if not match or int(match.group(2)) != row_number:
                    raise SofcMicropatterningScientificIntakeError(
                        f"invalid XLSX cell reference {ref!r}"
                    )
                col = match.group(1)
                value_node = cell.find(f"{{{_NS}}}v")
                cell_type = cell.attrib.get("t")
                if cell_type == "s":
                    value = None if value_node is None or value_node.text is None else shared[int(value_node.text)]
                elif cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall(f".//{{{_NS}}}t"))
                elif cell_type == "str":
                    value = value_node.text if value_node is not None else ""
                elif value_node is None or value_node.text is None:
                    value = None
                else:
                    text = value_node.text
                    try:
                        number = float(text)
                    except ValueError:
                        value = text
                    else:
                        value = int(number) if number.is_integer() else number
                cells[col] = value
                max_col = max(max_col, _col_index(col))
            parsed[row_number] = cells
            max_row = max(max_row, row_number)
        result: list[list[Any]] = []
        for row_number in range(1, max_row + 1):
            cells = parsed.get(row_number, {})
            result.append([cells.get(_col_name(index)) for index in range(1, max_col + 1)])
        return result


def _numeric_pairs(rows: list[list[str]], field: str) -> list[tuple[float, float]]:
    values: list[tuple[float, float]] = []
    for row in rows:
        if len(row) < 2:
            continue
        try:
            left = float(row[0])
            right = float(row[1])
        except ValueError:
            continue
        if not math.isfinite(left) or not math.isfinite(right):
            raise SofcMicropatterningScientificIntakeError(f"{field} contains non-finite values")
        values.append((left, right))
    if not values:
        raise SofcMicropatterningScientificIntakeError(f"{field} has no numeric pairs")
    return values


def _iv_intake(members: Mapping[str, bytes]) -> dict[str, Any]:
    expected_counts = {
        (600, "flat"): 2143,
        (600, "pattern"): 2143,
        (700, "flat"): 2115,
        (700, "pattern"): 2067,
        (800, "flat"): 1362,
        (800, "pattern"): 1261,
    }
    conditions: dict[str, Any] = {}
    raw_values: dict[tuple[int, str], list[tuple[float, float]]] = {}
    title_anomalies: list[dict[str, str]] = []
    for key, name in IV_FILES.items():
        rows = _csv_rows(members[name], name)
        values = _numeric_pairs(rows, name)
        if len(values) != expected_counts[key]:
            raise SofcMicropatterningScientificIntakeError(f"unexpected I-V row count for {name}")
        title = rows[0][0] if rows and rows[0] else ""
        expected_prefix = "A-C"
        if not title.startswith(expected_prefix):
            title_anomalies.append({"file": name, "observed_title": title, "expected_family": expected_prefix})
        positive = [(current, voltage, current * voltage) for current, voltage in values if current >= 0 and voltage >= 0]
        if not positive:
            raise SofcMicropatterningScientificIntakeError(f"{name} has no positive-power quadrant")
        peak = max(positive, key=lambda item: item[2])
        temperature, structure = key
        label = f"{temperature}_{structure}"
        conditions[label] = {
            "temperature_c": temperature,
            "structure": structure,
            "source_file": name,
            "numeric_point_count": len(values),
            "current_density_min_a_cm2": min(item[0] for item in values),
            "current_density_max_a_cm2": max(item[0] for item in values),
            "voltage_min_v": min(item[1] for item in values),
            "voltage_max_v": max(item[1] for item in values),
            "descriptive_peak_power_density_w_cm2": peak[2],
            "peak_power_current_density_a_cm2": peak[0],
            "peak_power_voltage_v": peak[1],
            "point_count_is_independent_n": False,
        }
        raw_values[key] = values
    paired = {
        str(temperature): {
            "flat_peak_power_density_w_cm2": conditions[f"{temperature}_flat"]["descriptive_peak_power_density_w_cm2"],
            "pattern_peak_power_density_w_cm2": conditions[f"{temperature}_pattern"]["descriptive_peak_power_density_w_cm2"],
            "pattern_minus_flat_w_cm2": (
                conditions[f"{temperature}_pattern"]["descriptive_peak_power_density_w_cm2"]
                - conditions[f"{temperature}_flat"]["descriptive_peak_power_density_w_cm2"]
            ),
            "descriptive_only_no_replicate_inference": True,
        }
        for temperature in (600, 700, 800)
    }
    return {"conditions": conditions, "raw_values": raw_values, "paired_descriptive_peak_power": paired, "title_anomalies": title_anomalies}


def _ocv_intake(members: Mapping[str, bytes]) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    for (temperature, structure), name in OCV_FILES.items():
        values = _numeric_pairs(_csv_rows(members[name], name), name)
        if len(values) != 18000:
            raise SofcMicropatterningScientificIntakeError(f"unexpected OCV sample count for {name}")
        times = [item[0] for item in values]
        voltage = [item[1] for item in values]
        intervals = [right - left for left, right in zip(times, times[1:])]
        if not intervals or max(abs(item - 0.2) for item in intervals) > 1e-8:
            raise SofcMicropatterningScientificIntakeError(f"OCV sampling interval changed for {name}")
        conditions[f"{temperature}_{structure}"] = {
            "temperature_c": temperature,
            "structure": structure,
            "time_sample_count": len(values),
            "sampling_interval_s": 0.2,
            "observed_span_s": times[-1] - times[0],
            "mean_voltage_v": statistics.fmean(voltage),
            "min_voltage_v": min(voltage),
            "max_voltage_v": max(voltage),
            "time_samples_are_independent_specimens": False,
        }
    return {"conditions": conditions, "replicate_independence_established": False}


def _impedance_intake(members: Mapping[str, bytes]) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    reference_grid: list[float] | None = None
    for (configuration, temperature, structure), name in IMPEDANCE_FILES.items():
        rows = _csv_rows(members[name], name)
        values: list[tuple[float, float, float]] = []
        for row in rows:
            if len(row) < 4:
                continue
            try:
                frequency = float(row[1])
                real_z = float(row[2])
                imag_z = float(row[3])
            except ValueError:
                continue
            if not all(math.isfinite(item) for item in (frequency, real_z, imag_z)):
                raise SofcMicropatterningScientificIntakeError(f"non-finite impedance in {name}")
            values.append((frequency, real_z, imag_z))
        if len(values) != 71:
            raise SofcMicropatterningScientificIntakeError(f"unexpected impedance point count for {name}")
        grid = [item[0] for item in values]
        if reference_grid is None:
            reference_grid = grid
        elif grid != reference_grid:
            raise SofcMicropatterningScientificIntakeError("impedance frequency grids differ")
        label = f"{configuration}|{temperature}|{structure}"
        conditions[label] = {
            "configuration": configuration,
            "temperature_c": temperature,
            "structure": structure,
            "frequency_point_count": len(values),
            "frequency_max_hz": grid[0],
            "frequency_min_hz": grid[-1],
            "frequency_points_are_independent_specimens": False,
        }
    if reference_grid is None or reference_grid[0] != 1_000_000 or reference_grid[-1] != 0.1:
        raise SofcMicropatterningScientificIntakeError("impedance frequency bounds changed")
    return {
        "condition_count": len(conditions),
        "conditions": conditions,
        "common_frequency_grid_established": True,
        "frequency_grid_point_count": 71,
        "configuration_count": 3,
        "equivalent_circuit_validated_from_raw_impedance": False,
        "replicate_independence_established": False,
    }


def _uv_intake(members: Mapping[str, bytes]) -> dict[str, Any]:
    rows = _csv_rows(members[UV_RAW], UV_RAW)
    values: list[tuple[float, float, float, float]] = []
    for row in rows:
        if len(row) < 4:
            continue
        try:
            item = tuple(float(value) for value in row[:4])
        except ValueError:
            continue
        if not all(math.isfinite(value) for value in item):
            raise SofcMicropatterningScientificIntakeError("UV data contain non-finite value")
        values.append(item)  # type: ignore[arg-type]
    if len(values) != 11:
        raise SofcMicropatterningScientificIntakeError("UV raw point count changed")
    baseline = values[0]
    normalized = {
        item[0]: [item[1] / baseline[1], item[2] / baseline[2], item[3] / baseline[3]]
        for item in values
    }
    return {
        "point_count": len(values),
        "distance_mm": [item[0] for item in values],
        "initial_uv_strength_mw_cm2": {
            "non_material_layer": baseline[1],
            "without_antihalation": baseline[2],
            "with_antihalation": baseline[3],
        },
        "normalized_by_initial": normalized,
        "spatial_points_are_independent_specimens": False,
    }


def _profile_intake(members: Mapping[str, bytes]) -> dict[str, Any]:
    rows = _csv_rows(members[PROFILE], PROFILE)
    if len(rows) < 4 or rows[0][:4] != ["X", "Height", "Height", "Heigh"]:
        raise SofcMicropatterningScientificIntakeError("profile header changed")
    profiles: list[list[tuple[float, float]]] = [[], [], []]
    x_count = 0
    for row in rows[3:]:
        if len(row) < 1:
            continue
        try:
            x = float(row[0])
        except ValueError:
            continue
        x_count += 1
        for index in range(3):
            if len(row) <= index + 1 or row[index + 1] == "":
                continue
            y = _decimal(row[index + 1], f"profile {index + 1}")
            profiles[index].append((x, y))
    if x_count != 907 or [len(item) for item in profiles] != [907, 727, 826]:
        raise SofcMicropatterningScientificIntakeError("profile coverage changed")
    summary = []
    for index, profile in enumerate(profiles, start=1):
        heights = [item[1] for item in profile]
        summary.append(
            {
                "profile": f"Prof{index}",
                "point_count": len(profile),
                "x_min_um": profile[0][0],
                "x_max_um": profile[-1][0],
                "height_min_um": min(heights),
                "height_max_um": max(heights),
                "peak_to_valley_um": max(heights) - min(heights),
            }
        )
    return {
        "source_header_anomaly": "Heigh",
        "x_row_count": x_count,
        "profiles": summary,
        "profile_lengths_equal": False,
        "three_profiles_are_independent_cells": False,
    }


def _iv_summary_reconciliation(rows: list[list[Any]], raw: Mapping[tuple[int, str], list[tuple[float, float]]]) -> dict[str, Any]:
    if len(rows) != 1264 or len(rows[0]) < 18:
        raise SofcMicropatterningScientificIntakeError("I-V-P summary shape changed")
    blocks = [
        ((800, "pattern"), 0),
        ((700, "pattern"), 3),
        ((600, "pattern"), 6),
        ((800, "flat"), 9),
        ((700, "flat"), 12),
        ((600, "flat"), 15),
    ]
    result: dict[str, Any] = {}
    for key, column in blocks:
        summary: list[tuple[float, float, float]] = []
        for row in rows[3:]:
            if len(row) <= column + 2 or row[column] is None or row[column + 1] is None or row[column + 2] is None:
                break
            summary.append(
                (
                    _decimal(row[column], "summary current"),
                    _decimal(row[column + 1], "summary voltage"),
                    _decimal(row[column + 2], "summary power"),
                )
            )
        if len(summary) != 1261:
            raise SofcMicropatterningScientificIntakeError("I-V-P block row count changed")
        source = raw[key]
        power_matches_raw = all(
            abs(power - current * voltage) <= 5.1e-6
            for (_, _, power), (current, voltage) in zip(summary, source)
        )
        if not power_matches_raw:
            raise SofcMicropatterningScientificIntakeError("summary power no longer reconciles to raw I-V")
        copy_current_voltage_matches = all(
            abs(s_current - r_current) <= 1.1e-5 and abs(s_voltage - r_voltage) <= 5.1e-6
            for (s_current, s_voltage, _), (r_current, r_voltage) in zip(summary, source)
        )
        label = f"{key[0]}_{key[1]}"
        result[label] = {
            "summary_row_count": len(summary),
            "raw_row_count": len(source),
            "raw_rows_omitted_from_summary": len(source) - len(summary),
            "summary_power_reconciles_to_raw_product_with_display_rounding": True,
            "summary_current_voltage_reconcile_to_raw_with_display_rounding": copy_current_voltage_matches,
            "summary_current_unique_count": len({item[0] for item in summary}),
            "summary_voltage_unique_count": len({item[1] for item in summary}),
        }
    flat600 = result["600_flat"]
    if flat600["summary_current_unique_count"] != 1 or flat600["summary_voltage_unique_count"] != 1:
        raise SofcMicropatterningScientificIntakeError("expected 600 C flat stale-column anomaly changed")
    if flat600["summary_current_voltage_reconcile_to_raw_with_display_rounding"] is not False:
        raise SofcMicropatterningScientificIntakeError("600 C flat summary unexpectedly reconciled")
    return {
        "common_summary_row_count": 1261,
        "blocks": result,
        "derived_representation_only": True,
        "information_truncation_present": any(item["raw_rows_omitted_from_summary"] > 0 for item in result.values()),
        "stale_column_anomaly": {
            "condition": "600_flat",
            "current_and_voltage_columns_repeat_first_values": True,
            "power_column_continues_to_reconcile_to_raw_product": True,
        },
    }


def _uv_summary_reconciliation(rows: list[list[Any]], uv: Mapping[str, Any]) -> dict[str, Any]:
    if len(rows) < 21 or len(rows[0]) < 4:
        raise SofcMicropatterningScientificIntakeError("UV summary shape changed")
    if [_decimal(rows[1][index], "UV strength") for index in range(1, 4)] != [42.0, 5.0, 3.0]:
        raise SofcMicropatterningScientificIntakeError("UV summary initial strengths changed")
    expected_distances = [0.0, 1.0, 2.0, 6.0, 8.0]
    for offset, distance in enumerate(expected_distances, start=16):
        if _decimal(rows[offset][0], "UV summary distance") != distance:
            raise SofcMicropatterningScientificIntakeError("UV summary selected distances changed")
        expected = uv["normalized_by_initial"][distance]
        observed = [_decimal(rows[offset][index], "UV normalized") for index in range(1, 4)]
        if any(abs(left - right) > 5e-4 for left, right in zip(observed, expected)):
            raise SofcMicropatterningScientificIntakeError("UV summary no longer matches raw normalization")
    return {
        "selected_distance_mm": expected_distances,
        "raw_point_count": uv["point_count"],
        "summary_selected_point_count": len(expected_distances),
        "summary_is_rounded_subset_of_raw_normalization": True,
        "independent_evidence": False,
    }


def _fit_audit(rows: list[list[Any]], structure: str) -> dict[str, Any]:
    if len(rows) < 13 or max(len(row) for row in rows) < 41:
        raise SofcMicropatterningScientificIntakeError(f"{structure} fitting workbook shape changed")
    conditions: dict[str, Any] = {}
    current_header: list[Any] | None = None
    for row in rows:
        if len(row) > 1 and row[1] == "Chi-Sqr":
            current_header = row
            continue
        if current_header is None or not row or not isinstance(row[0], str):
            continue
        temperature_match = re.search(r"(600|700|800)", row[0])
        if temperature_match is None:
            continue
        temperature = int(temperature_match.group(1))
        error_percentages = []
        for index, header in enumerate(current_header):
            if isinstance(header, str) and header.endswith("Error%") and index < len(row) and row[index] is not None:
                error_percentages.append(_decimal(row[index], f"{structure} fitting error%"))
        if not error_percentages:
            raise SofcMicropatterningScientificIntakeError("fitting workbook lacks parameter errors")
        conditions[str(temperature)] = {
            "chi_square": _decimal(row[1], "fit chi-square"),
            "max_reported_parameter_error_percent": max(error_percentages),
            "has_reported_parameter_error_above_100_percent": any(value > 100 for value in error_percentages),
            "asr_ohmic_ohm_cm2": _decimal(row[38], "ASR ohmic"),
            "asr_polarization_ohm_cm2": _decimal(row[40], "ASR polarization"),
        }
    if set(conditions) != {"600", "700", "800"}:
        raise SofcMicropatterningScientificIntakeError("fitting workbook temperature grid changed")
    return {
        "structure": structure,
        "conditions": conditions,
        "equivalent_circuit_component_identity_validated": False,
        "fit_parameters_are_independent_measurements": False,
    }


def _drt_audit(rows: list[list[Any]]) -> dict[str, Any]:
    if len(rows) != 713 or len(rows[0]) < 12:
        raise SofcMicropatterningScientificIntakeError("DRT summary shape changed")
    conditions = rows[0][::2][:6]
    data = rows[3:]
    counts = []
    first_frequency = []
    last_frequency = []
    for column in range(0, 12, 2):
        values = [row[column] for row in data if len(row) > column and row[column] is not None]
        counts.append(len(values))
        first_frequency.append(_decimal(values[0], "DRT first frequency"))
        last_frequency.append(_decimal(values[-1], "DRT last frequency"))
    if counts != [710] * 6:
        raise SofcMicropatterningScientificIntakeError("DRT condition row counts changed")
    return {
        "conditions": conditions,
        "derived_curve_points_per_condition": 710,
        "first_frequency_hz": first_frequency[0],
        "last_frequency_hz": last_frequency[0],
        "raw_a_r_impedance_points_per_condition": 71,
        "derived_dense_curve_points_are_new_physical_measurements": False,
        "drt_inverse_problem_validated_here": False,
    }


def _porosity_audit(rows: list[list[Any]]) -> dict[str, Any]:
    if len(rows) < 5 or max(len(row) for row in rows) < 8:
        raise SofcMicropatterningScientificIntakeError("porosity workbook shape changed")
    dot = rows[3]
    line = rows[4]
    if dot[3] != "Dot" or line[3] != "L&S":
        raise SofcMicropatterningScientificIntakeError("porosity labels changed")
    return {
        "dot": {
            "total_image_pixels": int(_decimal(dot[4], "dot total image")),
            "pore_area_pixels": int(_decimal(dot[5], "dot pore area")),
            "porosity_percent": _decimal(dot[6], "dot porosity"),
        },
        "line_and_space": {
            "total_image_pixels": int(_decimal(line[4], "L&S total image")),
            "pore_area_pixels": int(_decimal(line[5], "L&S pore area")),
            "porosity_percent": _decimal(line[6], "L&S porosity"),
        },
        "image_analysis_rows_are_independent_specimens": False,
        "source_image_to_electrochemical_cell_identity_established": False,
    }


def audit_sofc_micropatterning_archive(archive_bytes: bytes) -> dict[str, Any]:
    members = _archive_members(archive_bytes)
    archive_sha = _sha(archive_bytes)
    source_bindings = {name: {"sha256": _sha(body), "size_bytes": len(body)} for name, body in sorted(members.items())}

    iv = _iv_intake(members)
    ocv = _ocv_intake(members)
    impedance = _impedance_intake(members)
    uv = _uv_intake(members)
    profile = _profile_intake(members)

    initial = {
        "schema_version": SCHEMA_VERSION,
        "archive_sha256": archive_sha,
        "source_bindings": source_bindings,
        "raw_iv": {key: value for key, value in iv.items() if key != "raw_values"},
        "raw_ocv": ocv,
        "raw_impedance": impedance,
        "raw_uv": uv,
        "raw_single_dot_profile": profile,
        "experimental_unit_boundary": {
            "named_structure_levels": ["flat", "pattern"],
            "named_temperature_levels_c": [600, 700, 800],
            "independent_cell_or_specimen_ids_present": False,
            "replicate_independence_established": False,
            "time_frequency_curve_or_profile_points_are_independent_n": False,
            "sem_or_optical_image_to_electrochemical_cell_join_established": False,
        },
        "source_anomalies": [
            *iv["title_anomalies"],
            {
                "file": PROFILE,
                "observed_header": "Heigh",
                "issue": "truncated_height_header_and_unequal_profile_lengths",
            },
        ],
        "weaknesses": [
            "independent_cell_or_specimen_replication_not_established",
            "sem_and_optical_images_not_authoritatively_joined_to_electrochemical_cell_identity",
            "derived_workbooks_require_raw_reconciliation_before_use",
            "equivalent_circuit_and_drt_model_validity_not_established_by_raw_measurements_alone",
            "700_pattern_iv_title_uses_A-V_while_peer_iv_files_use_A-C",
            "single_50um_dot_profile_columns_have_unequal_spatial_coverage",
        ],
        "selected_next_action": "raw_derived_reconciliation_and_cell_lineage_audit",
        "strongest_eligible_claim": (
            "The released raw traces support descriptive flat-versus-pattern comparisons within named temperature and configuration labels; "
            "they do not establish an independent-replicate treatment effect."
        ),
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    initial["report_sha256"] = _canonical_sha(initial)

    iv_reconciliation = _iv_summary_reconciliation(_xlsx_rows(members[IV_SUMMARY]), iv["raw_values"])
    uv_reconciliation = _uv_summary_reconciliation(_xlsx_rows(members[UV_SUMMARY]), uv)
    fit_flat = _fit_audit(_xlsx_rows(members[FIT_FLAT]), "flat")
    fit_pattern = _fit_audit(_xlsx_rows(members[FIT_PATTERN]), "pattern")
    drt = _drt_audit(_xlsx_rows(members[DRT_SUMMARY]))
    porosity = _porosity_audit(_xlsx_rows(members[POROSITY]))

    reanalysis = {
        "schema_version": SCHEMA_VERSION,
        "archive_sha256": archive_sha,
        "parent_initial_report_sha256": initial["report_sha256"],
        "executed_action": "raw_derived_reconciliation_and_cell_lineage_audit",
        "iv_summary_reconciliation": iv_reconciliation,
        "uv_summary_reconciliation": uv_reconciliation,
        "a_r_equivalent_circuit_fitting": {
            "flat": fit_flat,
            "pattern": fit_pattern,
            "reported_asr_polarization_pattern_below_flat_at_all_three_temperatures": all(
                fit_pattern["conditions"][str(temperature)]["asr_polarization_ohm_cm2"]
                < fit_flat["conditions"][str(temperature)]["asr_polarization_ohm_cm2"]
                for temperature in (600, 700, 800)
            ),
            "fit_identifiability_warning_present": any(
                item["has_reported_parameter_error_above_100_percent"]
                for result in (fit_flat, fit_pattern)
                for item in result["conditions"].values()
            ),
            "asr_difference_is_causal_treatment_evidence": False,
        },
        "drt_representation": drt,
        "porosity_representation": porosity,
        "cell_lineage_reaudit": {
            "independent_cell_or_specimen_ids_recovered": False,
            "replicate_independence_recovered": False,
            "sem_to_electrochemistry_cell_join_recovered": False,
            "filename_or_folder_order_used_as_join_key": False,
        },
        "new_source_anomalies": [
            {
                "file": IV_SUMMARY,
                "condition": "600_flat",
                "issue": "current_and_voltage_columns_repeat_first_values_while_power_tracks_raw_curve",
            },
            {
                "file": IV_SUMMARY,
                "issue": "summary_truncates_longer_raw_iv_curves_to_1261_rows",
            },
            {
                "files": [FIT_FLAT, FIT_PATTERN],
                "issue": "some_reported_equivalent_circuit_parameter_error_percentages_exceed_100_percent",
            },
        ],
        "remaining_blockers": [
            "no_independent_cell_or_specimen_replication_contract",
            "no_authoritative_sem_or_optical_image_to_electrochemical_cell_join",
            "derived_iv_summary_contains_stale_columns_and_truncation",
            "equivalent_circuit_parameter_identifiability_not_uniformly_supported",
            "drt_is_dense_derived_representation_not_additional_physical_frequency_sampling",
            "porosity_workbook_exposes_single_image_analysis_values_without_replicate_lineage",
        ],
        "terminal_decision": "bounded_stop_source_bytes_exhausted_for_requested_lineage_and_model_validity",
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    reanalysis["reanalysis_sha256"] = _canonical_sha(reanalysis)

    sequence = {
        "schema_version": SCHEMA_VERSION,
        "archive_sha256": archive_sha,
        "initial_report_sha256": initial["report_sha256"],
        "selected_action": initial["selected_next_action"],
        "reanalysis_sha256": reanalysis["reanalysis_sha256"],
        "full_bounded_research_cycle_completed": True,
        "stop_reason": reanalysis["terminal_decision"],
        "independent_replicate_effect_claim_authorized": False,
        "geometry_to_performance_causal_claim_authorized": False,
        "sem_to_performance_mechanism_claim_authorized": False,
        "scientific_status_changed": False,
    }
    sequence["sequence_sha256"] = _canonical_sha(sequence)
    return {"initial_intake": initial, "reanalysis": reanalysis, "episode_sequence": sequence}


__all__ = [
    "SofcMicropatterningScientificIntakeError",
    "audit_sofc_micropatterning_archive",
]
