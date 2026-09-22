"""Production adapters from verified repository/domain artifacts into EvidencePacket v1.

These adapters are deliberately outside the provider-agnostic EvidencePacket validator.
They preserve the authority already established by their upstream domain contracts but may
not create comparability, downstream-use authorization, or scientific promotion.

Two scientifically different inputs are supported:

* the repository-pinned NIST AM-Bench 2018-02 IN625 trace tables -> empirical measurement
  EvidencePackets, one packet per physical AMMT trace;
* an independently replayed characterization L0-L8 assessment -> planning-metadata
  EvidencePacket only.

The NIST adapter authenticates the exact reviewed source files against versioned Git-blob
roots before deriving SHA-256 EvidencePacket source bindings. This prevents a modified
repository file from self-authorizing merely by receiving a new packet hash.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .characterization_evidence_bridge import (
    verify_characterization_evidence_assessment,
)
from .evidence_packet import (
    canonical_json_bytes,
    finalize_evidence_packet,
)
from .heat_conduction_solver import (
    HEAT_SOLVER_ID,
    HEAT_SOLVER_VERSION,
    run_reference_heat_conduction_request,
)

NIST_AMBENCH_ADAPTER_ID = "nist-ambench-2018-02-trace-evidence-packet-v1"
CHARACTERIZATION_ADAPTER_ID = "verified-characterization-ladder-evidence-packet-v1"

_NIST_PATHS = {
    "process": "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
    "measurement": "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
    "readme": "data/case_studies/nist_ambench_2018_02/README.md",
    "readiness": "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
}
_NIST_BLOB_SHA1 = {
    "process": "c39994e94474cb5f2f132221704dce03b5f76cd2",
    "measurement": "083bbd12a631d8603331c91c0a46db83a59be096",
    "readme": "979c243b64f73648cf61e697b3436ab5995b4056",
    "readiness": "0ffdbea391386e16f4a65fcfb04cd7ed38620d34",
}
_NIST_RAW_SHA256 = {
    "process": "bfec7d3099304edb3f7cefa96309d64853cc006eadf02ea976dc78b16bf1f137",
    "measurement": "728dc7de7675e14d6f5e1c0df42dcef90dcdd6c7d795a7039209decfc0b2712e",
    "readme": "9cd45e49c3b3c9aef455691bb9782013ae0103cfbf49c212ff083358523ef629",
    "readiness": "be2d1105bfeec861974f97979096d837255a4dd04f9642dd2eb051267abae8f4",
}
_PROCESS_HEADER = (
    "sample_id",
    "case_id",
    "trace_number",
    "actual_laser_power_w",
    "scan_speed_mm_s",
    "system",
    "material",
)
_MEASUREMENT_HEADER = (
    "sample_id",
    "case_id",
    "trace_number",
    "melt_pool_width_mean_um",
    "melt_pool_width_std_dev_um",
    "melt_pool_depth_mean_um",
    "melt_pool_depth_std_dev_um",
)


class EvidencePacketAdapterError(ValueError):
    """Raised when a domain artifact cannot be adapted without widening authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidencePacketAdapterError(message)


def _plain_json_snapshot(value: object, *, field: str) -> object:
    """Detach untrusted Mapping/sequence views into one JSON-native snapshot."""

    if value is None or type(value) in {bool, int, float, str}:
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key in value.keys():
            _require(type(raw_key) is str, f"{field} object keys must be strings")
            key = str(raw_key)
            _require(key not in result, f"{field} contains duplicate key: {key}")
            result[key] = _plain_json_snapshot(value[raw_key], field=f"{field}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _plain_json_snapshot(item, field=f"{field}[{index}]")
            for index, item in enumerate(value)
        ]
    raise EvidencePacketAdapterError(
        f"{field} contains non-JSON value type: {type(value).__name__}"
    )


def _git_blob_sha1(raw: bytes) -> str:
    payload = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def _repo_file(root: Path, relative: str) -> tuple[Path, bytes]:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise EvidencePacketAdapterError(
            f"evidence source escaped repository root: {relative}"
        ) from exc
    _require(path.is_file() and not path.is_symlink(), f"evidence source is not a regular file: {relative}")
    return path, path.read_bytes()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidencePacketAdapterError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _json_object(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidencePacketAdapterError(f"{field} must be duplicate-free UTF-8 JSON") from exc
    _require(isinstance(value, dict), f"{field} root must be an object")
    return value


def _csv_rows(raw: bytes, header: tuple[str, ...], field: str) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidencePacketAdapterError(f"{field} must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    _require(tuple(reader.fieldnames or ()) == header, f"{field} header drifted")
    rows = list(reader)
    _require(bool(rows), f"{field} must contain rows")
    _require(
        all(set(row) == set(header) and all(value is not None for value in row.values()) for row in rows),
        f"{field} row shape drifted",
    )
    return rows


def _finite_float(value: str, field: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise EvidencePacketAdapterError(f"{field} must be numeric") from exc
    _require(result == result and result not in {float("inf"), float("-inf")}, f"{field} must be finite")
    return result


def _integer_text(value: str, field: str) -> int:
    _require(value.isdigit(), f"{field} must be a positive integer string")
    result = int(value)
    _require(result > 0, f"{field} must be positive")
    return result


def _source_binding(
    *,
    binding_id: str,
    role: str,
    artifact_id: str,
    locator: str,
    raw: bytes,
    media_type: str,
) -> dict[str, Any]:
    return {
        "binding_id": binding_id,
        "role": role,
        "artifact_id": artifact_id,
        "locator": locator,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "media_type": media_type,
    }


def _attribute(
    name: str,
    value: object,
    *,
    source_binding_ids: list[str],
    unit: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    elif isinstance(value, str):
        value_type = "text"
    else:
        raise EvidencePacketAdapterError(f"unsupported context value type for {name}")
    return {
        "name": name,
        "value": value,
        "value_type": value_type,
        "unit_state": "specified" if unit is not None else "not_applicable",
        "unit": unit,
        "source_binding_ids": list(source_binding_ids),
    }


def _authenticate_nist_sources(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for key, relative in _NIST_PATHS.items():
        path, raw = _repo_file(root, relative)
        observed_blob = _git_blob_sha1(raw)
        observed_sha256 = hashlib.sha256(raw).hexdigest()
        _require(
            observed_blob == _NIST_BLOB_SHA1[key],
            f"NIST AM-Bench {key} source bytes drifted from reviewed Git-blob authority",
        )
        _require(
            observed_sha256 == _NIST_RAW_SHA256[key],
            f"NIST AM-Bench {key} source bytes drifted from reviewed SHA-256 authority",
        )
        records[key] = {
            "path": path,
            "raw": raw,
            "relative": relative,
            "git_blob_sha1": observed_blob,
            "sha256": observed_sha256,
        }

    process_rows = _csv_rows(records["process"]["raw"], _PROCESS_HEADER, "NIST process table")
    measurement_rows = _csv_rows(
        records["measurement"]["raw"],
        _MEASUREMENT_HEADER,
        "NIST measurement table",
    )
    _require(len(process_rows) == len(measurement_rows) == 10, "NIST trace count drifted")

    process_ids = [row["sample_id"] for row in process_rows]
    measurement_ids = [row["sample_id"] for row in measurement_rows]
    _require(len(set(process_ids)) == 10, "NIST process sample IDs must be unique")
    _require(set(process_ids) == set(measurement_ids), "NIST process/measurement identity join drifted")
    _require(
        all(row["system"] == "AMMT" and row["material"] == "IN625" for row in process_rows),
        "NIST system/material identity drifted",
    )
    conditions = {
        (
            _finite_float(row["actual_laser_power_w"], "actual_laser_power_w"),
            _finite_float(row["scan_speed_mm_s"], "scan_speed_mm_s"),
        )
        for row in process_rows
    }
    _require(
        conditions == {(137.9, 400.0), (179.2, 800.0), (179.2, 1200.0)},
        "NIST exact process-condition set drifted",
    )

    readme = records["readme"]["raw"].decode("utf-8")
    for phrase in (
        "Material: nickel-based superalloy IN625.",
        "System: NIST Additive Manufacturing Metrology Testbed (`AMMT`).",
        "Geometry: individual laser scan tracks on a bare substrate without powder.",
        "Characterization: polished transverse cross sections measured using the",
        "Reported individual-measurement uncertainty: approximately 0.5 µm.",
        "Status: `diagnostic`.",
    ):
        _require(phrase in readme, "NIST experimental/scientific boundary text drifted")

    readiness = _json_object(records["readiness"]["raw"], "NIST planning readiness")
    tracked = readiness.get("tracked_case")
    scope = readiness.get("current_scope")
    _require(isinstance(tracked, Mapping) and isinstance(scope, Mapping), "NIST readiness shape drifted")
    _require(
        readiness.get("schema_version") == "1.0"
        and tracked.get("material") == "IN625"
        and tracked.get("system") == "AMMT"
        and tracked.get("trace_count") == 10
        and tracked.get("unique_process_condition_count") == 3,
        "NIST readiness tracked-case identity drifted",
    )
    _require(
        scope.get("maximum_allowed_use") == "descriptive"
        and scope.get("predictive_use_authorized") is False
        and scope.get("causal_use_authorized") is False
        and scope.get("engineering_use_authorized") is False
        and readiness.get("model_fit_authorized") is False
        and readiness.get("scientific_evidence_upgrade_authorized") is False,
        "NIST readiness scientific-use boundary widened",
    )

    records["process"]["rows"] = process_rows
    records["measurement"]["rows"] = measurement_rows
    return records


def build_nist_ambench_trace_evidence_packets(
    repository_root: str | Path,
) -> list[dict[str, Any]]:
    """Build ten source-bound empirical packets for the reviewed NIST AM-Bench traces."""

    root = Path(repository_root).expanduser().resolve(strict=True)
    sources = _authenticate_nist_sources(root)
    process_rows = sources["process"]["rows"]
    measurement_rows = sources["measurement"]["rows"]
    assert isinstance(process_rows, list) and isinstance(measurement_rows, list)

    process_by_id = {row["sample_id"]: row for row in process_rows}
    measurement_by_id = {row["sample_id"]: row for row in measurement_rows}

    source_bindings = [
        _source_binding(
            binding_id="nist-process-table",
            role="source_reported_process_conditions",
            artifact_id="nist-ambench-2018-02-process-table",
            locator=_NIST_PATHS["process"],
            raw=sources["process"]["raw"],
            media_type="text/csv",
        ),
        _source_binding(
            binding_id="nist-measurement-table",
            role="source_reported_trace_measurements",
            artifact_id="nist-ambench-2018-02-measurement-table",
            locator=_NIST_PATHS["measurement"],
            raw=sources["measurement"]["raw"],
            media_type="text/csv",
        ),
        _source_binding(
            binding_id="nist-case-readme",
            role="reviewed_experimental_context",
            artifact_id="nist-ambench-2018-02-case-readme",
            locator=_NIST_PATHS["readme"],
            raw=sources["readme"]["raw"],
            media_type="text/markdown",
        ),
        _source_binding(
            binding_id="nist-planning-readiness",
            role="reviewed_scientific_use_boundary",
            artifact_id="nist-ambench-2018-02-planning-readiness",
            locator=_NIST_PATHS["readiness"],
            raw=sources["readiness"]["raw"],
            media_type="application/json",
        ),
    ]

    packets: list[dict[str, Any]] = []
    for sample_id in sorted(process_by_id):
        process = process_by_id[sample_id]
        measurement = measurement_by_id[sample_id]
        _require(
            process["case_id"] == measurement["case_id"]
            and process["trace_number"] == measurement["trace_number"],
            f"NIST joined row identity drifted for {sample_id}",
        )
        case_id = process["case_id"]
        trace_number = _integer_text(process["trace_number"], f"{sample_id}.trace_number")
        power = _finite_float(process["actual_laser_power_w"], f"{sample_id}.actual_laser_power_w")
        speed = _finite_float(process["scan_speed_mm_s"], f"{sample_id}.scan_speed_mm_s")
        width = _finite_float(
            measurement["melt_pool_width_mean_um"],
            f"{sample_id}.melt_pool_width_mean_um",
        )
        width_sd = _finite_float(
            measurement["melt_pool_width_std_dev_um"],
            f"{sample_id}.melt_pool_width_std_dev_um",
        )
        depth = _finite_float(
            measurement["melt_pool_depth_mean_um"],
            f"{sample_id}.melt_pool_depth_mean_um",
        )
        depth_sd = _finite_float(
            measurement["melt_pool_depth_std_dev_um"],
            f"{sample_id}.melt_pool_depth_std_dev_um",
        )
        _require(width > 0.0 and depth > 0.0 and width_sd >= 0.0 and depth_sd >= 0.0, "NIST geometry values are invalid")

        packet = finalize_evidence_packet(
            {
                "schema_version": "1.0",
                "packet_type": "evidence_packet",
                "evidence_id": f"nist-ambench-2018-02:{sample_id}",
                "evidence_kind": "measurement",
                "provider": {
                    "provider_id": "nist-ambench-2018-02-trace-provider",
                    "contract_version": "1.0",
                    "schema_version": "1.0",
                    "adapter_id": NIST_AMBENCH_ADAPTER_ID,
                },
                "subject": {
                    "subject_type": "material_process_characterization_measurement",
                    "identities": [
                        {"namespace": "material", "value": "IN625", "role": "material"},
                        {"namespace": "sample", "value": sample_id, "role": "sample"},
                        {"namespace": "nist_ambench_case", "value": case_id, "role": "case"},
                        {"namespace": "nist_ambench_trace", "value": str(trace_number), "role": "trace"},
                    ],
                    "material_scope": "NIST AM-Bench 2018-02 IN625 AMMT bare-substrate single-track case",
                    "description": "One source-reported NIST AM-Bench 2018-02 transverse melt-pool trace measurement.",
                },
                "contexts": {
                    "process": {
                        "status": "applicable",
                        "attributes": [
                            _attribute("process_family", "additive_manufacturing", source_binding_ids=["nist-case-readme"]),
                            _attribute("process_route", "AMMT bare-substrate single-track laser scan", source_binding_ids=["nist-case-readme"]),
                            _attribute("actual_laser_power_w", power, unit="W", source_binding_ids=["nist-process-table"]),
                            _attribute("scan_speed_mm_s", speed, unit="mm/s", source_binding_ids=["nist-process-table"]),
                            _attribute("system", "NIST AMMT", source_binding_ids=["nist-process-table", "nist-case-readme"]),
                        ],
                    },
                    "sample": {
                        "status": "applicable",
                        "attributes": [
                            _attribute("sample_id", sample_id, source_binding_ids=["nist-process-table", "nist-measurement-table"]),
                            _attribute("case_id", case_id, source_binding_ids=["nist-process-table", "nist-measurement-table"]),
                            _attribute("trace_number", trace_number, source_binding_ids=["nist-process-table", "nist-measurement-table"]),
                            _attribute("geometry", "individual laser scan track on bare substrate without powder", source_binding_ids=["nist-case-readme"]),
                        ],
                    },
                    "method": {
                        "status": "applicable",
                        "attributes": [
                            _attribute("method", "polished transverse cross-section optical metrology", source_binding_ids=["nist-case-readme"]),
                            _attribute("protocol_reference", "NIST AM-Bench 2018-02 transverse cross-section results", source_binding_ids=["nist-case-readme"]),
                        ],
                    },
                    "measurement": {
                        "status": "applicable",
                        "attributes": [
                            _attribute("measurement_semantics", "source-reported trace-level mean and standard deviation", source_binding_ids=["nist-measurement-table", "nist-case-readme"]),
                            _attribute("individual_measurement_uncertainty_approx_um", 0.5, unit="um", source_binding_ids=["nist-case-readme"]),
                            _attribute("reference_convention", "transverse cross-section melt-pool geometry", source_binding_ids=["nist-case-readme"]),
                        ],
                    },
                },
                "results": [
                    {
                        "result_id": "melt-pool-width-mean",
                        "result_kind": "melt_pool_width_mean",
                        "value_state": "observed",
                        "value": width,
                        "value_type": "number",
                        "unit_state": "specified",
                        "unit": "um",
                        "source_binding_ids": ["nist-measurement-table"],
                        "derivation_ids": [],
                        "uncertainty_ids": ["melt-pool-width-std-dev"],
                        "qualifiers": ["source-reported", "trace-level", "descriptive-only"],
                    },
                    {
                        "result_id": "melt-pool-depth-mean",
                        "result_kind": "melt_pool_depth_mean",
                        "value_state": "observed",
                        "value": depth,
                        "value_type": "number",
                        "unit_state": "specified",
                        "unit": "um",
                        "source_binding_ids": ["nist-measurement-table"],
                        "derivation_ids": [],
                        "uncertainty_ids": ["melt-pool-depth-std-dev"],
                        "qualifiers": ["source-reported", "trace-level", "descriptive-only"],
                    },
                ],
                "uncertainty": [
                    {
                        "uncertainty_id": "melt-pool-width-std-dev",
                        "status": "quantified",
                        "kind": "source_reported_standard_deviation",
                        "value": width_sd,
                        "unit": "um",
                        "distribution": "standard_deviation",
                        "confidence_level": None,
                        "source_binding_ids": ["nist-measurement-table"],
                        "notes": "Source table reports this trace-level standard-deviation value; no additional uncertainty propagation is performed.",
                    },
                    {
                        "uncertainty_id": "melt-pool-depth-std-dev",
                        "status": "quantified",
                        "kind": "source_reported_standard_deviation",
                        "value": depth_sd,
                        "unit": "um",
                        "distribution": "standard_deviation",
                        "confidence_level": None,
                        "source_binding_ids": ["nist-measurement-table"],
                        "notes": "Source table reports this trace-level standard-deviation value; no additional uncertainty propagation is performed.",
                    },
                ],
                "calibration": {"status": "unknown", "records": []},
                "source_bindings": source_bindings,
                "derivation_lineage": [],
                "independence": {
                    "source_family_id": "nist-ambench-2018-02",
                    "dataset_parent_id": "nist-ambench-2018-02",
                    "sample_parent_ids": [sample_id],
                    "acquisition_parent_ids": [sample_id],
                    "development_family_id": None,
                    "overlap_status": "unknown",
                    "overlap_with": [],
                    "independence_claim_status": "not_assessed",
                },
                "scientific_validity": {
                    "domain_verifier_id": NIST_AMBENCH_ADAPTER_ID,
                    "verification_status": "limited",
                    "validated_scope": [
                        "exact reviewed repository source-byte identity",
                        "trace/sample identity join",
                        "source-reported process condition",
                        "source-reported transverse melt-pool width/depth means and standard deviations",
                        "descriptive-use boundary",
                    ],
                    "excluded_scope": [
                        "independent replication",
                        "cross-source comparability",
                        "predictive validation",
                        "causality",
                        "process optimization",
                        "engineering release",
                        "instrument-calibration transfer",
                    ],
                    "assumptions": [
                        "The repository-pinned tracked tables preserve the reviewed manual transcription from official NIST benchmark/result pages.",
                    ],
                    "scientific_status_promoted": False,
                },
                "comparability": {
                    "status": "not_assessed",
                    "requirements": ["separate provenance-aware Comparability Engine assessment required"],
                    "limitations": ["same material or nominal process labels do not establish cross-source comparability"],
                    "comparison_performed": False,
                    "comparable_claimed": False,
                },
                "limitations": [
                    "The tracked numeric tables were manually transcribed from official NIST result pages; official webpage bytes are not represented as row-level packet artifacts, so this packet does not claim direct row-level measurement authority.",
                    "Calibration state needed for cross-experiment transfer is not established by this packet.",
                    "Only descriptive use inside the reviewed ten-trace case is supported.",
                ],
                "authority": {
                    "empirical_evidence_created": True,
                    "scientific_status_promoted": False,
                    "downstream_use_authorized": False,
                    "planning_metadata_only": False,
                    "row_level_measurement_authority": False,
                    "authority_source": "preexisting_authenticated_scientific_record",
                },
            }
        )
        packets.append(packet)

    return packets


def build_nist_ambench_trace_validation_material(
    repository_root: str | Path,
) -> list[dict[str, Any]]:
    """Return packets plus exact artifact/expectation material, but no self-issued trust root.

    The caller must obtain and pin the canonical SHA-256 of the expectation object outside
    this adapter before using the authority-bearing authenticated validation path. This
    separation prevents the producer path from authenticating its own mutable pair.
    """

    root = Path(repository_root).expanduser().resolve(strict=True)
    sources = _authenticate_nist_sources(root)
    packets = build_nist_ambench_trace_evidence_packets(root)
    artifacts = {
        "nist-process-table": bytes(sources["process"]["raw"]),
        "nist-measurement-table": bytes(sources["measurement"]["raw"]),
        "nist-case-readme": bytes(sources["readme"]["raw"]),
        "nist-planning-readiness": bytes(sources["readiness"]["raw"]),
    }
    result: list[dict[str, Any]] = []
    for packet in packets:
        results = packet["results"]
        uncertainty = packet["uncertainty"]
        _require(isinstance(results, list), "NIST packet results must be a list")
        _require(isinstance(uncertainty, list), "NIST packet uncertainty must be a list")
        result_units = {
            item["result_id"]: item["unit"]
            for item in results
            if isinstance(item, Mapping)
        }
        uncertainty_statuses = {
            item["uncertainty_id"]: item["status"]
            for item in uncertainty
            if isinstance(item, Mapping)
        }
        expected = {
            "provider_id": "nist-ambench-2018-02-trace-provider",
            "subject_identities": copy.deepcopy(packet["subject"]["identities"]),
            "source_bindings": copy.deepcopy(packet["source_bindings"]),
            "result_units": result_units,
            "calibration_status": "unknown",
            "uncertainty_status_by_id": uncertainty_statuses,
            "existing_source_family_ids": [],
            "packet_sha256": packet["packet_sha256"],
        }
        result.append(
            {
                "evidence_id": packet["evidence_id"],
                "packet": packet,
                "artifacts": dict(artifacts),
                "expected": expected,
            }
        )
    return result

def build_heat_conduction_reference_evidence_packet(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt one validated deterministic heat-diffusion reference run as non-empirical evidence."""

    request_snapshot = _plain_json_snapshot(request, field="heat_conduction_request")
    _require(
        isinstance(request_snapshot, dict),
        "heat_conduction_request root must be an object",
    )
    request_bytes = canonical_json_bytes(request_snapshot)
    result = run_reference_heat_conduction_request(request_snapshot)
    _require(
        result.get("run_status") == "completed",
        "heat-conduction reference run must complete before EvidencePacket adaptation",
    )
    validation = result.get("validation")
    stability = result.get("numerical_stability")
    _require(isinstance(validation, Mapping), "heat reference validation result is malformed")
    _require(isinstance(stability, Mapping), "heat reference stability result is malformed")
    _require(
        validation.get("passed") is True and stability.get("stable") is True,
        "heat-conduction reference run must pass analytical validation and stability",
    )

    result_bytes = canonical_json_bytes(result)
    request_sha = hashlib.sha256(request_bytes).hexdigest()
    result_sha = hashlib.sha256(result_bytes).hexdigest()
    max_error = validation.get("max_abs_error_K")
    fourier = stability.get("fourier_number")
    _require(
        isinstance(max_error, (int, float)) and not isinstance(max_error, bool),
        "heat reference max_abs_error_K is malformed",
    )
    _require(
        isinstance(fourier, (int, float)) and not isinstance(fourier, bool),
        "heat reference Fourier number is malformed",
    )

    return finalize_evidence_packet(
        {
            "schema_version": "1.0",
            "packet_type": "evidence_packet",
            "evidence_id": f"heat-conduction-reference:{result['result_sha256']}",
            "evidence_kind": "simulation_result",
            "provider": {
                "provider_id": "audited-heat-conduction-reference-solver",
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": "heat-conduction-reference-evidence-packet-v1",
            },
            "subject": {
                "subject_type": "numerical_reference_problem",
                "identities": [
                    {
                        "namespace": "solver_id",
                        "value": HEAT_SOLVER_ID,
                        "role": "method",
                    },
                    {
                        "namespace": "solver_version",
                        "value": HEAT_SOLVER_VERSION,
                        "role": "version",
                    },
                    {
                        "namespace": "request_sha256",
                        "value": str(result["request_sha256"]),
                        "role": "request",
                    },
                ],
                "material_scope": "constant-property one-dimensional heat diffusion reference problem",
                "description": (
                    "Deterministic FTCS numerical reference result validated against the "
                    "analytical sine eigenmode; not an LPBF or empirical material model."
                ),
            },
            "contexts": {
                "process": {"status": "not_applicable", "attributes": []},
                "sample": {"status": "not_applicable", "attributes": []},
                "method": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "governing_equation",
                            "dT/dt = alpha * d2T/dx2",
                            source_binding_ids=["heat-request", "heat-result"],
                        ),
                        _attribute(
                            "numerical_method",
                            "explicit FTCS finite difference",
                            source_binding_ids=["heat-request", "heat-result"],
                        ),
                        _attribute(
                            "analytical_validation",
                            "sine_eigenmode_analytical",
                            source_binding_ids=["heat-request", "heat-result"],
                        ),
                    ],
                },
                "measurement": {"status": "not_applicable", "attributes": []},
            },
            "results": [
                {
                    "result_id": "validation-max-abs-error",
                    "result_kind": "numerical_validation_max_abs_error",
                    "value_state": "derived",
                    "value": float(max_error),
                    "value_type": "number",
                    "unit_state": "specified",
                    "unit": "K",
                    "source_binding_ids": ["heat-result"],
                    "derivation_ids": ["heat-reference-run"],
                    "uncertainty_ids": [],
                    "qualifiers": ["numerical-reference-only", "analytical-validation"],
                },
                {
                    "result_id": "ftcs-fourier-number",
                    "result_kind": "ftcs_fourier_number",
                    "value_state": "derived",
                    "value": float(fourier),
                    "value_type": "number",
                    "unit_state": "not_applicable",
                    "unit": None,
                    "source_binding_ids": ["heat-result"],
                    "derivation_ids": ["heat-reference-run"],
                    "uncertainty_ids": [],
                    "qualifiers": ["numerical-stability-diagnostic"],
                },
            ],
            "uncertainty": [],
            "calibration": {"status": "not_applicable", "records": []},
            "source_bindings": [
                {
                    "binding_id": "heat-request",
                    "role": "audited_solver_request",
                    "artifact_id": str(result["request_sha256"]),
                    "locator": f"canonical/heat_conduction/request/{request_sha}.json",
                    "sha256": request_sha,
                    "byte_size": len(request_bytes),
                    "media_type": "application/json",
                },
                {
                    "binding_id": "heat-result",
                    "role": "deterministic_solver_result",
                    "artifact_id": str(result["result_sha256"]),
                    "locator": f"canonical/heat_conduction/result/{result_sha}.json",
                    "sha256": result_sha,
                    "byte_size": len(result_bytes),
                    "media_type": "application/json",
                },
            ],
            "derivation_lineage": [
                {
                    "derivation_id": "heat-reference-run",
                    "operation": "bounded deterministic 1-D heat-conduction FTCS solve with analytical validation",
                    "input_binding_ids": ["heat-request"],
                    "input_result_ids": [],
                    "output_result_ids": [
                        "validation-max-abs-error",
                        "ftcs-fourier-number",
                    ],
                    "software": {
                        "name": HEAT_SOLVER_ID,
                        "version": HEAT_SOLVER_VERSION,
                        "sha256": None,
                    },
                    "parameters": {
                        "request_sha256": str(result["request_sha256"]),
                        "result_sha256": str(result["result_sha256"]),
                    },
                    "scientific_status_promoted": False,
                }
            ],
            "independence": {
                "source_family_id": "deterministic-reference-simulation",
                "dataset_parent_id": None,
                "sample_parent_ids": [],
                "acquisition_parent_ids": [],
                "development_family_id": HEAT_SOLVER_ID,
                "overlap_status": "unknown",
                "overlap_with": [],
                "independence_claim_status": "not_assessed",
            },
            "scientific_validity": {
                "domain_verifier_id": "heat-conduction-sine-eigenmode-analytical-v1",
                "verification_status": "limited",
                "validated_scope": [
                    "constant-property one-dimensional diffusion equation",
                    "fixed-temperature boundaries",
                    "explicit FTCS numerical stability",
                    "sine-eigenmode analytical numerical validation",
                    "deterministic replay",
                ],
                "excluded_scope": [
                    "empirical measurement",
                    "material calibration",
                    "LPBF melt-pool physics",
                    "phase change",
                    "convection",
                    "radiation",
                    "predictive validation for IN625",
                    "engineering use",
                ],
                "assumptions": [
                    "constant thermal diffusivity",
                    "one-dimensional continuum diffusion",
                ],
                "scientific_status_promoted": False,
            },
            "comparability": {
                "status": "not_assessed",
                "requirements": [
                    "simulation/reference results require a separate declared comparability claim"
                ],
                "limitations": [
                    "numerical agreement with an analytical reference is not empirical validation"
                ],
                "comparison_performed": False,
                "comparable_claimed": False,
            },
            "limitations": [
                "This packet is non-empirical numerical reference evidence only.",
                "The solver is not an LPBF melt-pool model and cannot establish IN625 process-property truth.",
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


def build_characterization_planning_evidence_packet(
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt independently verified L0-L8 maturity into non-empirical planning metadata."""

    assessment_snapshot = _plain_json_snapshot(
        assessment,
        field="characterization_assessment",
    )
    _require(
        isinstance(assessment_snapshot, dict),
        "characterization_assessment root must be an object",
    )
    verified = verify_characterization_evidence_assessment(assessment_snapshot)
    assessment_bytes = canonical_json_bytes(assessment_snapshot)
    subject = verified["subject"]
    _require(isinstance(subject, Mapping), "verified characterization subject is malformed")
    highest_index = verified["highest_supported_index"]
    _require(type(highest_index) is int and -1 <= highest_index <= 8, "verified characterization maturity index drifted")
    highest_level = verified["highest_supported_level"]
    first_blocker = verified["first_blocking_level"]
    declaration_id = verified["declaration_id"]
    _require(isinstance(declaration_id, str) and declaration_id, "verified characterization declaration_id is missing")

    packet = finalize_evidence_packet(
        {
            "schema_version": "1.0",
            "packet_type": "evidence_packet",
            "evidence_id": f"characterization-ladder:{declaration_id}",
            "evidence_kind": "planning_metadata",
            "provider": {
                "provider_id": "characterization-evidence-ladder",
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": CHARACTERIZATION_ADAPTER_ID,
            },
            "subject": {
                "subject_type": "characterization_evidence_maturity",
                "identities": [
                    {
                        "namespace": "target_material_domain",
                        "value": str(subject["target_material_domain"]),
                        "role": "material",
                    },
                    {
                        "namespace": "characterization_modality",
                        "value": str(subject["modality"]),
                        "role": "modality",
                    },
                    {
                        "namespace": "declaration_id",
                        "value": declaration_id,
                        "role": "assessment",
                    },
                ],
                "material_scope": str(subject["target_material_domain"]),
                "description": "Independently replayed characterization L0-L8 readiness metadata; not measurement truth.",
            },
            "contexts": {
                "process": {"status": "not_applicable", "attributes": []},
                "sample": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "source_material_domain",
                            str(subject["source_material_domain"]),
                            source_binding_ids=["characterization-assessment"],
                        ),
                        _attribute(
                            "target_material_domain",
                            str(subject["target_material_domain"]),
                            source_binding_ids=["characterization-assessment"],
                        ),
                    ],
                },
                "method": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "modality",
                            str(subject["modality"]),
                            source_binding_ids=["characterization-assessment"],
                        ),
                        _attribute(
                            "claim_scope",
                            str(subject["claim_scope"]),
                            source_binding_ids=["characterization-assessment"],
                        ),
                    ],
                },
                "measurement": {"status": "not_applicable", "attributes": []},
            },
            "results": [
                {
                    "result_id": "highest-supported-level-index",
                    "result_kind": "characterization_evidence_ladder_highest_supported_index",
                    "value_state": "asserted_reference",
                    "value": highest_index,
                    "value_type": "integer",
                    "unit_state": "not_applicable",
                    "unit": None,
                    "source_binding_ids": ["characterization-assessment"],
                    "derivation_ids": [],
                    "uncertainty_ids": [],
                    "qualifiers": [
                        "planning-metadata-only",
                        f"highest_supported_level={highest_level}",
                        f"first_blocking_level={first_blocker}",
                    ],
                }
            ],
            "uncertainty": [],
            "calibration": {"status": "not_applicable", "records": []},
            "source_bindings": [
                {
                    "binding_id": "characterization-assessment",
                    "role": "independently_verified_characterization_evidence_ladder_assessment",
                    "artifact_id": declaration_id,
                    "locator": (
                        "canonical/characterization_evidence_ladder/"
                        + str(verified["assessment_sha256"])
                        + ".json"
                    ),
                    "sha256": hashlib.sha256(assessment_bytes).hexdigest(),
                    "byte_size": len(assessment_bytes),
                    "media_type": "application/json",
                }
            ],
            "derivation_lineage": [],
            "independence": {
                "source_family_id": None,
                "dataset_parent_id": None,
                "sample_parent_ids": [],
                "acquisition_parent_ids": [],
                "development_family_id": None,
                "overlap_status": "unknown",
                "overlap_with": [],
                "independence_claim_status": "not_assessed",
            },
            "scientific_validity": {
                "domain_verifier_id": "characterization-evidence-bridge-v1",
                "verification_status": "verified",
                "validated_scope": [
                    "assessment/declaration canonical hashes",
                    "monotonic L0-L8 supported prefix",
                    "readiness summary",
                    "declared source-binding digests",
                    "no-promotion policy boundary",
                ],
                "excluded_scope": [
                    "measurement truth",
                    "material-property truth",
                    "instrument-calibration truth beyond the declared maturity level",
                    "comparability",
                    "independence",
                    "downstream scientific use",
                    "engineering readiness unless separately authorized",
                ],
                "assumptions": [],
                "scientific_status_promoted": False,
            },
            "comparability": {
                "status": "not_assessed",
                "requirements": ["planning metadata must not be used as empirical comparison evidence"],
                "limitations": ["L0-L8 maturity is a readiness projection rather than canonical scientific truth"],
                "comparison_performed": False,
                "comparable_claimed": False,
            },
            "limitations": [
                "This packet preserves only independently verified planning metadata.",
                "Producer source-binding digests are retained inside the bound assessment but are not promoted to measurement authority by this adapter.",
            ],
            "authority": {
                "empirical_evidence_created": False,
                "scientific_status_promoted": False,
                "downstream_use_authorized": False,
                "planning_metadata_only": True,
                "row_level_measurement_authority": False,
                "authority_source": "none",
            },
        }
    )
    return packet


__all__ = [
    "CHARACTERIZATION_ADAPTER_ID",
    "EvidencePacketAdapterError",
    "NIST_AMBENCH_ADAPTER_ID",
    "build_characterization_planning_evidence_packet",
    "build_heat_conduction_reference_evidence_packet",
    "build_nist_ambench_trace_evidence_packets",
    "build_nist_ambench_trace_validation_material",
]
