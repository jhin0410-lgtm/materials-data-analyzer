"""Strict source and observation contracts for the measured-boundary rod action."""

import csv
import hashlib
import io
import json
import math
import re
from itertools import pairwise
from pathlib import Path

import numpy as np
import scipy

from .kernel import ResearchLoopError

ACTION = "measured_boundary_rod_heat_transfer"
VERSION = "1.0"
MODEL = "cylindrical_rod_fourier_dirichlet_neumann"
SHA = re.compile(r"[a-f0-9]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def require(ok, message):
    if not ok:
        raise ResearchLoopError(message)


def exact(mapping, keys, label):
    require(
        isinstance(mapping, dict) and set(mapping) == set(keys.split()),
        f"Unexpected or missing fields in {label}",
    )


def number(value, low, high, name):
    require(
        type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
        f"{name} is outside the allowed range",
    )
    return float(value)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(raw):
    def pairs(items):
        result = dict(items)
        require(len(result) == len(items), "Duplicate JSON key")
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def file_path(directory, value):
    require(
        isinstance(value, str) and value and "\\" not in value, "Invalid input path"
    )
    relative = Path(value)
    require(
        not relative.is_absolute() and ".." not in relative.parts,
        "Input must stay in request directory",
    )
    candidate = directory / relative
    resolved = candidate.resolve(strict=True)
    require(
        candidate == resolved
        and resolved.is_relative_to(directory)
        and resolved.is_file(),
        "Source must be a regular, confined, non-aliased file",
    )
    return resolved


def file_bytes(path, cap):
    with path.open("rb") as handle:
        raw = handle.read(cap + 1)
    require(len(raw) <= cap, "Input resource limit exceeded")
    return raw


def validate_request(request):
    exact(
        request,
        "schema_version action_type model_id model_version scipy_version "
        "material geometry temperatures numerics partition prior_ledger_sha256 source_columns",
        "rod request",
    )
    require(
        (
            request["schema_version"],
            request["action_type"],
            request["model_id"],
            request["model_version"],
            request["scipy_version"],
        )
        == (VERSION, ACTION, MODEL, VERSION, scipy.__version__),
        "Rod model, schema or SciPy version mismatch",
    )
    mat, geo, temp, numeric = [
        request[k] for k in ("material", "geometry", "temperatures", "numerics")
    ]
    exact(mat, "identity source density specific_heat k_bounds h_max units", "material")
    for field in ("source", "identity"):
        require(
            isinstance(mat[field], str) and bool(mat[field].strip()), f"Missing {field}"
        )
    require(
        mat["units"]
        == {
            "density": "kg/m^3",
            "specific_heat": "J/(kg*K)",
            "conductivity": "W/(m*K)",
            "heat_loss": "W/(m^2*K)",
        },
        "Invalid material units",
    )
    exact(geo, "length diameter length_unit boundary sensors", "geometry")
    require(
        geo["length_unit"] == "m"
        and geo["boundary"] == "measured_dirichlet_insulated_tip",
        "Invalid rod geometry units or boundary",
    )
    length = number(geo["length"], 0.01, 2.0, "length")
    diameter = number(geo["diameter"], 0.0001, length / 10.0, "diameter")
    require(
        isinstance(geo["sensors"], list) and 1 <= len(geo["sensors"]) <= 16,
        "Invalid sensor count",
    )
    sensors, positions = [], []
    for sensor in geo["sensors"]:
        exact(sensor, "id position_m", "sensor")
        require(
            isinstance(sensor["id"], str)
            and IDENTIFIER.fullmatch(sensor["id"])
            and sensor["id"] not in {"time_s", "boundary"},
            "Invalid sensor ID",
        )
        sensors.append(sensor["id"])
        positions.append(number(sensor["position_m"], 1e-6, length, "sensor position"))
    require(
        len(set(sensors)) == len(sensors)
        and all(a < b for a, b in pairwise(positions)),
        "Sensor IDs and positions must be unique and in increasing physical order",
    )
    exact(temp, "encoding reference_K ambient_K", "temperature contract")
    require(
        temp["encoding"] in ("excess_K", "absolute_K", "absolute_degC"),
        "Unsupported temperature definition/unit",
    )
    ambient = number(temp["ambient_K"], 173.0, 500.0, "ambient")
    if temp["encoding"] == "excess_K":
        reference = number(
            temp["reference_K"], 173.0, 500.0, "excess temperature reference"
        )
    else:
        require(
            temp["reference_K"] is None,
            "Absolute temperature must not have a reference offset",
        )
        reference = 273.15 if temp["encoding"] == "absolute_degC" else 0.0
    exact(numeric, "grid grid_tol_K bdf_tol_K duration_s late_start_s", "numerics")
    grid = numeric["grid"]
    require(
        type(grid) is int and 24 <= grid <= 200 and positions[0] >= 2 * length / grid,
        "Grid is unsupported or does not resolve the first downstream sensor",
    )
    require(
        isinstance(mat["k_bounds"], list) and len(mat["k_bounds"]) == 2,
        "Two conductivity bounds are required",
    )
    k_low, k_high = [number(k, 0.5, 500.0, "conductivity") for k in mat["k_bounds"]]
    require(k_low < k_high, "Conductivity bounds must be increasing")
    duration = number(numeric["duration_s"], 0.1, 3000, "duration")
    spec = {
        "length": length,
        "diameter": diameter,
        "positions": positions,
        "sensors": sensors,
        "source_offset_K": reference - ambient,
        "ambient_K": ambient,
        "grid": grid,
        "density": number(mat["density"], 300.0, 25000.0, "density"),
        "specific_heat": number(mat["specific_heat"], 50.0, 5000.0, "specific heat"),
        "k_bounds": [k_low, k_high],
        "h_max": number(mat["h_max"], 1.0, 500.0, "heat-loss bound"),
        "grid_tol": number(numeric["grid_tol_K"], 1e-10, 0.1, "grid tolerance"),
        "bdf_tol": number(numeric["bdf_tol_K"], 1e-10, 0.015, "BDF tolerance"),
        "duration": duration,
        "late_start": number(numeric["late_start_s"], 0, duration, "late start"),
    }
    columns = request["source_columns"]
    exact(columns, "time_s boundary " + " ".join(sensors), "original channel mapping")
    require(
        all(isinstance(v, str) and v for v in columns.values())
        and len(set(columns.values())) == len(columns),
        "Original source channels must be distinct",
    )
    spec["source_columns"] = columns
    partition = request["partition"]
    exact(partition, "calibration validation", "partition")
    train, validation = partition["calibration"], partition["validation"]
    require(
        isinstance(validation, list) and 1 <= len(validation) <= 4,
        "Invalid validation run count",
    )
    for i, run in enumerate([train, *validation]):
        exact(
            run,
            "id original_path original_sha256 source series"
            if i == 0
            else "id original_path original_sha256 source driver response",
            "run partition",
        )
        require(
            isinstance(run["id"], str)
            and IDENTIFIER.fullmatch(run["id"])
            and isinstance(run["original_path"], str)
            and isinstance(run["original_sha256"], str)
            and SHA.fullmatch(run["original_sha256"])
            and isinstance(run["source"], str)
            and bool(run["source"].strip()),
            "Run provenance is missing",
        )
        for view in ("series",) if i == 0 else ("driver", "response"):
            ref = run[view]
            exact(ref, "path sha256", "data view")
            require(
                isinstance(ref["path"], str)
                and isinstance(ref["sha256"], str)
                and SHA.fullmatch(ref["sha256"]),
                "Invalid view reference",
            )
    runs = [train, *validation]
    views = [
        train["series"],
        *(r[k] for r in validation for k in ("driver", "response")),
    ]
    paths = [*(r["path"] for r in views), *(r["original_path"] for r in runs)]
    require(
        len({r["id"].casefold() for r in runs}) == len(runs)
        and len({r["original_sha256"] for r in runs}) == len(runs)
        and len({r["sha256"] for r in views}) == len(views)
        and len(set(paths)) == len(paths),
        "Overlapping calibration/validation data",
    )
    return spec


def load_view(directory, ref, header, spec):
    raw = file_bytes(file_path(directory, ref["path"]), 2_000_000)
    require(digest(raw) == ref["sha256"], f"Source SHA-256 mismatch: {ref['path']}")
    rows = csv.reader(io.StringIO(raw.decode("utf-8")), strict=True)
    require(next(rows, None) == header, f"Unexpected columns or order: {ref['path']}")
    return _series(list(rows), len(header), spec)


def load_bound_view(directory, run, role, header, spec):
    """Match only the authorized columns to the checksum-bound original acquisition."""
    prepared = load_view(directory, run[role], header, spec)
    path = file_path(directory, run["original_path"])
    raw = file_bytes(path, 2_000_000)
    require(
        digest(raw) == run["original_sha256"],
        f"Original acquisition SHA-256 mismatch: {path.name}",
    )
    reader = csv.reader(io.StringIO(raw.decode("utf-8")), strict=True)
    columns = next(reader, [])
    requested = [spec["source_columns"][label] for label in header]
    require(
        len(set(columns)) == len(columns) and set(requested) <= set(columns),
        "Original acquisition channels do not match the declared mapping",
    )
    indices = [columns.index(c) for c in requested]
    projected = []
    for row in reader:
        require(
            len(row) == len(columns) and len(projected) < 5000,
            "Malformed original acquisition CSV",
        )
        projected.append([row[index] for index in indices])
    actual = _series(projected, len(header), spec)
    require(
        np.array_equal(actual, prepared),
        "Prepared view differs from the authenticated original channels",
    )
    return prepared


def _series(parsed, width, spec):
    require(
        3 <= len(parsed) <= 5000 and all(len(r) == width for r in parsed),
        "Malformed CSV shape",
    )
    data = np.asarray(parsed, dtype=float)
    require(
        np.isfinite(data).all()
        and data[0, 0] == 0
        and np.all(np.diff(data[:, 0]) >= 0.001)
        and data[-1, 0] >= spec["duration"],
        "Invalid acquisition time axis or non-finite observation",
    )
    data = data[data[:, 0] <= spec["duration"]]
    require(len(data) >= 3, "Insufficient observations in declared window")
    data[:, 1:] += spec["source_offset_K"]
    absolute = data[:, 1:] + spec["ambient_K"]
    require(
        np.all((150 <= absolute) & (absolute <= 900)),
        "Acquisition temperature outside physical action scope",
    )
    return data
