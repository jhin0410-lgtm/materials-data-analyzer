"""Battery source-metadata recovery and evaluator stability audit.

The audit reads only existing local artifacts. It recovers source-supported
metadata, executes predeclared descriptive evaluator policies, and keeps
mechanism fitting, prediction, threshold optimization, and network access out
of scope.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile

import pandas as pd

from .battery_trajectory_evaluator import (
    EVALUATOR_ID,
    FINDING_CATEGORIES,
    CapacityTrajectoryEvaluatorConfig,
    CapacityTrajectoryInput,
    CapacityTrajectoryResult,
    canonical_checksum,
    evaluate_capacity_trajectory,
    load_local_battery_trajectory_inputs,
)


AUDIT_VERSION = "2.3.5"
AUDIT_ID = "battery_source_metadata_recovery_and_stability_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_source_metadata_stability_audit.json"
DEFAULT_OUTPUT_ROOT = "outputs/battery_metadata_stability_v2_3"
EXPECTED_RAW_DISCHARGE_HEADER = (
    "Voltage_measured,Current_measured,Temperature_measured,"
    "Current_load,Voltage_load,Time"
)

TRACKED_OUTPUTS = {
    "source_lineage": "data/processed/battery_v2_3_5_source_lineage_summary.json",
    "metadata_recovery": "data/processed/battery_v2_3_5_metadata_recovery_summary.csv",
    "policy_definitions": "data/processed/battery_v2_3_5_policy_definition_snapshot.csv",
    "policy_stability": "data/processed/battery_v2_3_5_evaluator_stability_summary.csv",
    "event_stability": "data/processed/battery_v2_3_5_event_stability_summary.csv",
    "external_data_decision": "data/processed/battery_v2_3_5_external_data_requirement_decision.json",
    "decision": "data/processed/battery_v2_3_5_decision.json",
    "report": "data/processed/battery_v2_3_5_report_summary.md",
}

LOCAL_OUTPUTS = {
    "cell_lineage": f"{DEFAULT_OUTPUT_ROOT}/lineage/cell_lineage.csv",
    "cycle_metadata": f"{DEFAULT_OUTPUT_ROOT}/metadata/cycle_metadata_recovery.csv",
    "source_audit": f"{DEFAULT_OUTPUT_ROOT}/metadata/source_metadata_audit.json",
    "policy_results": f"{DEFAULT_OUTPUT_ROOT}/stability/policy_results.jsonl",
    "event_clusters": f"{DEFAULT_OUTPUT_ROOT}/stability/consolidated_events.jsonl",
    "report": f"{DEFAULT_OUTPUT_ROOT}/reports/battery_metadata_stability_report.md",
}

STABILITY_STATUSES = (
    "stable_across_policies",
    "stable_with_restrictions",
    "policy_sensitive",
    "insufficient_support",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_is_unsafe(path: str | Path) -> bool:
    normalized = str(path).replace("\\", "/")
    candidate = Path(normalized)
    windows = PureWindowsPath(normalized)
    return (
        candidate.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in candidate.parts
    )


def _resolve_repo_path(repo_root: str | Path, relative_path: str | Path) -> Path:
    if _path_is_unsafe(relative_path):
        raise ValueError("paths must be repository-relative and non-traversing")
    root = Path(repo_root).resolve()
    target = (root / Path(str(relative_path).replace("\\", "/"))).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("path escapes repository root") from None
    return target


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _csv_text(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _json_safe(row.get(column)) for column in columns})
    return stream.getvalue()


def parse_nasa_date_vector(value: Any) -> pd.Timestamp | pd.NaT:
    """Parse a MATLAB-style NASA cycle start-time vector."""
    if value is None or pd.isna(value):
        return pd.NaT
    numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(value))
    if len(numbers) < 6:
        return pd.NaT
    try:
        year, month, day, hour, minute = [int(float(number)) for number in numbers[:5]]
        second = float(numbers[5])
        base = pd.Timestamp(year=year, month=month, day=day, hour=hour, minute=minute)
        return base + pd.to_timedelta(second, unit="s")
    except (ValueError, OverflowError):
        return pd.NaT


@dataclass(frozen=True)
class SensitivityPolicy:
    policy_id: str
    policy_axis: str
    description: str
    overrides: Mapping[str, Any]

    def to_config(self) -> CapacityTrajectoryEvaluatorConfig:
        allowed = {
            "minimum_valid_observations",
            "reference_capacity_policy",
            "reference_window",
            "absolute_detection_floor",
            "robust_scale_multiplier",
            "window_size",
            "minimum_window_support",
            "gap_exclusion_threshold",
            "plateau_threshold",
            "accelerated_fade_threshold",
            "high_variability_scale_threshold",
            "terminal_retention_boundary",
            "numerical_tolerance",
            "maximum_states_per_trajectory",
        }
        unknown = sorted(set(self.overrides) - allowed)
        if unknown:
            raise ValueError(f"unsupported evaluator override(s): {unknown}")
        return replace(CapacityTrajectoryEvaluatorConfig(), **dict(self.overrides))


def load_audit_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != AUDIT_VERSION:
        raise ValueError(f"schema_version must be {AUDIT_VERSION}")
    if payload.get("audit_id") != AUDIT_ID:
        raise ValueError(f"audit_id must be {AUDIT_ID}")
    network = dict(payload.get("network_policy", {}))
    if network != {
        "automatic_download": False,
        "network_access": False,
        "credentials_required": False,
    }:
        raise ValueError("v2.3.5 requires an explicit no-network/no-credential policy")
    credential = dict(payload.get("credential_policy", {}))
    if credential != {
        "store_credentials": False,
        "network_access_required": False,
    }:
        raise ValueError("v2.3.5 credentials must remain disabled and unpersisted")
    recovery = dict(payload.get("recovery_policy", {}))
    if recovery.get("allow_default_fill") is not False or recovery.get("allow_inference") is not False:
        raise ValueError("metadata defaults and inference are prohibited")
    paths: list[str] = []
    for section_name in ("source", "inputs"):
        section = dict(payload.get(section_name, {}))
        paths.extend(str(value) for key, value in section.items() if key.endswith(("_path", "_root", "_summary", "_artifact")))
    paths.append(str(payload.get("output_root", DEFAULT_OUTPUT_ROOT)))
    if any(_path_is_unsafe(path) for path in paths):
        raise ValueError("config paths must be repository-relative and non-traversing")
    archive_member = str(dict(payload.get("source", {})).get("archive_metadata_member", ""))
    if not archive_member or _path_is_unsafe(archive_member):
        raise ValueError("archive_metadata_member must be relative and non-traversing")
    policies = [
        SensitivityPolicy(
            policy_id=str(row["policy_id"]),
            policy_axis=str(row["policy_axis"]),
            description=str(row["description"]),
            overrides=dict(row.get("overrides", {})),
        )
        for row in payload.get("sensitivity_policies", [])
    ]
    _validate_policies(policies)
    return payload


def _validate_policies(policies: Sequence[SensitivityPolicy]) -> None:
    ids = [policy.policy_id for policy in policies]
    if len(ids) != len(set(ids)):
        raise ValueError("sensitivity policy IDs must be unique")
    if not policies or policies[0].policy_id != "baseline_v2_3_4" or policies[0].overrides:
        raise ValueError("the exact v2.3.4 baseline must be the first policy")
    expected_axes = {"baseline", "threshold", "reference", "window", "gap"}
    if {policy.policy_axis for policy in policies} != expected_axes:
        raise ValueError("policies must cover baseline, threshold, reference, window, and gap")
    axis_fields = {
        "baseline": set(),
        "threshold": {
            "absolute_detection_floor",
            "robust_scale_multiplier",
            "plateau_threshold",
            "accelerated_fade_threshold",
            "high_variability_scale_threshold",
        },
        "reference": {"reference_capacity_policy", "reference_window"},
        "window": {"window_size", "minimum_window_support"},
        "gap": {"gap_exclusion_threshold"},
    }
    for policy in policies:
        if not set(policy.overrides).issubset(axis_fields[policy.policy_axis]):
            raise ValueError(f"{policy.policy_id} changes fields outside its declared axis")
        policy.to_config()


def _policies_from_payload(payload: Mapping[str, Any]) -> list[SensitivityPolicy]:
    policies = [
        SensitivityPolicy(
            policy_id=str(row["policy_id"]),
            policy_axis=str(row["policy_axis"]),
            description=str(row["description"]),
            overrides=dict(row.get("overrides", {})),
        )
        for row in payload["sensitivity_policies"]
    ]
    _validate_policies(policies)
    return policies


def _protocol_document_map(protocol_root: Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    for path in sorted(protocol_root.glob("README_*.txt"), key=lambda item: item.name):
        numbers = re.findall(r"\d+", path.stem.removeprefix("README_"))
        checksum = _sha256_file(path)
        for number in numbers:
            cell_id = f"B{int(number):04d}"
            if cell_id in mapping:
                raise ValueError(f"duplicate protocol document mapping for {cell_id}")
            mapping[cell_id] = {
                "protocol_group_id": path.stem.lower(),
                "protocol_document": path.name,
                "protocol_document_sha256": checksum,
            }
    return mapping


def _load_required_csv(path: Path, required: Iterable[str], name: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{name} is missing: {path}")
    table = pd.read_csv(path)
    missing = sorted(set(required) - set(table.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")
    return table


def _join_source_metadata(
    metadata: pd.DataFrame,
    analysis_ready: pd.DataFrame,
    features: pd.DataFrame,
    protocol_map: Mapping[str, Mapping[str, str]],
) -> pd.DataFrame:
    discharge = metadata.loc[metadata["type"].astype(str).str.lower().eq("discharge")].copy()
    discharge = discharge.rename(
        columns={
            "filename": "source_filename",
            "start_time": "source_start_time",
            "ambient_temperature": "source_ambient_temperature_c",
            "Capacity": "source_capacity_ah",
        }
    )
    keys = ["battery_id", "source_filename", "uid", "test_id"]
    for table in (discharge, analysis_ready, features):
        table["battery_id"] = table["battery_id"].astype(str)
        table["source_filename"] = table["source_filename"].astype(str)
        table["uid"] = pd.to_numeric(table["uid"], errors="raise").astype(int)
        table["test_id"] = pd.to_numeric(table["test_id"], errors="raise").astype(int)
    if discharge.duplicated(keys).any() or analysis_ready.duplicated(keys).any() or features.duplicated(keys).any():
        raise ValueError("source metadata join keys must be unique")
    source_columns = keys + [
        "source_start_time",
        "source_ambient_temperature_c",
        "source_capacity_ah",
    ]
    feature_columns = keys + [
        "discharge_duration_s",
        "voltage_mean_v",
        "voltage_min_v",
        "voltage_max_v",
        "current_mean_a",
        "current_min_a",
        "current_max_a",
        "temperature_mean_c",
        "temperature_min_c",
        "temperature_max_c",
        "temperature_rise_c",
        "raw_sample_count",
        "feature_extraction_status",
    ]
    joined = analysis_ready.merge(
        discharge[source_columns], on=keys, how="left", validate="one_to_one", indicator="source_join"
    )
    if not joined["source_join"].eq("both").all():
        raise ValueError("analysis-ready rows do not all map to source metadata")
    joined = joined.drop(columns="source_join").merge(
        features[feature_columns], on=keys, how="left", validate="one_to_one", indicator="feature_join"
    )
    if not joined["feature_join"].eq("both").all():
        raise ValueError("analysis-ready rows do not all map to discharge feature evidence")
    joined = joined.drop(columns="feature_join")
    joined["cycle_start_timestamp"] = joined["source_start_time"].map(parse_nasa_date_vector)
    joined["source_capacity_match"] = (
        pd.to_numeric(joined["discharge_capacity_ah"], errors="coerce")
        - pd.to_numeric(joined["source_capacity_ah"], errors="coerce")
    ).abs().le(1e-12)
    joined["ambient_temperature_match"] = (
        pd.to_numeric(joined["ambient_temperature_c"], errors="coerce")
        - pd.to_numeric(joined["source_ambient_temperature_c"], errors="coerce")
    ).abs().le(1e-12)
    joined["protocol_group_id"] = joined["battery_id"].map(
        {cell: row["protocol_group_id"] for cell, row in protocol_map.items()}
    )
    joined["protocol_document"] = joined["battery_id"].map(
        {cell: row["protocol_document"] for cell, row in protocol_map.items()}
    )
    joined["protocol_document_sha256"] = joined["battery_id"].map(
        {cell: row["protocol_document_sha256"] for cell, row in protocol_map.items()}
    )
    joined = joined.sort_values(["battery_id", "cycle_index"], kind="mergesort").reset_index(drop=True)
    joined["elapsed_seconds_since_first_discharge"] = joined.groupby("battery_id")[
        "cycle_start_timestamp"
    ].transform(lambda series: (series - series.iloc[0]).dt.total_seconds())
    joined["seconds_since_previous_discharge"] = joined.groupby("battery_id")[
        "cycle_start_timestamp"
    ].diff().dt.total_seconds()
    joined["timestamp_timezone_status"] = "timezone_unavailable"
    joined["protocol_evidence_status"] = "source_documented_cell_group"
    joined["source_uncertainty_status"] = "unavailable"
    return joined


def _validate_raw_headers(recovered: pd.DataFrame, raw_root: Path) -> tuple[int, int, dict[str, int]]:
    existing = 0
    expected = 0
    signatures: dict[str, int] = {}
    for filename in recovered["source_filename"].astype(str):
        path = raw_root / filename
        if not path.is_file():
            continue
        existing += 1
        with path.open(encoding="utf-8-sig") as handle:
            header = handle.readline().strip()
        signatures[header] = signatures.get(header, 0) + 1
        if header == EXPECTED_RAW_DISCHARGE_HEADER:
            expected += 1
    return existing, expected, dict(sorted(signatures.items()))


def recover_local_source_metadata(
    payload: Mapping[str, Any], repo_root: str | Path = "."
) -> dict[str, Any]:
    source = dict(payload["source"])
    inputs = dict(payload["inputs"])
    paths = {
        key: _resolve_repo_path(repo_root, value)
        for key, value in {**source, **inputs}.items()
        if key.endswith(("_path", "_root", "_summary", "_artifact"))
    }
    archive = paths["archive_path"]
    metadata_path = paths["metadata_path"]
    if not archive.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("local source archive and metadata.csv are required")
    archive_sha = _sha256_file(archive)
    metadata_sha = _sha256_file(metadata_path)
    if archive_sha != str(source["archive_sha256"]).lower():
        raise ValueError("source archive checksum mismatch")
    if metadata_sha != str(source["metadata_sha256"]).lower():
        raise ValueError("source metadata checksum mismatch")
    archive_metadata_member = str(source["archive_metadata_member"])
    with ZipFile(archive) as package:
        if archive_metadata_member not in package.namelist():
            raise ValueError("source metadata member is missing from the local archive")
        member_digest = hashlib.sha256()
        with package.open(archive_metadata_member) as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                member_digest.update(block)
    archive_metadata_sha = member_digest.hexdigest()
    if archive_metadata_sha != metadata_sha:
        raise ValueError("extracted source metadata does not match the archive member")

    metadata = _load_required_csv(
        metadata_path,
        ["type", "start_time", "ambient_temperature", "battery_id", "test_id", "uid", "filename", "Capacity", "Re", "Rct"],
        "source metadata",
    )
    full_summary = _load_required_csv(
        paths["full_cycle_summary"],
        ["battery_id", "cycle_index", "source_filename", "uid", "test_id"],
        "full cycle summary",
    )
    analysis_ready = _load_required_csv(
        paths["analysis_ready_summary"],
        ["battery_id", "cycle_index", "ambient_temperature_c", "discharge_capacity_ah", "source_filename", "uid", "test_id"],
        "analysis-ready summary",
    )
    features = _load_required_csv(
        paths["discharge_feature_summary"],
        ["battery_id", "cycle_index", "source_filename", "uid", "test_id", "discharge_duration_s", "feature_extraction_status"],
        "discharge feature summary",
    )
    trajectories, trajectory_source_metadata = load_local_battery_trajectory_inputs(repo_root)
    trajectory_cells = {trajectory.cell_id for trajectory in trajectories}
    source_discharge = metadata.loc[
        metadata["type"].astype(str).str.lower().eq("discharge")
    ].copy()
    if len(source_discharge) != len(full_summary):
        raise ValueError("full processed summary row count does not match source discharge metadata")
    source_discharge = source_discharge.rename(columns={"filename": "source_filename"})
    full_source_keys = ["battery_id", "source_filename", "uid", "test_id"]
    for table in (source_discharge, full_summary):
        table["battery_id"] = table["battery_id"].astype(str)
        table["source_filename"] = table["source_filename"].astype(str)
        table["uid"] = pd.to_numeric(table["uid"], errors="raise").astype(int)
        table["test_id"] = pd.to_numeric(table["test_id"], errors="raise").astype(int)
    if source_discharge.duplicated(full_source_keys).any() or full_summary.duplicated(full_source_keys).any():
        raise ValueError("full source lineage keys must be unique")
    source_key_set = set(source_discharge[full_source_keys].itertuples(index=False, name=None))
    full_summary_key_set = set(full_summary[full_source_keys].itertuples(index=False, name=None))
    if source_key_set != full_summary_key_set:
        raise ValueError("full processed summary keys do not exactly match source discharge metadata")
    if len(trajectories) != 34 or len(trajectory_cells) != 34:
        raise ValueError("v2.3.5 expects exactly 34 unique source trajectories")
    if trajectory_cells != set(analysis_ready["battery_id"].astype(str)):
        raise ValueError("trajectory cells and analysis-ready cells do not match")

    protocol_map = _protocol_document_map(paths["protocol_document_root"])
    if set(protocol_map) != trajectory_cells:
        raise ValueError("protocol documents must map exactly to all 34 trajectory cells")
    recovered = _join_source_metadata(metadata, analysis_ready, features, protocol_map)
    if not recovered["source_capacity_match"].all() or not recovered["ambient_temperature_match"].all():
        raise ValueError("processed values do not exactly match source metadata")
    if not recovered["cycle_start_timestamp"].notna().all():
        raise ValueError("source cycle timestamps are not fully parseable")
    if not recovered["feature_extraction_status"].eq("ok").all():
        raise ValueError("discharge feature evidence is incomplete")
    monotonic_cells = int(
        sum(
            group["cycle_start_timestamp"].is_monotonic_increasing
            for _, group in recovered.groupby("battery_id", sort=True)
        )
    )
    raw_existing, raw_expected_header, raw_signatures = _validate_raw_headers(
        recovered, paths["raw_cycle_root"]
    )
    if raw_existing != len(recovered) or raw_expected_header != len(recovered):
        raise ValueError("raw discharge file/header coverage is incomplete")

    impedance = metadata.loc[metadata["type"].astype(str).str.lower().eq("impedance")].copy()
    impedance_cells = set(impedance["battery_id"].astype(str))
    impedance_re = pd.to_numeric(impedance["Re"], errors="coerce")
    impedance_rct = pd.to_numeric(impedance["Rct"], errors="coerce")
    cell_rows: list[dict[str, Any]] = []
    for cell_id, group in recovered.groupby("battery_id", sort=True):
        protocol = protocol_map[cell_id]
        source_group = metadata.loc[metadata["battery_id"].astype(str).eq(cell_id)]
        cell_rows.append(
            {
                "cell_id": cell_id,
                "protocol_group_id": protocol["protocol_group_id"],
                "protocol_document": protocol["protocol_document"],
                "protocol_document_sha256": protocol["protocol_document_sha256"],
                "source_metadata_rows": int(len(source_group)),
                "source_discharge_rows": int(source_group["type"].astype(str).str.lower().eq("discharge").sum()),
                "analysis_ready_rows": int(len(group)),
                "impedance_rows": int(source_group["type"].astype(str).str.lower().eq("impedance").sum()),
                "first_timestamp": group["cycle_start_timestamp"].min().isoformat(),
                "last_timestamp": group["cycle_start_timestamp"].max().isoformat(),
                "timestamp_monotonic": bool(group["cycle_start_timestamp"].is_monotonic_increasing),
                "raw_discharge_files_verified": int(len(group)),
                "lineage_status": "exact_local_lineage_verified",
            }
        )

    summary = {
        "schema_version": AUDIT_VERSION,
        "audit_id": AUDIT_ID,
        "dataset_slug": source["dataset_slug"],
        "immediate_upstream_status": "verified_local_kaggle_package",
        "original_nasa_snapshot_status": "not_verifiable_from_local_package_metadata",
        "archive_path": source["archive_path"],
        "archive_size_bytes": archive.stat().st_size,
        "archive_sha256": archive_sha,
        "archive_metadata_member": archive_metadata_member,
        "archive_metadata_member_sha256": archive_metadata_sha,
        "archive_metadata_matches_extracted": True,
        "metadata_path": source["metadata_path"],
        "metadata_sha256": metadata_sha,
        "metadata_rows": int(len(metadata)),
        "metadata_cell_count": int(metadata["battery_id"].nunique()),
        "full_discharge_rows": int(metadata["type"].astype(str).str.lower().eq("discharge").sum()),
        "full_summary_rows": int(len(full_summary)),
        "full_source_key_match_rows": int(len(full_summary_key_set)),
        "analysis_ready_rows": int(len(recovered)),
        "trajectory_count": int(len(trajectories)),
        "exact_lineage_cell_count": int(len(cell_rows)),
        "exact_source_key_match_rows": int(len(recovered)),
        "protocol_document_count": int(len({row["protocol_document"] for row in cell_rows})),
        "protocol_document_cell_coverage": int(len(protocol_map)),
        "raw_discharge_files_verified": raw_existing,
        "raw_header_verified_rows": raw_expected_header,
        "raw_header_signatures": raw_signatures,
        "timestamp_parseable_rows": int(recovered["cycle_start_timestamp"].notna().sum()),
        "timestamp_monotonic_cells": monotonic_cells,
        "timestamp_timezone_status": "unavailable",
        "ambient_temperature_rows": int(recovered["source_ambient_temperature_c"].notna().sum()),
        "physical_duration_rows": int(recovered["discharge_duration_s"].notna().sum()),
        "measured_temperature_rows": int(recovered["temperature_mean_c"].notna().sum()),
        "measured_current_rows": int(recovered["current_mean_a"].notna().sum()),
        "measured_voltage_rows": int(recovered["voltage_mean_v"].notna().sum()),
        "impedance_rows": int(len(impedance)),
        "impedance_cell_count": int(len(impedance_cells & trajectory_cells)),
        "impedance_re_rows": int(impedance_re.notna().sum()),
        "impedance_rct_rows": int(impedance_rct.notna().sum()),
        "impedance_complete_re_rct_rows": int((impedance_re.notna() & impedance_rct.notna()).sum()),
        "uncertainty_rows": 0,
        "network_called": False,
        "default_fill_performed": False,
        "inference_performed": False,
        "row_level_output_policy": "local_only",
        "source_evidence_checksum": canonical_checksum(cell_rows),
        "pgir_source_checksum_sha256": trajectory_source_metadata["source_checksum_sha256"],
        "pgir_trajectory_checksum_sha256": trajectory_source_metadata["trajectory_checksum_sha256"],
        "pgir_state_checksum_sha256": trajectory_source_metadata["state_checksum_sha256"],
    }
    return {
        "summary": summary,
        "cell_rows": cell_rows,
        "recovered": recovered,
        "trajectories": trajectories,
        "protocol_map": protocol_map,
        "metadata": metadata,
    }


def _metadata_recovery_rows(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    total_rows = int(audit["analysis_ready_rows"])
    total_cells = int(audit["trajectory_count"])
    impedance_rows = int(audit["impedance_rows"])
    complete_impedance_rows = int(audit["impedance_complete_re_rct_rows"])
    rows = [
        ("cell_lineage", "metadata.csv + protocol README + PGIR trajectory", total_cells, total_cells, "recovered_exact", "local_cell_lineage_only", False, "immediate Kaggle package verified; original NASA snapshot version unresolved"),
        ("cycle_start_timestamp", "metadata.csv:start_time", total_rows, total_rows, "recovered_exact", "local_cycle_metadata_only", False, "timezone is unavailable"),
        ("ambient_temperature_c", "metadata.csv:ambient_temperature", total_rows, total_rows, "already_retained_and_verified", "existing PGIR State", False, "ambient condition is not measurement uncertainty"),
        ("physical_cycle_start_axis", "metadata.csv:start_time", total_rows, total_rows, "recovered_exact", "local_cycle_metadata_only", False, "evaluator still reports cycle-index findings"),
        ("discharge_duration_s", "per-cycle CSV:Time via tracked feature summary", total_rows, total_rows, "recovered_exact", "local_cycle_metadata_only", False, "within-cycle duration is not inter-cycle aging time"),
        ("measured_temperature_summary", "per-cycle CSV:Temperature_measured via tracked feature summary", total_rows, total_rows, "recovered_exact", "local_cycle_metadata_only", False, "summary statistics only"),
        ("measured_current_summary", "per-cycle CSV:Current_measured via tracked feature summary", total_rows, total_rows, "recovered_exact", "local_cycle_metadata_only", False, "observed current is not a commanded protocol log"),
        ("measured_voltage_summary", "per-cycle CSV:Voltage_measured via tracked feature summary", total_rows, total_rows, "recovered_exact", "local_cycle_metadata_only", False, "summary statistics only"),
        ("documented_protocol_group", "nine local extra_infos README documents", total_cells, total_cells, "recovered_with_group_granularity", "local_cell_lineage_only", False, "variable-condition groups lack a cycle-specific command log"),
        ("impedance_re_rct", "metadata.csv impedance rows", impedance_rows, complete_impedance_rows, "available_with_missing_values_not_joined", "metadata_audit_only", False, f"{impedance_rows - complete_impedance_rows} rows lack a complete Re/Rct pair; temporal alignment to discharge was not performed"),
        ("measurement_uncertainty", "source package", total_rows, 0, "genuinely_unavailable", "unavailable", True, "zero uncertainty was not assigned"),
        ("official_original_snapshot_version", "local package metadata", 1, 0, "genuinely_unavailable", "unavailable", True, "immediate Kaggle source is known; official NASA snapshot/version is not"),
    ]
    return [
        {
            "metadata_field": field,
            "source_evidence": evidence,
            "expected_records": expected,
            "supported_records": supported,
            "recovery_status": status,
            "integration_status": integration,
            "external_data_required": str(external).lower(),
            "limitation": limitation,
        }
        for field, evidence, expected, supported, status, integration, external, limitation in rows
    ]


def _enrich_trajectory_context(
    trajectories: Sequence[CapacityTrajectoryInput],
    recovered: pd.DataFrame,
) -> list[CapacityTrajectoryInput]:
    enriched: list[CapacityTrajectoryInput] = []
    by_cell = {cell: group.sort_values("cycle_index") for cell, group in recovered.groupby("battery_id")}
    for trajectory in trajectories:
        group = by_cell.get(trajectory.cell_id)
        if group is None or tuple(group["cycle_index"].astype(int)) != trajectory.cycle_indices:
            raise ValueError(f"recovered metadata is not cycle-aligned for {trajectory.cell_id}")
        timestamp_available = bool(group["cycle_start_timestamp"].notna().all())
        physical_time_available = timestamp_available and bool(group["cycle_start_timestamp"].is_monotonic_increasing)
        signatures = tuple(group["protocol_group_id"].astype(str))
        enriched.append(
            replace(
                trajectory,
                protocol_signatures=signatures,
                temperature_context_available=bool(group["source_ambient_temperature_c"].notna().all()),
                timestamp_available=timestamp_available,
                physical_elapsed_time_available=physical_time_available,
                source_uncertainty_status="unavailable",
            )
        )
    return enriched


def run_predeclared_sensitivity(
    trajectories: Sequence[CapacityTrajectoryInput],
    recovered: pd.DataFrame,
    policies: Sequence[SensitivityPolicy],
) -> list[dict[str, Any]]:
    enriched = _enrich_trajectory_context(trajectories, recovered)
    rows: list[dict[str, Any]] = []
    for policy in policies:
        evaluator_config = policy.to_config()
        for trajectory in enriched:
            evaluation_input = trajectory
            alternative_reference = policy.policy_axis == "reference"
            if alternative_reference:
                evaluation_input = replace(trajectory, recorded_reference_capacity=None)
            result = evaluate_capacity_trajectory(evaluation_input, evaluator_config)
            rows.append(
                {
                    "policy_id": policy.policy_id,
                    "policy_axis": policy.policy_axis,
                    "policy_description": policy.description,
                    "alternative_reference_audit": alternative_reference,
                    "source_reference_overwritten": False,
                    "trajectory_id": result.trajectory_id,
                    "cell_id": result.cell_id,
                    "config": evaluator_config.to_dict(),
                    "result": result,
                }
            )
    return rows


def _interval(finding: Mapping[str, Any]) -> tuple[int, int]:
    start = finding.get("start_cycle_index")
    end = finding.get("end_cycle_index")
    if start is None and end is None:
        return (0, 0)
    start_value = int(start if start is not None else end)
    end_value = int(end if end is not None else start)
    return (min(start_value, end_value), max(start_value, end_value))


def consolidate_policy_events(
    policy_results: Sequence[Mapping[str, Any]],
    *,
    baseline_policy_id: str,
    stable_ratio: float,
    restricted_ratio: float,
    minimum_policy_support: int,
    adjacency_cycles: int,
) -> list[dict[str, Any]]:
    eligibility: dict[str, set[str]] = {}
    findings_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in policy_results:
        result: CapacityTrajectoryResult = row["result"]
        if result.eligibility_status.startswith("eligible"):
            eligibility.setdefault(result.trajectory_id, set()).add(str(row["policy_id"]))
        for finding in result.findings:
            payload = finding.to_dict()
            start, end = _interval(payload)
            findings_by_key.setdefault((result.trajectory_id, finding.finding_category), []).append(
                {
                    "start": start,
                    "end": end,
                    "policy_id": str(row["policy_id"]),
                    "policy_axis": str(row["policy_axis"]),
                    "finding_id": finding.finding_id,
                }
            )

    events: list[dict[str, Any]] = []
    for (trajectory_id, category), findings in sorted(findings_by_key.items()):
        ordered = sorted(findings, key=lambda row: (row["start"], row["end"], row["policy_id"], row["finding_id"]))
        clusters: list[list[dict[str, Any]]] = []
        for finding in ordered:
            if not clusters or finding["start"] > max(row["end"] for row in clusters[-1]) + adjacency_cycles:
                clusters.append([finding])
            else:
                clusters[-1].append(finding)
        eligible_policies = eligibility.get(trajectory_id, set())
        for ordinal, cluster in enumerate(clusters, start=1):
            supporting = sorted({row["policy_id"] for row in cluster})
            axes = sorted({row["policy_axis"] for row in cluster})
            ratio = len(supporting) / len(eligible_policies) if eligible_policies else 0.0
            baseline_present = baseline_policy_id in supporting
            if len(eligible_policies) < minimum_policy_support:
                status = "insufficient_support"
            elif baseline_present and ratio >= stable_ratio:
                status = "stable_across_policies"
            elif baseline_present and ratio >= restricted_ratio:
                status = "stable_with_restrictions"
            elif len(supporting) >= 2:
                status = "policy_sensitive"
            else:
                status = "insufficient_support"
            identity = {
                "trajectory_id": trajectory_id,
                "category": category,
                "ordinal": ordinal,
                "start": min(row["start"] for row in cluster),
                "end": max(row["end"] for row in cluster),
            }
            events.append(
                {
                    "schema_version": AUDIT_VERSION,
                    "event_id": f"battery_event_{canonical_checksum(identity)[:16]}",
                    "trajectory_id": trajectory_id,
                    "finding_category": category,
                    "start_cycle_index": identity["start"],
                    "end_cycle_index": identity["end"],
                    "supporting_policy_count": len(supporting),
                    "eligible_policy_count": len(eligible_policies),
                    "policy_support_ratio": ratio,
                    "supporting_policy_ids": supporting,
                    "supporting_policy_axes": axes,
                    "baseline_present": baseline_present,
                    "stability_status": status,
                    "interpretation": "bounded descriptive event cluster; no degradation mechanism is assigned",
                }
            )
    return events


def _policy_definition_rows(policies: Sequence[SensitivityPolicy]) -> list[dict[str, Any]]:
    rows = []
    for policy in policies:
        config = policy.to_config()
        rows.append(
            {
                "policy_id": policy.policy_id,
                "policy_axis": policy.policy_axis,
                "description": policy.description,
                "is_baseline": str(policy.policy_axis == "baseline").lower(),
                "reference_policy": config.reference_capacity_policy,
                "reference_window": config.reference_window,
                "absolute_detection_floor": config.absolute_detection_floor,
                "robust_scale_multiplier": config.robust_scale_multiplier,
                "window_size": config.window_size,
                "minimum_window_support": config.minimum_window_support,
                "gap_exclusion_threshold": config.gap_exclusion_threshold,
                "plateau_threshold": config.plateau_threshold,
                "accelerated_fade_threshold": config.accelerated_fade_threshold,
                "high_variability_scale_threshold": config.high_variability_scale_threshold,
                "post_hoc_optimization_prohibited": "true",
            }
        )
    return rows


def _policy_summary_rows(policy_results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    policy_ids = sorted({str(row["policy_id"]) for row in policy_results})
    for policy_id in policy_ids:
        selected = [row for row in policy_results if row["policy_id"] == policy_id]
        results = [row["result"] for row in selected]
        finding_total = sum(len(result.findings) for result in results)
        category_counts = {
            category: sum(result.finding_counts.get(category, 0) for result in results)
            for category in FINDING_CATEGORIES
        }
        payload = [result.to_dict(include_identity=False) for result in results]
        rows.append(
            {
                "policy_id": policy_id,
                "policy_axis": selected[0]["policy_axis"],
                "requested_trajectories": len(results),
                "evaluated_trajectories": sum(result.eligibility_status.startswith("eligible") for result in results),
                "blocked_trajectories": sum(not result.eligibility_status.startswith("eligible") for result in results),
                "total_findings": finding_total,
                "missing_cycle_gap_findings": category_counts["missing_cycle_gap"],
                "abrupt_drop_findings": category_counts["abrupt_capacity_drop_candidate"],
                "abrupt_rise_findings": category_counts["abrupt_capacity_rise_candidate"],
                "plateau_findings": category_counts["plateau_candidate"],
                "accelerated_fade_findings": category_counts["accelerated_fade_candidate"],
                "decelerated_fade_findings": category_counts["decelerated_fade_candidate"],
                "high_variability_findings": category_counts["high_variability_candidate"],
                "terminal_low_retention_findings": category_counts["terminal_low_retention_observation"],
                "protocol_context_change_findings": category_counts["protocol_context_change_candidate"],
                "result_checksum": canonical_checksum(payload),
                "model_or_solver_executed": "false",
            }
        )
    return rows


def _event_summary_rows(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category in FINDING_CATEGORIES:
        for status in STABILITY_STATUSES:
            selected = [
                event
                for event in events
                if event["finding_category"] == category and event["stability_status"] == status
            ]
            if not selected:
                continue
            ratios = sorted(float(event["policy_support_ratio"]) for event in selected)
            midpoint = len(ratios) // 2
            median = ratios[midpoint] if len(ratios) % 2 else (ratios[midpoint - 1] + ratios[midpoint]) / 2
            rows.append(
                {
                    "finding_category": category,
                    "stability_status": status,
                    "event_count": len(selected),
                    "trajectory_count": len({event["trajectory_id"] for event in selected}),
                    "minimum_policy_support_ratio": min(ratios),
                    "median_policy_support_ratio": median,
                    "maximum_policy_support_ratio": max(ratios),
                    "mechanism_interpretation": "prohibited",
                }
            )
    return rows


def _external_data_decision(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": AUDIT_VERSION,
        "decision_status": "selective_external_source_documentation_required",
        "automatic_download_performed": False,
        "network_called": False,
        "locally_recovered_without_external_data": [
            "exact 34-cell immediate lineage",
            "cycle start timestamps",
            "ambient temperature",
            "discharge duration",
            "measured temperature/current/voltage summaries",
            "cell-group protocol documents",
            "impedance Re/Rct availability",
        ],
        "genuinely_unavailable_from_local_source": [
            "per-measurement uncertainty and calibration uncertainty",
            "official original NASA snapshot/version identifier",
            "cycle-specific commanded protocol logs for variable-condition groups",
        ],
        "preferred_routing": [
            {
                "source": "NASA PCoE",
                "role": "preferred official protocol, source-version, calibration, and uncertainty evidence",
                "automatic_download": False,
            },
            {
                "source": "NIST OAR",
                "role": "dataset discovery and metadata catalog only",
                "automatic_download": False,
            },
            {
                "source": "CALCE",
                "role": "possible external battery source only after a separate comparability audit",
                "automatic_download": False,
            },
            {
                "source": "NREL_API_KEY",
                "role": "not a substitute for cell protocol or measurement uncertainty",
                "applicable": False,
            },
            {
                "source": "NVD_API_KEY",
                "role": "security CVE/CPE only; not battery scientific enrichment",
                "applicable": False,
            },
        ],
        "heterogeneous_dataset_combination_allowed": False,
        "source_lineage_checksum": audit["source_evidence_checksum"],
    }


def _decision(
    audit: Mapping[str, Any],
    policy_rows: Sequence[Mapping[str, Any]],
    event_rows: Sequence[Mapping[str, Any]],
    external: Mapping[str, Any],
) -> dict[str, Any]:
    counts = {status: 0 for status in STABILITY_STATUSES}
    for row in event_rows:
        counts[str(row["stability_status"])] += 1
    status = (
        "descriptive_evaluator_stable_with_policy_restrictions"
        if counts["policy_sensitive"] or counts["insufficient_support"]
        else "descriptive_evaluator_stable_across_predeclared_policies"
    )
    payload = {
        "schema_version": AUDIT_VERSION,
        "audit_id": AUDIT_ID,
        "status": status,
        "source_metadata_recovery_status": "source_metadata_recovered_with_explicit_limitations",
        "exact_lineage_cell_count": audit["exact_lineage_cell_count"],
        "analysis_ready_rows": audit["analysis_ready_rows"],
        "predeclared_policy_count": len(policy_rows),
        "bounded_event_count": len(event_rows),
        "event_stability_counts": counts,
        "external_data_requirement_status": external["decision_status"],
        "baseline_v2_3_4_decision_preserved": True,
        "representative_mechanism": "none",
        "mechanism_fitting_performed": False,
        "prediction_performed": False,
        "threshold_optimization_performed": False,
        "post_hoc_reference_selection_performed": False,
        "network_called": False,
        "allowed_claims": [
            "existing local battery source metadata was audited",
            "source-supported metadata was recovered without default filling",
            "predeclared evaluator sensitivity was measured",
            "overlapping descriptive findings were consolidated into bounded events",
            "finding stability was classified across policies",
        ],
        "prohibited_claims": [
            "degradation mechanism identified",
            "lifetime or RUL predicted",
            "SOH model validated",
            "policy-sensitive finding is a physical transition",
            "source uncertainty is zero",
            "external battery datasets are directly comparable",
            "production decision supported",
        ],
    }
    payload["decision_checksum"] = canonical_checksum(payload)
    return payload


def _tracked_report(
    audit: Mapping[str, Any],
    decision: Mapping[str, Any],
    event_summary: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# Battery v2.3.5 Source Metadata and Stability Summary",
        "",
        f"- Immediate source: `{audit['dataset_slug']}` local package",
        f"- Exact cell lineage: {audit['exact_lineage_cell_count']}/34",
        f"- Analysis-ready source-key matches: {audit['exact_source_key_match_rows']}",
        f"- Parsed cycle timestamps: {audit['timestamp_parseable_rows']}",
        f"- Physical discharge durations: {audit['physical_duration_rows']}",
        f"- Protocol documents: {audit['protocol_document_count']} covering {audit['protocol_document_cell_coverage']} cells",
        f"- Impedance rows: {audit['impedance_rows']} across {audit['impedance_cell_count']} cells; "
        f"complete numeric Re/Rct pairs: {audit['impedance_complete_re_rct_rows']}",
        f"- Source uncertainty rows: {audit['uncertainty_rows']}",
        f"- Stability decision: `{decision['status']}`",
        "",
        "## Event Stability",
        "",
        "| Finding | Status | Events | Trajectories | Median policy support |",
        "|---|---|---:|---:|---:|",
    ]
    for row in event_summary:
        lines.append(
            f"| {row['finding_category']} | {row['stability_status']} | {row['event_count']} | "
            f"{row['trajectory_count']} | {float(row['median_policy_support_ratio']):.3f} |"
        )
    lines.extend(
        [
            "",
            "Thresholds and reference/window/gap variants were predeclared. Results are descriptive candidates, not physical mechanisms. The evaluator still does not fit a mechanism, predict lifetime, or treat source uncertainty as zero.",
            "",
        ]
    )
    return "\n".join(lines)


def preview_battery_metadata_stability(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    payload = load_audit_config(config_path)
    source = dict(payload["source"])
    inputs = dict(payload["inputs"])
    required = {
        key: {
            "path": value,
            "exists": _resolve_repo_path(repo_root, value).is_file()
            if key.endswith(("_path", "_summary", "_artifact"))
            else _resolve_repo_path(repo_root, value).is_dir()
        }
        for key, value in {**source, **inputs}.items()
        if key.endswith(("_path", "_root", "_summary", "_artifact"))
    }
    return {
        "schema_version": AUDIT_VERSION,
        "audit_id": AUDIT_ID,
        "status": "ready_for_local_execution" if all(row["exists"] for row in required.values()) else "blocked_missing_local_source",
        "required_inputs": required,
        "sensitivity_policy_count": len(payload["sensitivity_policies"]),
        "network_called": False,
        "automatic_download": False,
        "model_or_solver_executed": False,
        "expected_local_outputs": LOCAL_OUTPUTS,
        "expected_tracked_outputs": TRACKED_OUTPUTS,
    }


def run_battery_metadata_stability_audit(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
    *,
    write_local: bool = True,
    write_tracked: bool = True,
) -> dict[str, Any]:
    payload = load_audit_config(config_path)
    policies = _policies_from_payload(payload)
    recovery = recover_local_source_metadata(payload, repo_root)
    policy_results = run_predeclared_sensitivity(
        recovery["trajectories"], recovery["recovered"], policies
    )
    classification = dict(payload["stability_classification"])
    events = consolidate_policy_events(
        policy_results,
        baseline_policy_id="baseline_v2_3_4",
        stable_ratio=float(classification["stable_across_policies_min_ratio"]),
        restricted_ratio=float(classification["stable_with_restrictions_min_ratio"]),
        minimum_policy_support=int(classification["minimum_policy_support"]),
        adjacency_cycles=int(classification["overlap_adjacency_cycles"]),
    )
    policy_definitions = _policy_definition_rows(policies)
    policy_summary = _policy_summary_rows(policy_results)
    event_summary = _event_summary_rows(events)
    metadata_summary = _metadata_recovery_rows(recovery["summary"])
    external = _external_data_decision(recovery["summary"])
    decision = _decision(recovery["summary"], policy_summary, events, external)
    report = _tracked_report(recovery["summary"], decision, event_summary)

    root = Path(repo_root).resolve()
    if write_local:
        local_paths = {key: _resolve_repo_path(root, value) for key, value in LOCAL_OUTPUTS.items()}
        cell_columns = list(recovery["cell_rows"][0])
        _atomic_write(local_paths["cell_lineage"], _csv_text(recovery["cell_rows"], cell_columns))
        cycle_columns = [
            "battery_id",
            "cycle_index",
            "source_filename",
            "uid",
            "test_id",
            "cycle_start_timestamp",
            "elapsed_seconds_since_first_discharge",
            "seconds_since_previous_discharge",
            "source_ambient_temperature_c",
            "discharge_duration_s",
            "temperature_mean_c",
            "temperature_min_c",
            "temperature_max_c",
            "temperature_rise_c",
            "current_mean_a",
            "current_min_a",
            "current_max_a",
            "voltage_mean_v",
            "voltage_min_v",
            "voltage_max_v",
            "protocol_group_id",
            "protocol_document",
            "protocol_evidence_status",
            "timestamp_timezone_status",
            "source_uncertainty_status",
        ]
        cycle_rows = recovery["recovered"][cycle_columns].to_dict(orient="records")
        _atomic_write(local_paths["cycle_metadata"], _csv_text(cycle_rows, cycle_columns))
        _atomic_write(local_paths["source_audit"], _canonical_json(recovery["summary"]))
        policy_jsonl = "".join(
            _canonical_json(
                {
                    "schema_version": AUDIT_VERSION,
                    "policy_id": row["policy_id"],
                    "policy_axis": row["policy_axis"],
                    "alternative_reference_audit": row["alternative_reference_audit"],
                    "source_reference_overwritten": False,
                    "result": row["result"].to_dict(include_identity=True, include_findings=True),
                }
            ).replace("\n", "")
            + "\n"
            for row in policy_results
        )
        _atomic_write(local_paths["policy_results"], policy_jsonl)
        event_jsonl = "".join(
            json.dumps(_json_safe(event), sort_keys=True, separators=(",", ":")) + "\n"
            for event in events
        )
        _atomic_write(local_paths["event_clusters"], event_jsonl)
        _atomic_write(local_paths["report"], report)

    if write_tracked:
        tracked_paths = {key: _resolve_repo_path(root, value) for key, value in TRACKED_OUTPUTS.items()}
        _atomic_write(tracked_paths["source_lineage"], _canonical_json(recovery["summary"]))
        _atomic_write(
            tracked_paths["metadata_recovery"],
            _csv_text(metadata_summary, list(metadata_summary[0])),
        )
        _atomic_write(
            tracked_paths["policy_definitions"],
            _csv_text(policy_definitions, list(policy_definitions[0])),
        )
        _atomic_write(
            tracked_paths["policy_stability"],
            _csv_text(policy_summary, list(policy_summary[0])),
        )
        _atomic_write(
            tracked_paths["event_stability"],
            _csv_text(event_summary, list(event_summary[0])),
        )
        _atomic_write(tracked_paths["external_data_decision"], _canonical_json(external))
        _atomic_write(tracked_paths["decision"], _canonical_json(decision))
        _atomic_write(tracked_paths["report"], report)

    return {
        "schema_version": AUDIT_VERSION,
        "audit_id": AUDIT_ID,
        "status": decision["status"],
        "source_lineage": recovery["summary"],
        "metadata_recovery": metadata_summary,
        "policy_summary": policy_summary,
        "event_summary": event_summary,
        "external_data_decision": external,
        "decision": decision,
        "local_outputs": LOCAL_OUTPUTS,
        "tracked_outputs": TRACKED_OUTPUTS,
        "network_called": False,
        "model_or_solver_executed": False,
    }


def load_battery_v2_3_5_summary(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root)
    decision_path = _resolve_repo_path(root, TRACKED_OUTPUTS["decision"])
    lineage_path = _resolve_repo_path(root, TRACKED_OUTPUTS["source_lineage"])
    if not decision_path.is_file() or not lineage_path.is_file():
        return {"schema_version": AUDIT_VERSION, "status": "not_available"}
    return {
        "schema_version": AUDIT_VERSION,
        "status": "available",
        "decision": json.loads(decision_path.read_text(encoding="utf-8")),
        "source_lineage": json.loads(lineage_path.read_text(encoding="utf-8")),
        "tracked_outputs": TRACKED_OUTPUTS,
    }


def validate_battery_v2_3_5_artifacts(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root)
    errors: list[str] = []
    combined = ""
    for name, relative_path in TRACKED_OUTPUTS.items():
        path = _resolve_repo_path(root, relative_path)
        if not path.is_file():
            errors.append(f"missing tracked output: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        combined += text
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON {name}: {exc}")
        elif path.suffix == ".csv":
            reader = csv.reader(io.StringIO(text))
            header = next(reader, [])
            if len(header) != len(set(header)):
                errors.append(f"duplicate CSV header: {name}")
    prohibited_fragments = ["C:/", "C:\\", "battery_trajectory_B", "battery_state_B", "NVD_API_KEY=", "NREL_API_KEY="]
    for fragment in prohibited_fragments:
        if fragment in combined:
            errors.append(f"tracked output contains prohibited fragment: {fragment}")
    return {
        "schema_version": AUDIT_VERSION,
        "status": "valid" if not errors else "invalid",
        "valid": not errors,
        "errors": errors,
        "tracked_output_count": len(TRACKED_OUTPUTS),
    }
