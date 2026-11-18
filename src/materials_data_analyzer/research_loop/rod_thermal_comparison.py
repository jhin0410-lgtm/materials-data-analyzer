"""Prediction freeze and off-fit comparison for the rod action."""

import math
import os
from datetime import UTC, datetime

import numpy as np

from .evidence_packet import (
    canonical_json_bytes,
    finalize_evidence_packet,
    validate_evidence_packet,
)
from .rod_thermal_contract import (
    ACTION,
    MODEL,
    VERSION,
    digest,
    load_bound_view,
    load_view,
    require,
)
from .rod_thermal_solver import calibrate, predict, verify_prediction

CALIBRATION = "calibration.json"
FORECAST = "frozen-predictions.json"
RESULT = "comparison.json"
PACKET = "evidence-packet.json"
FREEZE = "prediction-freeze.json"


def now():
    return datetime.now(UTC).isoformat()


def save(path, value):
    raw = canonical_json_bytes(value)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return raw


def _metrics(t, predicted, measured, spec):
    residual = predicted - measured
    rmse = float(np.sqrt(np.mean(residual**2)))
    independent = math.sqrt(
        math.fsum(float(p - o) ** 2 for p, o in zip(predicted.flat, measured.flat))
        / measured.size
    )
    require(abs(independent - rmse) <= 1e-10, "Independent RMSE mismatch")
    late = t >= spec["late_start"]
    return {
        "rmse_K": rmse,
        "rmse_each_sensor_K": np.sqrt(np.mean(residual**2, axis=0)).tolist(),
        "signed_bias_K": residual.mean(axis=0).tolist(),
        "late_samples": int(late.sum()),
        "late_bias_each_sensor_K": residual[late].mean(axis=0).tolist()
        if late.sum() >= 2
        else None,
    }


def _packet(request_sha, request_bytes, result, result_bytes):
    sources = {"rod-request": request_bytes, "rod-result": result_bytes}
    first = next(iter(result["runs"].values()))["models"]["distributed_loss"]
    packet = finalize_evidence_packet(
        {
            "schema_version": VERSION,
            "packet_type": "evidence_packet",
            "evidence_id": f"rod-comparison:{digest(result_bytes)}",
            "evidence_kind": "simulation_result",
            "provider": {
                "provider_id": ACTION,
                "contract_version": VERSION,
                "schema_version": VERSION,
                "adapter_id": "rod-conditional-comparison-v1",
            },
            "subject": {
                "subject_type": "measured_boundary_rod_model",
                "identities": [
                    {"namespace": "solver_id", "value": MODEL, "role": "method"}
                ],
                "material_scope": "request-bound cylindrical rod",
                "description": "Conditional downstream temperature model",
            },
            "contexts": {
                k: {"status": "not_applicable", "attributes": []}
                for k in ("process", "sample", "method", "measurement")
            },
            "results": [
                {
                    "result_id": "first-run-loss-rmse",
                    "result_kind": "conditional_rmse",
                    "value_state": "derived",
                    "value": first["rmse_K"],
                    "value_type": "number",
                    "unit_state": "specified",
                    "unit": "K",
                    "source_binding_ids": ["rod-result"],
                    "derivation_ids": ["compare"],
                    "uncertainty_ids": [],
                    "qualifiers": ["observed-driver", "diagnostic-only"],
                }
            ],
            "uncertainty": [],
            "calibration": {"status": "unknown", "records": []},
            "source_bindings": [
                {
                    "binding_id": key,
                    "role": key,
                    "artifact_id": digest(raw),
                    "locator": f"canonical/rod/{digest(raw)}",
                    "sha256": digest(raw),
                    "byte_size": len(raw),
                    "media_type": "application/json",
                }
                for key, raw in sources.items()
            ],
            "derivation_lineage": [
                {
                    "derivation_id": "compare",
                    "operation": "conditional rod forecast and residual check",
                    "input_binding_ids": ["rod-request"],
                    "input_result_ids": [],
                    "output_result_ids": ["first-run-loss-rmse"],
                    "software": {"name": MODEL, "version": VERSION, "sha256": None},
                    "parameters": {"request_sha256": request_sha},
                    "scientific_status_promoted": False,
                }
            ],
            "independence": {
                "source_family_id": "request-bound-rod-comparison",
                "dataset_parent_id": None,
                "sample_parent_ids": [],
                "acquisition_parent_ids": [],
                "development_family_id": MODEL,
                "overlap_status": "unknown",
                "overlap_with": [],
                "independence_claim_status": "not_assessed",
            },
            "scientific_validity": {
                "domain_verifier_id": "rod-bdf-modal-check-v1",
                "verification_status": "limited",
                "validated_scope": [
                    "numerical time and space checks",
                    "conditional comparison",
                ],
                "excluded_scope": [
                    "empirical measurement creation",
                    "physical mechanism approval",
                ],
                "assumptions": [
                    "constant properties",
                    "prescribed measured boundary",
                    "insulated tip",
                ],
                "scientific_status_promoted": False,
            },
            "comparability": {
                "status": "not_assessed",
                "requirements": ["independent instrument and sample metadata"],
                "limitations": ["Measured boundary input is required"],
                "comparison_performed": False,
                "comparable_claimed": False,
            },
            "limitations": [
                "This result carries no authority to change the status of a scientific hypothesis."
            ],
            "authority": {
                "empirical_evidence_created": False,
                "scientific_status_promoted": False,
                "downstream_use_authorized": False,
                "planning_metadata_only": False,
                "row_level_measurement_authority": False,
                "authority_source": "none",
            },
        }
    )
    return validate_evidence_packet(packet, artifacts=sources)


def compare(directory, stage, request, raw_request, spec):
    partition = request["partition"]
    train = partition["calibration"]
    sensors = spec["sensors"]
    calibration = load_bound_view(
        directory, train, "series", ["time_s", "boundary", *sensors], spec
    )
    models = calibrate(calibration, spec)
    save(stage / CALIBRATION, {"id": train["id"], "models": models})
    forecasts = {}
    for run in partition["validation"]:
        inputs = load_view(directory, run["driver"], ["time_s", "boundary"], spec)
        t, driver = inputs.T
        outputs = {}
        for name, model in models.items():
            k, h = model["k_W_mK"], model["h_effective_W_m2K"]
            values = predict(t, driver, spec, k, h, spec["grid"])
            errors = verify_prediction(t, driver, spec, k, h, spec["grid"], values)
            outputs[name] = {"values_K": values.tolist(), "numerical_checks": errors}
        forecasts[run["id"]] = {
            "time_s": t.tolist(),
            "driver_excess_K": driver.tolist(),
            "models": outputs,
        }
    raw_forecast = save(stage / FORECAST, forecasts)
    freeze = {
        "forecast_sha256": digest(raw_forecast),
        "request_sha256": digest(raw_request),
        "timestamp_utc": now(),
        "validation_response_parsed": False,
    }
    save(stage / FREEZE, freeze)
    require(
        digest((stage / FORECAST).read_bytes()) == freeze["forecast_sha256"],
        "Forecast freeze mismatch",
    )
    # Response parsing occurs after serialization and hashing of all predictions.
    opened_at = now()
    rows = {}
    for run in partition["validation"]:
        locked = forecasts[run["id"]]
        driver = load_bound_view(directory, run, "driver", ["time_s", "boundary"], spec)
        require(
            np.array_equal(driver, np.c_[locked["time_s"], locked["driver_excess_K"]]),
            "Frozen driver differs from authenticated input",
        )
        observed = load_bound_view(
            directory, run, "response", ["time_s", *sensors], spec
        )
        t = observed[:, 0]
        require(
            np.array_equal(t, locked["time_s"]),
            "Validation response time axis does not match driver",
        )
        rows[run["id"]] = {
            "samples": len(t),
            "models": {
                name: _metrics(t, np.asarray(entry["values_K"]), observed[:, 1:], spec)
                for name, entry in locked["models"].items()
            },
        }
    result = {
        "runs": rows,
        "sensor_order": sensors,
        "freeze": freeze,
        "response_access_started_utc": opened_at,
        "scientific_status_promoted": False,
        "basis": "downstream_response_given_measured_boundary",
        "source_scope": "off_fit_acquisitions_independence_not_certified",
    }
    raw_result = save(stage / RESULT, result)
    save(stage / PACKET, _packet(digest(raw_request), raw_request, result, raw_result))
    return result
