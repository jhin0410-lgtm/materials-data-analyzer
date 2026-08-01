"""Provenance and identity admission gate for optional battery raw signals."""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


REQUIRED_PROVENANCE_FIELDS = {
    "source_name",
    "source_identifier",
    "retrieved_at",
    "source_sha256",
    "license_or_terms",
    "battery_id_mapping_method",
    "cycle_mapping_method",
    "unit_declarations",
}
EXPECTED_UNITS = {
    "elapsed_time_s": {"s", "sec", "second", "seconds"},
    "voltage_v": {"v", "volt", "volts"},
    "current_a": {"a", "amp", "amps", "ampere", "amperes"},
    "temperature_c": {"c", "degc", "degree_celsius", "degrees_celsius", "°c"},
    "capacity_ah": {"ah", "a*h", "ampere_hour", "ampere_hours"},
    "global_time_s": {"s", "sec", "second", "seconds"},
}


def _normalized_unit(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")


def audit_raw_signal_admission(
    *,
    cycle_summary: pd.DataFrame,
    raw_signal: pd.DataFrame,
    provenance: Mapping[str, Any] | None,
    raw_sha256: str,
    group_column: str,
    cycle_column: str,
) -> dict[str, Any]:
    """Assess whether raw signals may enter predictive feature comparison.

    Signal extraction remains available for software diagnostics, but predictive
    use is admitted only when source identity, checksum, units, and battery-cycle
    mapping are explicit and coverage is sufficient for grouped validation.
    """
    summary_pairs = {
        (str(row[group_column]), float(row[cycle_column]))
        for _, row in cycle_summary[[group_column, cycle_column]].iterrows()
    }
    raw_pairs = {
        (str(row["battery_id"]), float(row["cycle_index"]))
        for _, row in raw_signal[["battery_id", "cycle_index"]].drop_duplicates().iterrows()
    }
    unknown_pairs = sorted(raw_pairs - summary_pairs)
    covered_pairs = raw_pairs & summary_pairs
    summary_batteries = {item[0] for item in summary_pairs}
    covered_batteries = {item[0] for item in covered_pairs}

    missing_fields: list[str] = []
    checksum_matches = False
    unit_checks: dict[str, bool] = {}
    provenance_present = provenance is not None
    if provenance is None:
        missing_fields = sorted(REQUIRED_PROVENANCE_FIELDS)
    else:
        missing_fields = sorted(
            field
            for field in REQUIRED_PROVENANCE_FIELDS
            if field not in provenance
            or provenance[field] is None
            or provenance[field] == ""
        )
        checksum_matches = str(provenance.get("source_sha256", "")).lower() == raw_sha256.lower()
        declared_units = provenance.get("unit_declarations", {})
        if not isinstance(declared_units, Mapping):
            declared_units = {}
        for column, accepted in EXPECTED_UNITS.items():
            if column not in raw_signal.columns:
                continue
            unit_checks[column] = _normalized_unit(declared_units.get(column, "")) in accepted

    identity_mapping_complete = len(unknown_pairs) == 0
    unit_declarations_valid = bool(unit_checks) and all(unit_checks.values())
    covered_battery_fraction = (
        len(covered_batteries) / len(summary_batteries) if summary_batteries else 0.0
    )
    covered_cycle_fraction = len(covered_pairs) / len(summary_pairs) if summary_pairs else 0.0
    grouped_validation_support = len(covered_batteries) >= 5
    coverage_support = covered_battery_fraction >= 0.5 and covered_cycle_fraction >= 0.5

    checks = {
        "provenance_sidecar_present": provenance_present,
        "required_provenance_fields_complete": not missing_fields,
        "source_checksum_matches": checksum_matches,
        "unit_declarations_valid": unit_declarations_valid,
        "battery_cycle_identity_mapping_complete": identity_mapping_complete,
        "at_least_five_covered_batteries": grouped_validation_support,
        "minimum_half_cohort_and_cycle_coverage": coverage_support,
    }
    admitted = all(checks.values())
    if admitted:
        status = "admitted_for_predictive_comparison"
    elif not provenance_present:
        status = "not_admitted_missing_provenance"
    elif not checksum_matches:
        status = "not_admitted_checksum_mismatch"
    elif not identity_mapping_complete:
        status = "not_admitted_identity_mismatch"
    elif not unit_declarations_valid:
        status = "not_admitted_unit_contract"
    else:
        status = "not_admitted_insufficient_coverage"

    return {
        "schema_version": "1.0",
        "status": status,
        "admitted_for_predictive_comparison": admitted,
        "checks": checks,
        "missing_provenance_fields": missing_fields,
        "unit_checks": unit_checks,
        "summary_battery_count": len(summary_batteries),
        "covered_battery_count": len(covered_batteries),
        "covered_battery_fraction": covered_battery_fraction,
        "summary_cycle_pair_count": len(summary_pairs),
        "covered_cycle_pair_count": len(covered_pairs),
        "covered_cycle_fraction": covered_cycle_fraction,
        "unknown_raw_pair_count": len(unknown_pairs),
        "unknown_raw_pair_examples": [
            {"battery_id": battery_id, "cycle_index": cycle_index}
            for battery_id, cycle_index in unknown_pairs[:20]
        ],
        "predictive_use_policy": (
            "Raw-signal features enter model comparison only when every admission "
            "check passes. Extraction alone does not establish scientific value."
        ),
    }
