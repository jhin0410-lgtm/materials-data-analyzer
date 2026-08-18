"""Exact scientific intake for the public Co-Cr corrosion electrochemistry dataset.

This adapter treats control/wear time-series acquisitions as repeated measurements unless
source identity proves otherwise.  It also detects the exact numerical transform in the
separate converted-control LPR workbook without inventing its physical rationale or
applying that transform to wear data.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "1.0"
_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_TIME_RE = re.compile(r"(?P<hours>\d+)\s*HOURS?", re.IGNORECASE)


class CocrCorrosionScientificIntakeError(ValueError):
    """Raised when exact workbook bytes cannot support the declared intake."""


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _col_index(col: str) -> int:
    value = 0
    for ch in col:
        value = value * 26 + ord(ch) - ord("A") + 1
    return value


def _xlsx_sheets(body: bytes) -> list[tuple[str, list[list[Any]]]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body), "r")
    except zipfile.BadZipFile as exc:
        raise CocrCorrosionScientificIntakeError("selected source is not a valid XLSX") from exc
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise CocrCorrosionScientificIntakeError("XLSX repeats ZIP member names")
        for required in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
            if required not in names:
                raise CocrCorrosionScientificIntakeError(f"XLSX part missing: {required}")

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{_NS}}}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{{{_NS}}}t")))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
        sheet_root = workbook.find(f"{{{_NS}}}sheets")
        if sheet_root is None:
            raise CocrCorrosionScientificIntakeError("XLSX has no sheets")

        result: list[tuple[str, list[list[Any]]]] = []
        for sheet in sheet_root:
            sheet_name = sheet.attrib.get("name", "")
            rel_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
            target = rel_map.get(rel_id or "")
            if not sheet_name or not target:
                raise CocrCorrosionScientificIntakeError("worksheet identity is incomplete")
            member = target.lstrip("/") if target.startswith("/") else "xl/" + target.lstrip("/")
            if member not in names:
                raise CocrCorrosionScientificIntakeError(f"worksheet XML missing: {sheet_name}")
            root = ET.fromstring(archive.read(member))
            sparse: dict[int, dict[int, Any]] = {}
            max_col = 0
            for row in root.findall(f".//{{{_NS}}}sheetData/{{{_NS}}}row"):
                row_number = int(row.attrib["r"])
                if row_number in sparse:
                    raise CocrCorrosionScientificIntakeError("worksheet repeats row number")
                cells: dict[int, Any] = {}
                for cell in row.findall(f"{{{_NS}}}c"):
                    ref = cell.attrib.get("r", "")
                    match = _CELL_RE.fullmatch(ref)
                    if not match or int(match.group(2)) != row_number:
                        raise CocrCorrosionScientificIntakeError(f"invalid cell reference {ref!r}")
                    col = _col_index(match.group(1))
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
                    max_col = max(max_col, col)
                sparse[row_number] = cells
            rows: list[list[Any]] = []
            for row_number in sorted(sparse):
                rows.append([sparse[row_number].get(col) for col in range(1, max_col + 1)])
            result.append((sheet_name, rows))
        return result


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CocrCorrosionScientificIntakeError(f"{field} must be numeric source value")
    number = float(value)
    if not math.isfinite(number):
        raise CocrCorrosionScientificIntakeError(f"{field} must be finite")
    return number


def _time_from_title(value: object, field: str) -> int:
    if not isinstance(value, str):
        raise CocrCorrosionScientificIntakeError(f"{field} title is not text")
    match = _TIME_RE.search(value)
    if match is None:
        raise CocrCorrosionScientificIntakeError(f"{field} title lacks immersion time: {value!r}")
    return int(match.group("hours"))


def _audit_eis(body: bytes, condition: str) -> dict[str, Any]:
    sheets = [(name, rows) for name, rows in _xlsx_sheets(body) if rows]
    acquisitions: list[dict[str, Any]] = []
    reference_frequency: list[float] | None = None
    source_date_representation_types: set[str] = set()
    for sheet_name, rows in sheets:
        if len(rows) < 58 or len(rows[0]) < 3 or len(rows[1]) < 7:
            continue
        if str(rows[1][0]).strip() != "freq / Hz":
            continue
        title = rows[0][1]
        time_h = _time_from_title(title, f"EIS {condition}")
        if condition.upper() not in str(title).upper():
            raise CocrCorrosionScientificIntakeError("EIS condition label changed")
        expected_headers = ["freq / Hz", "neg. Phase / °", "Idc / uA", "Z / Ohm", "Z' / Ohm", "-Z'' / Ohm", "Cs / F"]
        if [str(v).strip() for v in rows[1][:7]] != expected_headers:
            raise CocrCorrosionScientificIntakeError("EIS headers changed")
        points = rows[2:58]
        if len(points) != 56:
            raise CocrCorrosionScientificIntakeError("EIS point count changed")
        frequencies = [_number(row[0], "EIS frequency") for row in points]
        for row in points:
            for col, label in enumerate(expected_headers[1:], start=1):
                _number(row[col], f"EIS {label}")
        if reference_frequency is None:
            reference_frequency = frequencies
        elif frequencies != reference_frequency:
            raise CocrCorrosionScientificIntakeError("EIS frequency grids differ across time points")
        source_date = rows[0][2]
        source_date_representation_types.add(type(source_date).__name__)
        acquisitions.append(
            {
                "sheet": sheet_name,
                "title_source": title,
                "immersion_time_h": time_h,
                "source_date_value": source_date,
                "point_count": 56,
                "frequency_hz_max": frequencies[0],
                "frequency_hz_min": frequencies[-1],
                "low_frequency_z_prime_ohm": _number(points[-1][4], "low-frequency Z prime"),
                "low_frequency_minus_z_double_prime_ohm": _number(points[-1][5], "low-frequency -Z double prime"),
            }
        )
    if not acquisitions:
        raise CocrCorrosionScientificIntakeError(f"no EIS acquisitions found for {condition}")
    times = [item["immersion_time_h"] for item in acquisitions]
    if len(times) != len(set(times)):
        raise CocrCorrosionScientificIntakeError("EIS repeats an immersion-time label")
    return {
        "condition": condition,
        "acquisition_count": len(acquisitions),
        "immersion_times_h": times,
        "frequency_point_count_per_acquisition": 56,
        "frequency_grid_identical_across_time": True,
        "frequency_hz_max": reference_frequency[0],
        "frequency_hz_min": reference_frequency[-1],
        "source_date_representation_types": sorted(source_date_representation_types),
        "acquisitions": acquisitions,
        "independent_specimen_replicates_established": False,
        "equivalent_circuit_fit_performed": False,
    }


def _audit_lpr_raw(body: bytes, condition: str) -> dict[str, Any]:
    sheets = _xlsx_sheets(body)
    if not sheets or not sheets[0][1]:
        raise CocrCorrosionScientificIntakeError("LPR workbook is empty")
    rows = sheets[0][1]
    if len(rows) != 23:
        raise CocrCorrosionScientificIntakeError("LPR row count changed")
    width = 20 if condition == "control" else 22
    if len(rows[0]) < width or len(rows[1]) < width:
        raise CocrCorrosionScientificIntakeError("LPR column count changed")
    times: list[int] = []
    traces: list[dict[str, Any]] = []
    for col in range(0, width, 2):
        title = rows[0][col]
        time_h = _time_from_title(title, f"LPR {condition}")
        if condition.upper() not in str(title).upper():
            raise CocrCorrosionScientificIntakeError("LPR condition label changed")
        if str(rows[1][col]).strip() != "V" or str(rows[1][col + 1]).strip() != "µA":
            raise CocrCorrosionScientificIntakeError("raw LPR headers changed")
        values = rows[2:23]
        if len(values) != 21:
            raise CocrCorrosionScientificIntakeError("LPR point count changed")
        potentials = [_number(row[col], "LPR potential") for row in values]
        currents = [_number(row[col + 1], "LPR current") for row in values]
        traces.append(
            {
                "title_source": title,
                "immersion_time_h": time_h,
                "point_count": 21,
                "potential_v_min": min(potentials),
                "potential_v_max": max(potentials),
                "current_microamp_min": min(currents),
                "current_microamp_max": max(currents),
            }
        )
        times.append(time_h)
    return {
        "condition": condition,
        "trace_count": len(traces),
        "immersion_times_h": times,
        "point_count_per_trace": 21,
        "potential_source_unit_label": "V",
        "current_source_unit_label": "µA",
        "independent_specimen_replicates_established": False,
        "traces": traces,
    }


def _audit_converted_control(raw_control_body: bytes, converted_body: bytes) -> dict[str, Any]:
    raw_rows = _xlsx_sheets(raw_control_body)[0][1]
    sheets = {name: rows for name, rows in _xlsx_sheets(converted_body)}
    for required in ("Raw_Data", "Converted_Normalized", "Rp_Summary"):
        if required not in sheets:
            raise CocrCorrosionScientificIntakeError(f"converted LPR sheet missing: {required}")
    copied = sheets["Raw_Data"]
    converted = sheets["Converted_Normalized"]
    if len(raw_rows) != 23 or len(copied) != 23 or len(converted) != 23:
        raise CocrCorrosionScientificIntakeError("converted-control LPR row count changed")

    potential_shifts: list[float] = []
    current_factors: list[float] = []
    copied_numeric_pairs_equal = True
    for source_row, copied_row, converted_row in zip(raw_rows[2:], copied[2:], converted[2:]):
        for col in range(0, 20, 2):
            source_e = _number(source_row[col], "raw control potential")
            source_i = _number(source_row[col + 1], "raw control current")
            copied_e = _number(copied_row[col], "copied control potential")
            copied_i = _number(copied_row[col + 1], "copied control current")
            converted_e = _number(converted_row[col], "converted potential")
            converted_i = _number(converted_row[col + 1], "converted current density")
            if abs(source_e - copied_e) > 1e-15 or abs(source_i - copied_i) > 1e-15:
                copied_numeric_pairs_equal = False
            potential_shifts.append(converted_e - source_e)
            if source_i == 0:
                raise CocrCorrosionScientificIntakeError("cannot audit converted current factor from zero source current")
            current_factors.append(converted_i / source_i)

    shift = potential_shifts[0]
    factor = current_factors[0]
    if not all(abs(value - shift) <= 1e-12 for value in potential_shifts):
        raise CocrCorrosionScientificIntakeError("converted potential shift is not constant")
    if not all(abs(value - factor) <= 1e-12 for value in current_factors):
        raise CocrCorrosionScientificIntakeError("converted current factor is not constant")
    if not copied_numeric_pairs_equal:
        raise CocrCorrosionScientificIntakeError("Raw_Data does not reproduce original control numeric pairs")

    summary = sheets["Rp_Summary"]
    if len(summary) != 11 or [str(v).strip() for v in summary[0][:5]] != [
        "Immersion time (h)", "Slope (V per uA/cm2)", "Rp (ohm.cm2)", "R2", "n points"
    ]:
        raise CocrCorrosionScientificIntakeError("Rp summary schema changed")
    rows = []
    for row in summary[1:]:
        time_h = int(_number(row[0], "Rp time"))
        slope = _number(row[1], "Rp slope")
        rp = _number(row[2], "Rp")
        r2 = _number(row[3], "Rp R2")
        n_points = int(_number(row[4], "Rp n points"))
        if n_points != 21 or abs(rp - slope * 1_000_000.0) > max(1e-6, abs(rp) * 1e-12):
            raise CocrCorrosionScientificIntakeError("Rp summary arithmetic contract changed")
        rows.append({"immersion_time_h": time_h, "slope_v_per_uA_cm2": slope, "rp_ohm_cm2": rp, "r2": r2, "n_points": n_points})
    return {
        "raw_data_numeric_pairs_exactly_reproduce_original_control": True,
        "converted_potential_constant_shift_v": float(format(shift, ".15g")),
        "converted_current_constant_factor": float(format(factor, ".15g")),
        "converted_headers_claim_reference": "Ag/AgCl",
        "converted_headers_claim_current_density_unit": "uA/cm2",
        "physical_basis_of_potential_shift_established_by_acquired_source_metadata": False,
        "physical_basis_of_current_normalization_established_by_acquired_source_metadata": False,
        "wear_conversion_contract_present": False,
        "rp_summary_rows": rows,
        "rp_summary_is_derived_representation_not_independent_measurement": True,
    }


def _audit_pdp(body: bytes) -> dict[str, Any]:
    sheets = _xlsx_sheets(body)
    if not sheets or not sheets[0][1] or len(sheets[0][1]) < 3:
        raise CocrCorrosionScientificIntakeError("PDP workbook is empty")
    rows = sheets[0][1]
    if [str(v).strip() if v is not None else None for v in rows[0][:4]] != ["CONTROL PDP", None, "WEAR PDP", None]:
        raise CocrCorrosionScientificIntakeError("PDP condition headers changed")
    if [str(v).strip() for v in rows[1][:4]] != ["V", "Log10(µA)", "V", "Log10(µA)"]:
        raise CocrCorrosionScientificIntakeError("PDP headers changed")
    counts = {"control": 0, "wear": 0}
    for row in rows[2:]:
        if len(row) >= 2 and row[0] is not None and row[1] is not None:
            _number(row[0], "PDP control potential")
            _number(row[1], "PDP control log current")
            counts["control"] += 1
        if len(row) >= 4 and row[2] is not None and row[3] is not None:
            _number(row[2], "PDP wear potential")
            _number(row[3], "PDP wear log current")
            counts["wear"] += 1
    if min(counts.values()) == 0:
        raise CocrCorrosionScientificIntakeError("PDP condition contains no numeric pairs")
    return {
        "numeric_pair_counts": counts,
        "source_current_representation": "Log10(µA)",
        "reference_electrode_established_by_acquired_workbook": False,
        "independent_specimen_replicates_established": False,
        "tafel_or_corrosion_parameter_fit_performed": False,
    }


def audit_cocr_corrosion_files(files: dict[str, bytes]) -> dict[str, Any]:
    required = {
        "EIS CONTROL RAW DATA.xlsx",
        "EIS WEAR RAW DATA.xlsx",
        "lpr control cocr.xlsx",
        "LPR WEAR.xlsx",
        "LPR_Control_Converted.xlsx",
        "PDP CONTROL VS WEAR.xlsx",
    }
    if set(files) != required:
        raise CocrCorrosionScientificIntakeError("exact six-file electrochemistry set is required")
    bindings = {name: {"sha256": _sha(body), "size_bytes": len(body)} for name, body in sorted(files.items())}
    eis_control = _audit_eis(files["EIS CONTROL RAW DATA.xlsx"], "control")
    eis_wear = _audit_eis(files["EIS WEAR RAW DATA.xlsx"], "wear")
    lpr_control = _audit_lpr_raw(files["lpr control cocr.xlsx"], "control")
    lpr_wear = _audit_lpr_raw(files["LPR WEAR.xlsx"], "wear")
    converted = _audit_converted_control(files["lpr control cocr.xlsx"], files["LPR_Control_Converted.xlsx"])
    pdp = _audit_pdp(files["PDP CONTROL VS WEAR.xlsx"])
    common_eis_times = sorted(set(eis_control["immersion_times_h"]) & set(eis_wear["immersion_times_h"]))
    common_lpr_times = sorted(set(lpr_control["immersion_times_h"]) & set(lpr_wear["immersion_times_h"]))

    initial = {
        "schema_version": SCHEMA_VERSION,
        "source_bindings": bindings,
        "eis": {"control": eis_control, "wear": eis_wear, "common_immersion_times_h": common_eis_times},
        "lpr": {"control": lpr_control, "wear": lpr_wear, "common_immersion_times_h": common_lpr_times, "converted_control": converted},
        "pdp": pdp,
        "experimental_unit_boundary": {
            "dataset_describes_single_retrieved_prosthesis": True,
            "control_and_wear_time_series_treated_as_independent_specimen_replicates": False,
            "time_rows_or_frequency_points_treated_as_independent_specimens": False,
            "replicate_independence_established": False,
        },
        "detected_weaknesses": [
            {"code": "control_and_wear_independent_specimen_lineage_unresolved", "severity": "blocks_inferential_treatment_comparison"},
            {"code": "lpr_control_conversion_basis_not_source_bound", "severity": "blocks_applying_conversion_to_wear"},
            {"code": "converted_control_is_derived_representation", "severity": "prevents_double_counting"},
            {"code": "eis_equivalent_circuit_not_validated", "severity": "blocks_model_parameter_claims"},
            {"code": "pdp_reference_and_fit_contract_unresolved", "severity": "blocks_corrosion_parameter inference"},
            {"code": "control_and_wear_early_time_grids_differ", "severity": "limits_direct_time-matched comparison"},
        ],
        "descriptive_result": {
            "eis_control_acquisition_count": eis_control["acquisition_count"],
            "eis_wear_acquisition_count": eis_wear["acquisition_count"],
            "common_eis_time_count": len(common_eis_times),
            "lpr_control_trace_count": lpr_control["trace_count"],
            "lpr_wear_trace_count": lpr_wear["trace_count"],
            "common_lpr_time_count": len(common_lpr_times),
            "wear_changes_corrosion_behavior_causally_established": False,
        },
        "bounded_next_action": {
            "action_type": "conversion_and_repeat_lineage_audit",
            "objective": "Reconcile the converted-control LPR representation and repeated-measurement identities before any control-vs-wear corrosion parameter comparison.",
        },
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    initial["report_sha256"] = _canonical_sha(initial)

    reanalysis = {
        "schema_version": SCHEMA_VERSION,
        "initial_report_sha256": initial["report_sha256"],
        "selected_next_action_type": "conversion_and_repeat_lineage_audit",
        "exact_conversion_reaudit": {
            "potential_shift_v": converted["converted_potential_constant_shift_v"],
            "current_factor": converted["converted_current_constant_factor"],
            "raw_control_copy_exact": converted["raw_data_numeric_pairs_exactly_reproduce_original_control"],
            "converted_representation_is_independent_measurement": False,
            "physical_conversion_basis_established": False,
            "wear_conversion_contract_present": False,
        },
        "repeat_lineage_reaudit": {
            "eis_common_times_h": common_eis_times,
            "lpr_common_times_h": common_lpr_times,
            "independent_control_specimen_count_established": False,
            "independent_wear_specimen_count_established": False,
            "time_series_points_counted_as_independent_n": False,
        },
        "bounded_stop": True,
        "bounded_stop_reasons": [
            "the acquired source does not establish independent control/wear specimen replication",
            "the converted-control workbook exposes an exact numerical transform but the acquired metadata does not establish its physical basis or authorize applying it to wear data",
            "equivalent-circuit, Tafel, reference-electrode, and microscopy linkage contracts are not sufficiently source-bound for stronger inference",
        ],
        "future_followups": [
            {"action": "obtain_explicit_electrode_area_reference_and_conversion_method", "executed_in_this_episode": False},
            {"action": "obtain_specimen_repeat_and_surface_lineage", "executed_in_this_episode": False},
            {"action": "only_then_compare_control_and_wear_corrosion_parameters", "executed_in_this_episode": False},
        ],
        "model_training_authorized": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    reanalysis["reanalysis_sha256"] = _canonical_sha(reanalysis)
    sequence = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": "zenodo-cocr-knee-corrosion-generalization",
        "initial_report_sha256": initial["report_sha256"],
        "next_action_type": initial["bounded_next_action"]["action_type"],
        "persisted_reanalysis_sha256": reanalysis["reanalysis_sha256"],
        "bounded_stop": True,
        "future_followups_kept_unexecuted": all(item["executed_in_this_episode"] is False for item in reanalysis["future_followups"]),
        "full_bounded_research_cycle_completed": True,
        "scientific_status_changed": False,
    }
    sequence["sequence_sha256"] = _canonical_sha(sequence)
    return {"initial_intake": initial, "reanalysis": reanalysis, "episode_sequence": sequence}


__all__ = ["CocrCorrosionScientificIntakeError", "audit_cocr_corrosion_files"]
