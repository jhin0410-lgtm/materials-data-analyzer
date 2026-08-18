"""Exact SSRM temperature/pressure logger parsing with source-unavailable tokens.

The Ti logger contains two rows where both pressure and temperature are encoded as
``**``.  They are preserved as source-unavailable observations; no interpolation,
forward fill, numeric coercion, or row deletion is allowed.  Timestamp coverage is
computed over all rows while numeric ranges use only explicitly numeric source rows.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime
from typing import Any

from .ssrm_titanium_scientific_intake import SsrmTitaniumScientificIntakeError

_SOURCE_UNAVAILABLE = "**"


def _number(value: str, *, field: str, material: str, row_number: int) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise SsrmTitaniumScientificIntakeError(
            f"unexpected nonnumeric {field} token for {material} at CSV row {row_number}: {value!r}"
        ) from exc


def audit_ssrm_logger_with_source_unavailable_tokens(
    body: bytes, material: str
) -> dict[str, Any]:
    """Audit one exact logger while preserving paired ``**`` rows as unavailable."""

    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SsrmTitaniumScientificIntakeError("logger CSV must be UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ["#", "Time", "P (Bar)", "T (°C)"]:
        raise SsrmTitaniumScientificIntakeError(f"logger CSV headers changed for {material}")

    timestamps: list[datetime] = []
    pressure: list[float] = []
    temperature: list[float] = []
    unavailable_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            timestamp = datetime.strptime(row["Time"].strip("'"), "%m-%d-%Y %H:%M:%S.%f")
        except (AttributeError, ValueError) as exc:
            raise SsrmTitaniumScientificIntakeError(
                f"logger timestamp invalid for {material} at CSV row {row_number}"
            ) from exc
        timestamps.append(timestamp)

        p_token = row["P (Bar)"].strip()
        t_token = row["T (°C)"].strip()
        p_unavailable = p_token == _SOURCE_UNAVAILABLE
        t_unavailable = t_token == _SOURCE_UNAVAILABLE
        if p_unavailable != t_unavailable:
            raise SsrmTitaniumScientificIntakeError(
                f"logger has one-sided unavailable P/T token for {material} at CSV row {row_number}"
            )
        if p_unavailable:
            unavailable_rows.append(
                {
                    "csv_row": row_number,
                    "timestamp_source": timestamp.isoformat(),
                    "pressure_source_token": p_token,
                    "temperature_source_token": t_token,
                }
            )
            continue
        pressure.append(_number(p_token, field="pressure", material=material, row_number=row_number))
        temperature.append(
            _number(t_token, field="temperature", material=material, row_number=row_number)
        )

    if len(timestamps) < 2 or not pressure or not temperature:
        raise SsrmTitaniumScientificIntakeError("logger trace is too short")
    steps = [
        int((right - left).total_seconds())
        for left, right in zip(timestamps, timestamps[1:])
    ]
    span_h = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
    return {
        "material": material,
        "row_count": len(timestamps),
        "numeric_pair_row_count": len(pressure),
        "source_unavailable_pair_row_count": len(unavailable_rows),
        "source_unavailable_rows": unavailable_rows,
        "source_unavailable_token": _SOURCE_UNAVAILABLE,
        "source_unavailable_rows_interpolated_or_imputed": False,
        "start_timestamp_source": timestamps[0].isoformat(),
        "end_timestamp_source": timestamps[-1].isoformat(),
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
