"""Leakage-resistant AMB2018-02 calibration/holdout benchmark contract.

Phase 1 deliberately separates prediction generation from holdout evaluation:

* Case B response rows are calibration evidence and may be exposed to the baseline builder.
* Cases A/C process conditions are visible because prediction requires their inputs.
* Cases A/C response values are NOT embedded in the frozen prediction contract.
* Holdout response values are opened only by the evaluator after a prediction artifact has
  already been frozen against the contract SHA.

The included Case-B persistence baseline is an evaluator smoke test, not an LPBF physics model.
It cannot establish empirical model validity, causality, engineering readiness, or process
optimization.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .evidence_packet import canonical_sha256
from .in625_geometry_condition_mapping_assessment import (
    TARGET_PROCESS_SHA256,
    TARGET_RESPONSE_SHA256,
)

BENCHMARK_SCHEMA_VERSION = "1.0"
BENCHMARK_POLICY_VERSION = "1.0"
CALIBRATION_CASES = ("B",)
HOLDOUT_CASES = ("A", "C")
_PROCESS_REL = Path(
    "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
)
_RESPONSE_REL = Path(
    "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
)
_EXPECTED_CONDITIONS = {
    "A": {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 400.0, "trace_count": 3},
    "B": {"actual_laser_power_w": 179.2, "scan_speed_mm_s": 800.0, "trace_count": 3},
    "C": {"actual_laser_power_w": 179.2, "scan_speed_mm_s": 1200.0, "trace_count": 4},
}


class In625ModelHoldoutBenchmarkError(ValueError):
    """Raised when calibration/holdout separation or source identity drifts."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625ModelHoldoutBenchmarkError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return str(value)


def _read_source(root: Path, relative: Path, expected_sha: str) -> bytes:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise In625ModelHoldoutBenchmarkError(
            f"benchmark source escaped repository root: {relative}"
        ) from exc
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    _require(
        observed == expected_sha,
        f"benchmark source SHA drifted for {relative}: {observed}",
    )
    return raw


def _csv_rows(raw: bytes, label: str) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise In625ModelHoldoutBenchmarkError(f"{label} must be UTF-8 CSV") from exc
    rows = list(csv.DictReader(io.StringIO(text)))
    _require(bool(rows), f"{label} contains no rows")
    return rows


def _number(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise In625ModelHoldoutBenchmarkError(f"{field} must be numeric") from exc
    _require(math.isfinite(number), f"{field} must be finite")
    return number


def _sample_sd(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    center = sum(values) / len(values)
    return math.sqrt(
        sum((value - center) ** 2 for value in values) / (len(values) - 1)
    )


def _mean(values: Sequence[float]) -> float:
    _require(bool(values), "mean requires at least one value")
    return sum(values) / len(values)


def _validated_sources(
    repository_root: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    process_raw = _read_source(root, _PROCESS_REL, TARGET_PROCESS_SHA256)
    response_raw = _read_source(root, _RESPONSE_REL, TARGET_RESPONSE_SHA256)
    process_rows_raw = _csv_rows(process_raw, "process source")
    response_rows_raw = _csv_rows(response_raw, "response source")

    process_rows: list[dict[str, Any]] = []
    process_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(process_rows_raw):
        sample_id = str(row.get("sample_id", "")).strip()
        case_id = str(row.get("case_id", "")).strip()
        _require(sample_id and case_id in _EXPECTED_CONDITIONS, f"bad process row {index}")
        item = {
            "sample_id": sample_id,
            "case_id": case_id,
            "trace_number": int(row["trace_number"]),
            "actual_laser_power_w": _number(
                row["actual_laser_power_w"], f"process[{index}].actual_laser_power_w"
            ),
            "scan_speed_mm_s": _number(
                row["scan_speed_mm_s"], f"process[{index}].scan_speed_mm_s"
            ),
            "system": str(row["system"]).strip(),
            "material": str(row["material"]).strip(),
        }
        _require(sample_id not in process_by_id, "duplicate process sample_id")
        process_by_id[sample_id] = item
        process_rows.append(item)

    case_process: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in process_rows:
        case_process[row["case_id"]].append(row)
    _require(set(case_process) == set(_EXPECTED_CONDITIONS), "case support drifted")
    for case_id, expected in _EXPECTED_CONDITIONS.items():
        rows = case_process[case_id]
        _require(
            len(rows) == expected["trace_count"],
            f"{case_id} trace count drifted",
        )
        for row in rows:
            _require(
                row["system"] == "AMMT" and row["material"] == "IN625",
                f"{case_id} material/system identity drifted",
            )
            _require(
                row["actual_laser_power_w"] == expected["actual_laser_power_w"]
                and row["scan_speed_mm_s"] == expected["scan_speed_mm_s"],
                f"{case_id} corrected process condition drifted",
            )

    response_rows: list[dict[str, Any]] = []
    seen_response_ids: set[str] = set()
    for index, row in enumerate(response_rows_raw):
        sample_id = str(row.get("sample_id", "")).strip()
        _require(sample_id in process_by_id, f"response row {index} has unknown sample_id")
        _require(sample_id not in seen_response_ids, "duplicate response sample_id")
        seen_response_ids.add(sample_id)
        process = process_by_id[sample_id]
        _require(
            str(row.get("case_id", "")).strip() == process["case_id"]
            and int(row["trace_number"]) == process["trace_number"],
            f"response/process identity mismatch at {sample_id}",
        )
        response_rows.append(
            {
                "sample_id": sample_id,
                "case_id": process["case_id"],
                "trace_number": process["trace_number"],
                "melt_pool_width_mean_um": _number(
                    row["melt_pool_width_mean_um"],
                    f"response[{index}].melt_pool_width_mean_um",
                ),
                "melt_pool_width_std_dev_um": _number(
                    row["melt_pool_width_std_dev_um"],
                    f"response[{index}].melt_pool_width_std_dev_um",
                ),
                "melt_pool_depth_mean_um": _number(
                    row["melt_pool_depth_mean_um"],
                    f"response[{index}].melt_pool_depth_mean_um",
                ),
                "melt_pool_depth_std_dev_um": _number(
                    row["melt_pool_depth_std_dev_um"],
                    f"response[{index}].melt_pool_depth_std_dev_um",
                ),
            }
        )
    _require(
        seen_response_ids == set(process_by_id),
        "process/response source tables do not form an exact one-to-one trace join",
    )
    return process_rows, response_rows


def _case_process_summary(process_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in process_rows:
        grouped[str(row["case_id"])].append(row)
    result: list[dict[str, Any]] = []
    for case_id in ("A", "B", "C"):
        rows = grouped[case_id]
        result.append(
            {
                "case_id": case_id,
                "actual_laser_power_w": float(rows[0]["actual_laser_power_w"]),
                "scan_speed_mm_s": float(rows[0]["scan_speed_mm_s"]),
                "trace_count": len(rows),
                "sample_ids": sorted(str(row["sample_id"]) for row in rows),
            }
        )
    return result


def _case_response_summary(
    rows: Sequence[Mapping[str, Any]],
    case_id: str,
) -> dict[str, Any]:
    case_rows = [row for row in rows if row["case_id"] == case_id]
    _require(bool(case_rows), f"response rows missing for case {case_id}")
    widths = [float(row["melt_pool_width_mean_um"]) for row in case_rows]
    depths = [float(row["melt_pool_depth_mean_um"]) for row in case_rows]
    return {
        "case_id": case_id,
        "trace_count": len(case_rows),
        "sample_ids": sorted(str(row["sample_id"]) for row in case_rows),
        "width": {
            "trace_mean_average_um": _mean(widths),
            "trace_mean_sample_sd_um": _sample_sd(widths),
            "trace_mean_range_um": [min(widths), max(widths)],
        },
        "depth": {
            "trace_mean_average_um": _mean(depths),
            "trace_mean_sample_sd_um": _sample_sd(depths),
            "trace_mean_range_um": [min(depths), max(depths)],
        },
    }


def build_in625_ambench_holdout_contract(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Freeze process inputs plus Case-B calibration responses; hide A/C responses."""

    process_rows, response_rows = _validated_sources(repository_root)
    calibration_summary = _case_response_summary(response_rows, "B")
    contract: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "policy_version": BENCHMARK_POLICY_VERSION,
        "benchmark_id": "nist-amb2018-02-ammt-in625-case-b-calibration-ac-holdout-v1",
        "source_bindings": {
            "process_table_sha256": TARGET_PROCESS_SHA256,
            "response_table_sha256": TARGET_RESPONSE_SHA256,
        },
        "partition": {
            "calibration_case_ids": list(CALIBRATION_CASES),
            "holdout_case_ids": list(HOLDOUT_CASES),
            "partition_frozen_before_prediction": True,
            "holdout_response_values_exposed_in_contract": False,
        },
        "process_conditions": _case_process_summary(process_rows),
        "calibration_response": calibration_summary,
        "holdout_response_binding": {
            "response_table_sha256": TARGET_RESPONSE_SHA256,
            "case_ids": list(HOLDOUT_CASES),
            "values_embedded": False,
            "evaluation_only": True,
        },
        "required_prediction_responses": [
            "melt_pool_width_mean_um",
            "melt_pool_depth_mean_um",
        ],
        "scientific_boundary": {
            "calibration_fit_is_validation": False,
            "simulation_is_empirical_measurement": False,
            "agreement_establishes_causality": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    contract["contract_sha256"] = canonical_sha256(contract)
    return contract


def _authenticate_contract(
    contract: Mapping[str, Any],
    *,
    trusted_contract_sha256: str,
) -> dict[str, Any]:
    trusted = _sha(trusted_contract_sha256, "trusted_contract_sha256")
    snapshot = copy.deepcopy(dict(contract))
    _require(
        canonical_sha256(snapshot) == trusted,
        "holdout contract does not match external trust-root SHA-256",
    )
    embedded = _sha(snapshot.pop("contract_sha256", None), "contract.contract_sha256")
    _require(
        canonical_sha256(snapshot) == embedded,
        "holdout contract embedded self-hash mismatch",
    )
    snapshot["contract_sha256"] = embedded
    partition = snapshot.get("partition")
    _require(isinstance(partition, Mapping), "holdout contract partition missing")
    _require(
        partition.get("calibration_case_ids") == ["B"]
        and partition.get("holdout_case_ids") == ["A", "C"]
        and partition.get("partition_frozen_before_prediction") is True
        and partition.get("holdout_response_values_exposed_in_contract") is False,
        "holdout contract calibration/validation partition widened",
    )
    return snapshot


def build_case_b_persistence_baseline(
    contract: Mapping[str, Any],
    *,
    trusted_contract_sha256: str,
) -> dict[str, Any]:
    """Build a non-physics smoke baseline using Case-B response means only."""

    snapshot = _authenticate_contract(
        contract,
        trusted_contract_sha256=trusted_contract_sha256,
    )
    calibration = snapshot.get("calibration_response")
    _require(isinstance(calibration, Mapping), "calibration response missing")
    width = calibration.get("width")
    depth = calibration.get("depth")
    _require(
        isinstance(width, Mapping) and isinstance(depth, Mapping),
        "calibration width/depth summary missing",
    )
    width_value = _number(width.get("trace_mean_average_um"), "calibration width")
    depth_value = _number(depth.get("trace_mean_average_um"), "calibration depth")

    prediction: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "prediction_type": "diagnostic_baseline_prediction",
        "benchmark_contract_sha256": snapshot["contract_sha256"],
        "model": {
            "model_id": "case-b-persistence-baseline",
            "model_version": "1.0",
            "model_class": "diagnostic_persistence_baseline_not_physics",
            "computational_evidence_class": "diagnostic_computational",
        },
        "calibration_provenance": {
            "response_case_ids_used_for_fit": ["B"],
            "response_case_ids_used_for_model_selection": [],
            "response_case_ids_used_for_hyperparameter_tuning": [],
            "holdout_response_values_consumed_before_prediction_freeze": False,
        },
        "predictions": [
            {
                "case_id": case_id,
                "melt_pool_width_mean_um": width_value,
                "melt_pool_depth_mean_um": depth_value,
            }
            for case_id in HOLDOUT_CASES
        ],
        "scientific_boundary": {
            "physics_model_claimed": False,
            "empirical_measurement_created": False,
            "predictive_validation_established": False,
            "scientific_status_promoted": False,
        },
    }
    prediction["prediction_sha256"] = canonical_sha256(prediction)
    return prediction


def _authenticate_prediction(
    prediction: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = copy.deepcopy(dict(prediction))
    embedded = _sha(
        snapshot.pop("prediction_sha256", None),
        "prediction.prediction_sha256",
    )
    _require(
        canonical_sha256(snapshot) == embedded,
        "prediction embedded self-hash mismatch",
    )
    snapshot["prediction_sha256"] = embedded
    _require(
        snapshot.get("benchmark_contract_sha256") == contract["contract_sha256"],
        "prediction is bound to a different holdout contract",
    )
    provenance = snapshot.get("calibration_provenance")
    _require(isinstance(provenance, Mapping), "prediction calibration provenance missing")
    for field in (
        "response_case_ids_used_for_fit",
        "response_case_ids_used_for_model_selection",
        "response_case_ids_used_for_hyperparameter_tuning",
    ):
        values = provenance.get(field)
        _require(
            isinstance(values, list)
            and all(isinstance(item, str) for item in values),
            f"prediction {field} must be a list",
        )
        leaked = set(values) & set(HOLDOUT_CASES)
        _require(
            not leaked,
            f"holdout response leakage declared in {field}: {sorted(leaked)}",
        )
    _require(
        provenance.get("holdout_response_values_consumed_before_prediction_freeze")
        is False,
        "prediction declares holdout-response leakage",
    )
    predictions = snapshot.get("predictions")
    _require(isinstance(predictions, list), "prediction rows missing")
    by_case: dict[str, Mapping[str, Any]] = {}
    for row in predictions:
        _require(isinstance(row, Mapping), "prediction row must be an object")
        case_id = row.get("case_id")
        _require(
            isinstance(case_id, str) and case_id in HOLDOUT_CASES,
            "prediction may contain only A/C holdout cases",
        )
        _require(case_id not in by_case, "duplicate holdout prediction case")
        for response in (
            "melt_pool_width_mean_um",
            "melt_pool_depth_mean_um",
        ):
            _number(row.get(response), f"prediction[{case_id}].{response}")
        by_case[case_id] = row
    _require(set(by_case) == set(HOLDOUT_CASES), "A/C prediction coverage incomplete")
    return snapshot


def evaluate_in625_ambench_holdout_predictions(
    contract: Mapping[str, Any],
    prediction: Mapping[str, Any],
    *,
    trusted_contract_sha256: str,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Reveal A/C responses only after prediction freeze and compute descriptive metrics."""

    frozen = _authenticate_contract(
        contract,
        trusted_contract_sha256=trusted_contract_sha256,
    )
    pred = _authenticate_prediction(prediction, contract=frozen)
    _process_rows, response_rows = _validated_sources(repository_root)
    holdout_observed = {
        case_id: _case_response_summary(response_rows, case_id)
        for case_id in HOLDOUT_CASES
    }
    prediction_by_case = {
        str(row["case_id"]): row for row in pred["predictions"]
    }

    case_metrics: list[dict[str, Any]] = []
    width_errors: list[float] = []
    depth_errors: list[float] = []
    for case_id in HOLDOUT_CASES:
        observed = holdout_observed[case_id]
        predicted = prediction_by_case[case_id]
        response_metrics: dict[str, Any] = {}
        for short, prediction_field in (
            ("width", "melt_pool_width_mean_um"),
            ("depth", "melt_pool_depth_mean_um"),
        ):
            obs = float(observed[short]["trace_mean_average_um"])
            value = _number(predicted[prediction_field], f"{case_id}.{prediction_field}")
            absolute_error = abs(value - obs)
            relative_error = absolute_error / abs(obs) if obs != 0.0 else None
            sd = observed[short]["trace_mean_sample_sd_um"]
            normalized = (
                absolute_error / float(sd)
                if isinstance(sd, (int, float)) and float(sd) > 0.0
                else None
            )
            low, high = observed[short]["trace_mean_range_um"]
            response_metrics[short] = {
                "prediction_um": value,
                "observed_trace_mean_average_um": obs,
                "observed_trace_mean_sample_sd_um": sd,
                "observed_trace_mean_range_um": [low, high],
                "absolute_error_um": absolute_error,
                "relative_error_fraction": relative_error,
                "absolute_error_over_trace_mean_sample_sd": normalized,
                "prediction_within_observed_trace_mean_range": low <= value <= high,
                "trace_spread_is_calibrated_uncertainty_interval": False,
            }
            (width_errors if short == "width" else depth_errors).append(absolute_error)
        case_metrics.append(
            {
                "case_id": case_id,
                "trace_count": observed["trace_count"],
                "responses": response_metrics,
            }
        )

    evaluation: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "policy_version": BENCHMARK_POLICY_VERSION,
        "evaluation_type": "nist_amb2018_02_case_ac_holdout",
        "benchmark_contract_sha256": frozen["contract_sha256"],
        "prediction_sha256": pred["prediction_sha256"],
        "calibration_case_ids": ["B"],
        "holdout_case_ids": ["A", "C"],
        "case_metrics": case_metrics,
        "aggregate_holdout_metrics": {
            "width_mae_um": _mean(width_errors),
            "depth_mae_um": _mean(depth_errors),
            "case_count": 2,
            "calibration_case_included": False,
        },
        "scientific_boundary": {
            "metrics_are_descriptive_holdout_diagnostics": True,
            "trace_spread_interpreted_as_confidence_interval": False,
            "simulation_treated_as_empirical": False,
            "causal_validity_established": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    evaluation["evaluation_sha256"] = canonical_sha256(evaluation)
    return evaluation


__all__ = [
    "BENCHMARK_POLICY_VERSION",
    "BENCHMARK_SCHEMA_VERSION",
    "CALIBRATION_CASES",
    "HOLDOUT_CASES",
    "In625ModelHoldoutBenchmarkError",
    "build_case_b_persistence_baseline",
    "build_in625_ambench_holdout_contract",
    "evaluate_in625_ambench_holdout_predictions",
]
