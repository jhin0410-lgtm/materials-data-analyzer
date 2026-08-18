"""Exact scientific intake for the SSRM Ti/Ti6Al4V/Ti5553 Zenodo archive.

The adapter reads only explicitly selected members from an already checksum-bound ZIP.
File-description workbook statements are the authority for material/time semantics; file
names alone never become sample identity.  Descriptive evidence is separated from
replicate independence and cross-technique aliquot claims.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "1.0"
ROOT = "SSRM of Ti, Ti6Al4V, Ti5553"
DESCRIPTION = f"{ROOT}/description/files descriptions.xlsx"
ELEMENTAL = f"{ROOT}/raw data/elemental analysis/elemental analysis Ti_Ti6Al4V_Ti5553.xlsx"
EDS_RAW = f"{ROOT}/raw data/chemical composition analysis/Ti64_10h_N.xlsx"
EDS_PROCESSED = f"{ROOT}/processed data/chemical composition analysis/N_content.xlsx"
RAMAN = {
    "Ti": f"{ROOT}/processed data/Raman spectroscopy/Raman_Ti.xlsx",
    "Ti6Al4V": f"{ROOT}/processed data/Raman spectroscopy/Raman_Ti64.xlsx",
    "Ti5553": f"{ROOT}/processed data/Raman spectroscopy/Raman_Ti5553.xlsx",
}
LOGGER = {
    "Ti": f"{ROOT}/raw data/temperature and nitrogen pressure/66573_DC_TiGd1_500_50_10h_3.csv",
    "Ti6Al4V": f"{ROOT}/raw data/temperature and nitrogen pressure/66573_DC_Ti64_500_50_10h_3.csv",
    "Ti5553": f"{ROOT}/raw data/temperature and nitrogen pressure/66573_DC_Ti5553_500_50_10h_3.csv",
}

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_CONDITION_RE = re.compile(
    r"^(?P<alias>TiGd1|Ti64|Ti5553)(?:_500_50_(?P<time>5min|15min|30min|60min|600min))?$"
)


class SsrmTitaniumScientificIntakeError(ValueError):
    """Raised when exact source bytes cannot support the declared intake."""


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_sha(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _archive_members(archive_bytes: bytes) -> dict[str, bytes]:
    if not isinstance(archive_bytes, bytes):
        raise SsrmTitaniumScientificIntakeError("archive input must be exact bytes")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise SsrmTitaniumScientificIntakeError("archive repeats member names")
            required = {DESCRIPTION, ELEMENTAL, EDS_RAW, EDS_PROCESSED, *RAMAN.values(), *LOGGER.values()}
            missing = sorted(required - set(names))
            if missing:
                raise SsrmTitaniumScientificIntakeError(
                    f"required SSRM intake members are missing: {missing}"
                )
            return {name: archive.read(name) for name in required}
    except zipfile.BadZipFile as exc:
        raise SsrmTitaniumScientificIntakeError("SSRM source is not a valid ZIP") from exc


def _xlsx_rows(body: bytes) -> list[list[Any]]:
    """Read the first worksheet as exact values using only XLSX XML parts."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(body), "r")
    except zipfile.BadZipFile as exc:
        raise SsrmTitaniumScientificIntakeError("selected member is not a valid XLSX") from exc
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise SsrmTitaniumScientificIntakeError("XLSX repeats ZIP member names")
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            raise SsrmTitaniumScientificIntakeError("XLSX workbook parts are missing")
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
            raise SsrmTitaniumScientificIntakeError("XLSX has no worksheet")
        first = sheets[0]
        rel_id = first.attrib.get(f"{{{_REL_NS}}}id")
        target = rel_map.get(rel_id or "")
        if not target:
            raise SsrmTitaniumScientificIntakeError("first worksheet target is missing")
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target.lstrip("/")
        if member not in names:
            raise SsrmTitaniumScientificIntakeError("worksheet XML is missing")
        root = ET.fromstring(archive.read(member))
        rows: dict[int, dict[str, Any]] = {}
        max_col = 0
        for row in root.findall(f".//{{{_NS}}}sheetData/{{{_NS}}}row"):
            row_number = int(row.attrib["r"])
            if row_number in rows:
                raise SsrmTitaniumScientificIntakeError("XLSX repeats row number")
            cells: dict[str, Any] = {}
            for cell in row.findall(f"{{{_NS}}}c"):
                ref = cell.attrib.get("r", "")
                match = _CELL_RE.fullmatch(ref)
                if not match or int(match.group(2)) != row_number:
                    raise SsrmTitaniumScientificIntakeError(f"invalid XLSX cell reference {ref!r}")
                col = match.group(1)
                value_node = cell.find(f"{{{_NS}}}v")
                cell_type = cell.attrib.get("t")
                if cell_type == "s":
                    if value_node is None or value_node.text is None:
                        value = None
                    else:
                        value = shared[int(value_node.text)]
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
                index = 0
                for ch in col:
                    index = index * 26 + ord(ch) - ord("A") + 1
                max_col = max(max_col, index)
            rows[row_number] = cells
        result: list[list[Any]] = []
        for row_number in sorted(rows):
            values: list[Any] = []
            for index in range(1, max_col + 1):
                n = index
                col = ""
                while n:
                    n, rem = divmod(n - 1, 26)
                    col = chr(ord("A") + rem) + col
                values.append(rows[row_number].get(col))
            result.append(values)
        return result


def _description_contract(rows: list[list[Any]]) -> dict[str, Any]:
    text = "\n".join(str(value) for row in rows for value in row if value is not None)
    required = {
        "ti_alias": "TiGd1 - Ti powder at the initial (as-received) stage",
        "ti64_alias": "Ti64 - Ti6Al4V powder at the initial (as-received) stage",
        "ti5553_alias": "Ti5553 - Ti5553 powder at the initial (as-received) stage",
        "ti_logger": "The temperature and pressure signals within the cylinder colected during milling of Ti powder under nitrogen pressure",
        "ti64_logger": "The temperature and pressure signals within the cylinder colected during milling of Ti6Al4V powder under nitrogen pressure",
        "ti5553_logger": "The temperature and pressure signals within the cylinder colected during milling of Ti5553 powder under nitrogen pressure",
        "eds": "EDS line scan of nitrogen content in Ti64 powder milled for 10 h under nitrogen pressure",
        "raman_ti": "Raman data for Ti powder at the initial stage or milled for 5, 15, 30, 60 and 600 min",
        "raman_ti64": "Raman data for Ti6Al4V powder at the initial stage or milled for 5, 15, 30, 60 and 600 min",
        "raman_ti5553": "Raman data for Ti5553 powder at the initial stage or milled for 5, 15, 30, 60 and 600 min",
        "elemental": "Ti, Ti6Al4V and Ti5553 powders at the initial stage or milled for 5, 15, 30, 60 and 600 min",
    }
    missing = [label for label, token in required.items() if token not in text]
    if missing:
        raise SsrmTitaniumScientificIntakeError(
            f"description workbook no longer supports declared semantics: {missing}"
        )
    return {
        "alias_map": {"TiGd1": "Ti", "Ti64": "Ti6Al4V", "Ti5553": "Ti5553"},
        "milling_speed_rpm": 500,
        "nitrogen_pressure_bar": 50,
        "declared_characterization_times_min": [0, 5, 15, 30, 60, 600],
        "logger_active_window_explicitly_marked": False,
        "raman_p1_to_p10_semantics_explicitly_defined": False,
        "suffix_1_or_3_replicate_semantics_explicitly_defined": False,
        "cross_technique_identical_aliquot_explicitly_defined": False,
    }


def _decimal(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise SsrmTitaniumScientificIntakeError(f"{field} must be decimal")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip() == value:
        try:
            number = float(value)
        except ValueError as exc:
            raise SsrmTitaniumScientificIntakeError(f"{field} is not decimal") from exc
    else:
        raise SsrmTitaniumScientificIntakeError(f"{field} is not decimal")
    if not math.isfinite(number):
        raise SsrmTitaniumScientificIntakeError(f"{field} must be finite")
    return number


def _elemental_analysis(rows: list[list[Any]], alias_map: dict[str, str]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    index = 1
    while index < len(rows):
        name = rows[index][0] if rows[index] else None
        if name is None:
            index += 1
            continue
        name_text = str(name).strip()
        if name_text in {"Mean value", "Deviation (abs.)"}:
            index += 1
            continue
        if index + 3 >= len(rows):
            break
        next_name = str(rows[index + 1][0]).strip() if rows[index + 1][0] is not None else ""
        mean_label = str(rows[index + 2][0]).strip() if rows[index + 2][0] is not None else ""
        dev_label = str(rows[index + 3][0]).strip() if rows[index + 3][0] is not None else ""
        if next_name != name_text or mean_label != "Mean value" or dev_label != "Deviation (abs.)":
            index += 1
            continue
        match = _CONDITION_RE.fullmatch(name_text)
        if match is None:
            raise SsrmTitaniumScientificIntakeError(f"unexpected elemental condition {name_text!r}")
        alias = match.group("alias")
        material = alias_map[alias]
        time_token = match.group("time")
        time_min = 0 if time_token is None else int(time_token.removesuffix("min"))
        measurements = [_decimal(rows[index][1], "N [%]"), _decimal(rows[index + 1][1], "N [%]")]
        source_mean = _decimal(rows[index + 2][1], "source mean N [%]")
        source_deviation = _decimal(rows[index + 3][1], "source deviation N [%]")
        blocks.append(
            {
                "source_condition": name_text,
                "material": material,
                "time_min": time_min,
                "measurement_values_n_percent": measurements,
                "measurement_row_count": 2,
                "measurement_independence_established": False,
                "source_reported_mean_n_percent": source_mean,
                "source_reported_deviation_abs_n_percent": source_deviation,
                "displayed_measurement_arithmetic_mean_n_percent": sum(measurements) / 2,
            }
        )
        index += 4
    expected = {(material, time) for material in alias_map.values() for time in (0, 5, 15, 30, 60, 600)}
    observed = {(item["material"], item["time_min"]) for item in blocks}
    if len(blocks) != 18 or observed != expected:
        raise SsrmTitaniumScientificIntakeError("elemental-analysis condition grid is incomplete")
    by_material: dict[str, list[dict[str, Any]]] = {}
    for material in ("Ti", "Ti6Al4V", "Ti5553"):
        items = sorted((item for item in blocks if item["material"] == material), key=lambda item: item["time_min"])
        means = [item["source_reported_mean_n_percent"] for item in items]
        by_material[material] = items
        for item, mean in zip(items, means):
            item["source_mean_is_display_rounded_not_recomputed"] = abs(
                item["displayed_measurement_arithmetic_mean_n_percent"] - mean
            ) > 1e-12
    trend = {
        material: {
            "initial_source_mean_n_percent": items[0]["source_reported_mean_n_percent"],
            "600min_source_mean_n_percent": items[-1]["source_reported_mean_n_percent"],
            "initial_to_600min_increase": items[-1]["source_reported_mean_n_percent"] > items[0]["source_reported_mean_n_percent"],
            "source_mean_nondecreasing_from_5min": all(
                right["source_reported_mean_n_percent"] >= left["source_reported_mean_n_percent"]
                for left, right in zip(items[1:], items[2:])
            ),
            "max_two_measurement_spread_n_percent": max(
                abs(item["measurement_values_n_percent"][0] - item["measurement_values_n_percent"][1])
                for item in items
            ),
        }
        for material, items in by_material.items()
    }
    rounded_mismatch_count = sum(
        item["source_mean_is_display_rounded_not_recomputed"] for item in blocks
    )
    return {
        "condition_count": len(blocks),
        "source_measurement_rows": 36,
        "measurement_independence_established": False,
        "conditions": blocks,
        "descriptive_source_mean_trends": trend,
        "source_mean_not_exactly_reconstructed_from_displayed_two_values_count": rounded_mismatch_count,
    }


def _eds_reconciliation(raw_rows: list[list[Any]], processed_rows: list[list[Any]]) -> dict[str, Any]:
    if len(raw_rows) < 104 or len(processed_rows) < 101:
        raise SsrmTitaniumScientificIntakeError("EDS source rows are incomplete")
    if [str(value).strip() if value is not None else None for value in raw_rows[3][:4]] != [
        "Point", "Distance", "N K", "SE1"
    ]:
        raise SsrmTitaniumScientificIntakeError("raw EDS headers changed")
    if [str(value).strip() if value is not None else None for value in processed_rows[0][:2]] != [
        "Distance", "N K"
    ]:
        raise SsrmTitaniumScientificIntakeError("processed EDS headers changed")
    raw_pairs = [(_decimal(row[1], "EDS distance"), _decimal(row[2], "EDS N K")) for row in raw_rows[4:104]]
    processed_pairs = [(_decimal(row[0], "EDS distance"), _decimal(row[1], "EDS N K")) for row in processed_rows[1:101]]
    if raw_pairs != processed_pairs:
        raise SsrmTitaniumScientificIntakeError("processed EDS line scan does not reproduce raw Distance/N K pairs")
    return {
        "material": "Ti6Al4V",
        "time_min": 600,
        "point_count": 100,
        "processed_distance_nk_exactly_reproduces_raw": True,
        "line_scan_is_not_independent_specimen_replication": True,
        "other_materials_or_times_eds_line_scan_present": False,
    }


def _raman_audit(rows: list[list[Any]], material: str) -> dict[str, Any]:
    if len(rows) != 1215 or len(rows[0]) < 13 or rows[0][0] != "Wave":
        raise SsrmTitaniumScientificIntakeError(f"processed Raman shape changed for {material}")
    pairs = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)]
    pair_reports: list[dict[str, Any]] = []
    for left, right in pairs:
        diffs: list[float] = []
        for row in rows[1:]:
            diffs.append(_decimal(row[right], "Raman intensity") - _decimal(row[left], "Raman intensity"))
        reference = diffs[0]
        if not all(abs(value - reference) <= 1e-8 for value in diffs):
            raise SsrmTitaniumScientificIntakeError(
                f"Raman paired columns are not exact constant-offset representations for {material}"
            )
        pair_reports.append(
            {
                "left_header": str(rows[0][left]),
                "right_header": str(rows[0][right]),
                "point_count": len(diffs),
                "right_minus_left_constant_offset": float(format(reference, ".15g")),
                "independent_spectra_count_from_pair": 1,
                "second_column_is_deterministic_plot_offset_copy": True,
            }
        )
    return {
        "material": material,
        "wave_point_count": len(rows) - 1,
        "display_column_pair_count": len(pair_reports),
        "paired_columns": pair_reports,
        "independent_replicate_count_established": False,
        "raw_p1_to_p10_mapping_to_processed_spectrum_established": False,
    }


def _logger_audit(body: bytes, material: str) -> dict[str, Any]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SsrmTitaniumScientificIntakeError("logger CSV must be UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ["#", "Time", "P (Bar)", "T (°C)"]:
        raise SsrmTitaniumScientificIntakeError(f"logger CSV headers changed for {material}")
    records: list[tuple[datetime, float, float]] = []
    for row in reader:
        try:
            timestamp = datetime.strptime(row["Time"].strip("'"), "%m-%d-%Y %H:%M:%S.%f")
        except ValueError as exc:
            raise SsrmTitaniumScientificIntakeError(f"logger timestamp invalid for {material}") from exc
        records.append((timestamp, _decimal(row["P (Bar)"], "pressure"), _decimal(row["T (°C)"], "temperature")))
    if len(records) < 2:
        raise SsrmTitaniumScientificIntakeError("logger trace is too short")
    steps = [int((right[0] - left[0]).total_seconds()) for left, right in zip(records, records[1:])]
    span_h = (records[-1][0] - records[0][0]).total_seconds() / 3600
    pressure = [row[1] for row in records]
    temperature = [row[2] for row in records]
    return {
        "material": material,
        "row_count": len(records),
        "start_timestamp_source": records[0][0].isoformat(),
        "end_timestamp_source": records[-1][0].isoformat(),
        "logger_span_hours": float(format(span_h, ".12g")),
        "declared_milling_duration_hours": 10,
        "logger_span_exceeds_declared_milling_duration": span_h > 10,
        "sampling_interval_seconds_counts": dict(sorted(Counter(steps).items())),
        "pressure_bar_min": min(pressure),
        "pressure_bar_max": max(pressure),
        "temperature_c_min": min(temperature),
        "temperature_c_max": max(temperature),
        "full_trace_mean_not_interpreted_as_10h_milling_mean": True,
        "active_milling_window_established": False,
    }


def audit_ssrm_titanium_archive(archive_bytes: bytes) -> dict[str, Any]:
    members = _archive_members(archive_bytes)
    description = _description_contract(_xlsx_rows(members[DESCRIPTION]))
    elemental = _elemental_analysis(_xlsx_rows(members[ELEMENTAL]), description["alias_map"])
    eds = _eds_reconciliation(_xlsx_rows(members[EDS_RAW]), _xlsx_rows(members[EDS_PROCESSED]))
    raman = {material: _raman_audit(_xlsx_rows(members[path]), material) for material, path in RAMAN.items()}
    loggers = {material: _logger_audit(members[path], material) for material, path in LOGGER.items()}
    member_bindings = {
        path: {"sha256": _sha(body), "size_bytes": len(body)} for path, body in sorted(members.items())
    }
    initial = {
        "schema_version": SCHEMA_VERSION,
        "archive_sha256": _sha(archive_bytes),
        "selected_member_bindings": member_bindings,
        "description_contract": description,
        "elemental_nitrogen": elemental,
        "eds_line_scan": eds,
        "raman_processed_representation": raman,
        "temperature_pressure_loggers": loggers,
        "detected_weaknesses": [
            {
                "code": "elemental_duplicate_measurements_have_no_independence_identity",
                "severity": "blocks_inferential_replicate_count",
            },
            {
                "code": "temperature_pressure_logger_span_exceeds_declared_10h_milling",
                "severity": "blocks_full_trace_process_summary",
            },
            {
                "code": "raman_duplicate_labeled_columns_are_constant_offset_copies",
                "severity": "prevents_raman_pseudoreplication",
            },
            {
                "code": "cross_technique_aliquot_identity_unresolved",
                "severity": "blocks_joint_multimodal_sample_level_inference",
            },
            {
                "code": "eds_line_scan_scope_is_ti6al4v_600min_only",
                "severity": "limits_cross_material_surface_nitrogen_comparison",
            },
        ],
        "descriptive_result": {
            "source_reported_elemental_n_mean_increases_initial_to_600min_for_all_materials": all(
                item["initial_to_600min_increase"] for item in elemental["descriptive_source_mean_trends"].values()
            ),
            "source_reported_elemental_n_mean_nondecreasing_from_5min_for_all_materials": all(
                item["source_mean_nondecreasing_from_5min"] for item in elemental["descriptive_source_mean_trends"].values()
            ),
            "causal_milling_time_effect_established": False,
        },
        "bounded_next_action": {
            "action_type": "process_window_and_lineage_audit",
            "objective": "Search exact source descriptions/logger schema for an explicit active milling window and independent replicate/aliquot mapping before process-response or multimodal inference.",
        },
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    initial["report_sha256"] = _canonical_sha(initial)
    reanalysis = {
        "schema_version": SCHEMA_VERSION,
        "initial_report_sha256": initial["report_sha256"],
        "selected_next_action_type": "process_window_and_lineage_audit",
        "exact_description_reaudit": {
            "logger_active_window_explicitly_marked": description["logger_active_window_explicitly_marked"],
            "suffix_1_or_3_replicate_semantics_explicitly_defined": description[
                "suffix_1_or_3_replicate_semantics_explicitly_defined"
            ],
            "raman_p1_to_p10_semantics_explicitly_defined": description[
                "raman_p1_to_p10_semantics_explicitly_defined"
            ],
            "cross_technique_identical_aliquot_explicitly_defined": description[
                "cross_technique_identical_aliquot_explicitly_defined"
            ],
        },
        "logger_reaudit": {
            material: {
                "row_count": item["row_count"],
                "logger_span_hours": item["logger_span_hours"],
                "active_milling_window_established": item["active_milling_window_established"],
            }
            for material, item in loggers.items()
        },
        "raman_reaudit": {
            material: {
                "all_six_display_pairs_are_deterministic_offset_copies": all(
                    pair["second_column_is_deterministic_plot_offset_copy"] for pair in item["paired_columns"]
                ),
                "independent_replicate_count_established": item["independent_replicate_count_established"],
            }
            for material, item in raman.items()
        },
        "bounded_stop": True,
        "bounded_stop_reasons": [
            "no explicit active milling interval is encoded in the exact logger schema/description despite 40-46 h logger spans for nominal 10 h milling files",
            "suffix _1/_3 and Raman p1-p10 are not explicitly bound to independent replicate identity",
            "cross-technique identical physical aliquot identity is not established",
        ],
        "future_followups": [
            {"action": "obtain_process_state_or_active_window_metadata", "executed_in_this_episode": False},
            {"action": "obtain_explicit_replicate_and_aliquot_lineage", "executed_in_this_episode": False},
            {"action": "only_then_test_process_time_to_multimodal_response_associations", "executed_in_this_episode": False},
        ],
        "model_training_authorized": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    reanalysis["reanalysis_sha256"] = _canonical_sha(reanalysis)
    sequence = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": "zenodo-ssrm-titanium-nitriding-generalization",
        "initial_report_sha256": initial["report_sha256"],
        "next_action_type": initial["bounded_next_action"]["action_type"],
        "persisted_reanalysis_sha256": reanalysis["reanalysis_sha256"],
        "bounded_stop": True,
        "future_followups_kept_unexecuted": all(
            item["executed_in_this_episode"] is False for item in reanalysis["future_followups"]
        ),
        "full_bounded_research_cycle_completed": True,
        "scientific_status_changed": False,
    }
    sequence["sequence_sha256"] = _canonical_sha(sequence)
    return {"initial_intake": initial, "reanalysis": reanalysis, "episode_sequence": sequence}


__all__ = [
    "SCHEMA_VERSION",
    "SsrmTitaniumScientificIntakeError",
    "audit_ssrm_titanium_archive",
]
