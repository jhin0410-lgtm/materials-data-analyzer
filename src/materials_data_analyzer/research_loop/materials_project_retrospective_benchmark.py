"""Locked retrospective benchmark partitioning for Materials Project Stage 4.

This module creates only the evaluation boundary required by the autonomous
research-loop RFC. It does not select actions, train models, expose locked-test
evidence, or make a materials-discovery claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from platform_core.output_safety import transactional_output_directory

SCHEMA_VERSION = "1.0"
PARTITIONS = ("seed_evidence", "acquisition_pool", "locked_test")
MANIFEST_NAME = "benchmark_manifest.json"


class MaterialsProjectBenchmarkError(ValueError):
    """Raised when the retrospective benchmark contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterialsProjectBenchmarkError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise MaterialsProjectBenchmarkError(
            f"invalid JSON in {resolved}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MaterialsProjectBenchmarkError(f"JSON root must be an object: {resolved}")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterialsProjectBenchmarkError(f"{field} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MaterialsProjectBenchmarkError(f"{field} must be a positive integer")
    return value


def _require_exact_keys(
    value: Any,
    *,
    field: str,
    keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaterialsProjectBenchmarkError(f"{field} must be a JSON object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing:
        raise MaterialsProjectBenchmarkError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise MaterialsProjectBenchmarkError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return value


def _require_unique_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MaterialsProjectBenchmarkError(f"{field} must be a non-empty JSON array")
    normalized = [_require_string(item, f"{field} item") for item in value]
    if len(normalized) != len(set(normalized)):
        raise MaterialsProjectBenchmarkError(f"{field} must not contain duplicates")
    return normalized


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "schema_version",
        "benchmark_id",
        "dataset_version",
        "identifier_column",
        "target_column",
        "partition_group_column",
        "required_disjoint_group_columns",
        "partition_fractions",
        "partition_salt",
        "expected_source",
        "planner_visibility",
        "scientific_boundary",
    }
    config = _require_exact_keys(value, field="benchmark config", keys=keys)
    if config["schema_version"] != SCHEMA_VERSION:
        raise MaterialsProjectBenchmarkError("unsupported benchmark schema_version")

    identifier = _require_string(config["identifier_column"], "identifier_column")
    target = _require_string(config["target_column"], "target_column")
    partition_group = _require_string(
        config["partition_group_column"], "partition_group_column"
    )
    groups = _require_unique_strings(
        config["required_disjoint_group_columns"],
        "required_disjoint_group_columns",
    )
    if partition_group not in groups:
        raise MaterialsProjectBenchmarkError(
            "partition_group_column must be included in required_disjoint_group_columns"
        )
    if len({identifier, target, *groups}) != 2 + len(groups):
        raise MaterialsProjectBenchmarkError(
            "identifier, target, and group columns must be distinct"
        )

    fractions = _require_exact_keys(
        config["partition_fractions"],
        field="partition_fractions",
        keys=set(PARTITIONS),
    )
    normalized_fractions: dict[str, float] = {}
    for name in PARTITIONS:
        raw = fractions[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise MaterialsProjectBenchmarkError(
                f"partition_fractions.{name} must be numeric"
            )
        fraction = float(raw)
        if not math.isfinite(fraction) or fraction <= 0.0 or fraction >= 1.0:
            raise MaterialsProjectBenchmarkError(
                f"partition_fractions.{name} must be between 0 and 1"
            )
        normalized_fractions[name] = fraction
    if not math.isclose(
        sum(normalized_fractions.values()), 1.0, rel_tol=0.0, abs_tol=1e-12
    ):
        raise MaterialsProjectBenchmarkError("partition fractions must sum to 1.0")

    expected = _require_exact_keys(
        config["expected_source"],
        field="expected_source",
        keys={"row_count", "primary_feature_count"},
    )
    visibility = _require_exact_keys(
        config["planner_visibility"],
        field="planner_visibility",
        keys={
            "seed_target_visible",
            "acquisition_target_visible",
            "locked_test_visible",
            "visible_columns",
        },
    )
    if visibility["seed_target_visible"] is not True:
        raise MaterialsProjectBenchmarkError("seed target must be planner-visible")
    if visibility["acquisition_target_visible"] is not False:
        raise MaterialsProjectBenchmarkError("acquisition target must remain oracle-only")
    if visibility["locked_test_visible"] is not False:
        raise MaterialsProjectBenchmarkError("locked test must not be planner-visible")
    _require_string(visibility["visible_columns"], "planner_visibility.visible_columns")
    boundary = _require_unique_strings(config["scientific_boundary"], "scientific_boundary")

    return {
        **config,
        "benchmark_id": _require_string(config["benchmark_id"], "benchmark_id"),
        "dataset_version": _require_string(config["dataset_version"], "dataset_version"),
        "identifier_column": identifier,
        "target_column": target,
        "partition_group_column": partition_group,
        "required_disjoint_group_columns": groups,
        "partition_fractions": normalized_fractions,
        "partition_salt": _require_string(config["partition_salt"], "partition_salt"),
        "expected_source": {
            "row_count": _require_positive_int(expected["row_count"], "expected_source.row_count"),
            "primary_feature_count": _require_positive_int(
                expected["primary_feature_count"],
                "expected_source.primary_feature_count",
            ),
        },
        "scientific_boundary": boundary,
    }


def _primary_features(inventory: pd.DataFrame, expected_count: int) -> list[str]:
    required = {"column_name", "primary_feature"}
    missing = sorted(required - set(inventory.columns))
    if missing:
        raise MaterialsProjectBenchmarkError(
            "descriptor inventory missing columns: " + ", ".join(missing)
        )
    mask = inventory["primary_feature"].astype(str).str.strip().str.lower().eq("true")
    features = [str(value).strip() for value in inventory.loc[mask, "column_name"]]
    if any(not value for value in features):
        raise MaterialsProjectBenchmarkError("primary feature names must not be blank")
    if len(features) != len(set(features)):
        raise MaterialsProjectBenchmarkError("primary feature names must be unique")
    if len(features) != expected_count:
        raise MaterialsProjectBenchmarkError(
            f"expected {expected_count} primary features but found {len(features)}"
        )
    return features


def _validate_source(
    frame: pd.DataFrame,
    config: dict[str, Any],
    features: list[str],
) -> pd.DataFrame:
    if len(frame) != config["expected_source"]["row_count"]:
        raise MaterialsProjectBenchmarkError(
            "source row count does not match the locked benchmark contract"
        )

    identifier = config["identifier_column"]
    target = config["target_column"]
    groups = config["required_disjoint_group_columns"]
    required = [identifier, target, *groups, *features]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise MaterialsProjectBenchmarkError(
            "analysis-ready source missing columns: " + ", ".join(missing)
        )
    forbidden_primary = sorted({identifier, target, *groups}.intersection(features))
    if forbidden_primary:
        raise MaterialsProjectBenchmarkError(
            "identifier/target/group column marked as primary feature: "
            + ", ".join(forbidden_primary)
        )

    identifiers = frame[identifier].astype(str).str.strip()
    if identifiers.eq("").any():
        raise MaterialsProjectBenchmarkError("material identifiers must not be blank")
    if identifiers.duplicated().any():
        raise MaterialsProjectBenchmarkError("material identifiers must be unique")

    for group_column in groups:
        values = frame[group_column].astype(str).str.strip()
        if values.eq("").any():
            raise MaterialsProjectBenchmarkError(
                f"group column contains blank values: {group_column}"
            )

    target_values = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)
    if not bool(np.all(np.isfinite(target_values))):
        raise MaterialsProjectBenchmarkError("target must contain only finite numeric values")

    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce").to_numpy(dtype=float)
        if not bool(np.all(np.isfinite(values))):
            raise MaterialsProjectBenchmarkError(
                f"primary feature must contain only finite numeric values: {feature}"
            )

    if frame[config["partition_group_column"]].astype(str).nunique() < 3:
        raise MaterialsProjectBenchmarkError(
            "at least three partition groups are required for seed/acquisition/locked partitions"
        )
    return frame.copy()


def _stable_hash(salt: str, value: str) -> str:
    return hashlib.sha256(f"{salt}\0{value}".encode("utf-8")).hexdigest()


def _group_partition_map(
    frame: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, str]:
    """Assign whole groups without reading the target column."""
    group_column = config["partition_group_column"]
    salt = config["partition_salt"]
    sizes = frame[group_column].astype(str).value_counts(sort=False).to_dict()
    records = sorted(
        ((str(group), int(size)) for group, size in sizes.items()),
        key=lambda item: (-item[1], _stable_hash(salt, item[0]), item[0]),
    )
    targets = {
        name: len(frame) * float(config["partition_fractions"][name])
        for name in PARTITIONS
    }
    counts = {name: 0 for name in PARTITIONS}
    assignment: dict[str, str] = {}

    for group, size in records:
        scored: list[tuple[tuple[float, ...], str]] = []
        for order, name in enumerate(PARTITIONS):
            target = targets[name]
            current = counts[name]
            projected = current + size
            overflow = max(0.0, projected - target)
            score = (
                1.0 if overflow > 0.0 else 0.0,
                overflow / target,
                current / target,
                float(order),
            )
            scored.append((score, name))
        selected = min(scored, key=lambda item: item[0])[1]
        assignment[group] = selected
        counts[selected] += size

    if any(counts[name] == 0 for name in PARTITIONS):
        raise MaterialsProjectBenchmarkError(
            "deterministic group assignment produced an empty benchmark partition"
        )
    return assignment


def _membership(
    frame: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    identifier = config["identifier_column"]
    groups = config["required_disjoint_group_columns"]
    partition_group = config["partition_group_column"]
    assignment = _group_partition_map(frame, config)
    membership = frame[[identifier, *groups]].copy()
    membership["benchmark_partition"] = (
        frame[partition_group].astype(str).map(assignment)
    )
    if membership["benchmark_partition"].isna().any():
        raise MaterialsProjectBenchmarkError("failed to assign all rows to a partition")
    return membership.sort_values(identifier, kind="mergesort").reset_index(drop=True)


def _assert_disjoint_groups(
    membership: pd.DataFrame,
    group_columns: list[str],
) -> None:
    for column in group_columns:
        counts = membership.groupby(column, dropna=False)["benchmark_partition"].nunique()
        if bool((counts > 1).any()):
            raise MaterialsProjectBenchmarkError(
                f"group leakage across benchmark partitions: {column}"
            )


def _selected_rows(
    frame: pd.DataFrame,
    membership: pd.DataFrame,
    config: dict[str, Any],
    features: list[str],
) -> dict[str, pd.DataFrame]:
    identifier = config["identifier_column"]
    target = config["target_column"]
    groups = config["required_disjoint_group_columns"]
    visible_columns = list(dict.fromkeys([identifier, *groups, *features]))
    by_id = membership.set_index(identifier)["benchmark_partition"]
    partition_for_row = frame[identifier].map(by_id)
    if partition_for_row.isna().any():
        raise MaterialsProjectBenchmarkError("partition membership does not cover source rows")

    result: dict[str, pd.DataFrame] = {}
    for name in PARTITIONS:
        mask = partition_for_row.eq(name)
        subset = frame.loc[mask]
        if name == "seed_evidence":
            output = subset[[*visible_columns, target]].copy()
        elif name == "acquisition_pool":
            output = subset[visible_columns].copy()
        else:
            output = subset[[*visible_columns, target]].copy()
        result[name] = output.sort_values(identifier, kind="mergesort").reset_index(drop=True)

    acquisition_ids = result["acquisition_pool"][[identifier]].copy()
    source_target = frame.set_index(identifier)[target]
    acquisition_ids[target] = acquisition_ids[identifier].map(source_target)
    result["acquisition_labels"] = acquisition_ids
    return result


def _csv_text(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _partition_stats(
    membership: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    total = len(membership)
    for name in PARTITIONS:
        part = membership[membership["benchmark_partition"].eq(name)]
        result[name] = {
            "rows": int(len(part)),
            "row_fraction": float(len(part) / total),
            "partition_group_count": int(part[config["partition_group_column"]].nunique()),
            "requested_row_fraction": float(config["partition_fractions"][name]),
        }
    return result


def build_materials_project_retrospective_benchmark(
    *,
    input_path: str | Path,
    inventory_path: str | Path,
    config_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build a target-blind, group-disjoint Stage 4 benchmark partition."""
    source_path = Path(input_path).expanduser().resolve(strict=True)
    inventory_resolved = Path(inventory_path).expanduser().resolve(strict=True)
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    inventory = pd.read_csv(inventory_resolved)
    features = _primary_features(
        inventory, config["expected_source"]["primary_feature_count"]
    )
    source = _validate_source(pd.read_csv(source_path), config, features)
    membership = _membership(source, config)
    _assert_disjoint_groups(membership, config["required_disjoint_group_columns"])
    partitions = _selected_rows(source, membership, config, features)

    target = config["target_column"]
    identifier = config["identifier_column"]
    if target in partitions["acquisition_pool"].columns:
        raise MaterialsProjectBenchmarkError("acquisition target leaked into planner catalog")
    if list(partitions["acquisition_labels"].columns) != [identifier, target]:
        raise MaterialsProjectBenchmarkError("oracle acquisition labels have unexpected columns")

    output_paths = {
        "seed_evidence": "planner/seed_evidence.csv",
        "acquisition_catalog": "planner/acquisition_catalog.csv",
        "acquisition_labels": "oracle/acquisition_labels.csv",
        "partition_membership": "oracle/partition_membership.csv",
        "locked_test": "locked/locked_test.csv",
    }
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(source_path, inventory_resolved, config_resolved),
        recognized_markers=(MANIFEST_NAME,),
    ) as staging:
        frames = {
            "seed_evidence": partitions["seed_evidence"],
            "acquisition_catalog": partitions["acquisition_pool"],
            "acquisition_labels": partitions["acquisition_labels"],
            "partition_membership": membership,
            "locked_test": partitions["locked_test"],
        }
        for key, relative in output_paths.items():
            _write_text(staging / relative, _csv_text(frames[key]))

        output_sha256 = {
            key: _sha256_file(staging / relative)
            for key, relative in output_paths.items()
        }
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "benchmark_id": config["benchmark_id"],
            "dataset_version": config["dataset_version"],
            "execution_status": "partition_locked",
            "scientific_evidence_created": False,
            "source": {
                "filename": source_path.name,
                "sha256": _sha256_file(source_path),
                "row_count": int(len(source)),
            },
            "descriptor_inventory": {
                "filename": inventory_resolved.name,
                "sha256": _sha256_file(inventory_resolved),
                "primary_feature_count": int(len(features)),
            },
            "benchmark_config": {
                "filename": config_resolved.name,
                "sha256": _sha256_file(config_resolved),
            },
            "software": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "numpy": np.__version__,
            },
            "partition_method": {
                "name": "target_blind_whole_group_greedy_v1",
                "partition_group_column": config["partition_group_column"],
                "required_disjoint_group_columns": config["required_disjoint_group_columns"],
                "salt": config["partition_salt"],
                "target_used_for_assignment": False,
            },
            "partitions": _partition_stats(membership, config),
            "planner_access_policy": {
                "planner_directory": "planner/",
                "seed_target_visible": True,
                "acquisition_target_visible": False,
                "acquisition_labels_directory": "oracle/",
                "locked_test_directory": "locked/",
                "locked_test_visible": False,
            },
            "leakage_checks": {
                "identifier_overlap_across_partitions": False,
                "required_group_overlap_across_partitions": False,
                "acquisition_catalog_contains_target": False,
                "locked_test_exposed_in_planner_directory": False,
                "target_used_for_partition_assignment": False,
            },
            "outputs": output_paths,
            "output_sha256": output_sha256,
            "scientific_boundary": config["scientific_boundary"],
            "next_stage": (
                "Implement costed acquisition actions and sequence evaluation without "
                "changing this locked partition or exposing locked-test evidence."
            ),
        }
        _write_text(
            staging / MANIFEST_NAME,
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    return manifest


def _assert_csv_matches(path: Path, expected: pd.DataFrame, label: str) -> None:
    actual_text = path.read_text(encoding="utf-8")
    expected_text = _csv_text(expected)
    if actual_text != expected_text:
        raise MaterialsProjectBenchmarkError(
            f"benchmark output no longer matches source-derived {label}: {path}"
        )


def verify_materials_project_retrospective_benchmark(
    *,
    benchmark_dir: str | Path,
    input_path: str | Path,
    inventory_path: str | Path,
    config_path: str | Path,
) -> dict[str, Any]:
    """Independently recompute partition membership and verify all locked outputs."""
    root = Path(benchmark_dir).expanduser().resolve(strict=True)
    manifest = _load_json(root / MANIFEST_NAME)
    source_path = Path(input_path).expanduser().resolve(strict=True)
    inventory_resolved = Path(inventory_path).expanduser().resolve(strict=True)
    config_resolved = Path(config_path).expanduser().resolve(strict=True)

    config = _validate_config(_load_json(config_resolved))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise MaterialsProjectBenchmarkError("unsupported benchmark manifest schema_version")
    if manifest.get("benchmark_id") != config["benchmark_id"]:
        raise MaterialsProjectBenchmarkError("benchmark manifest/config id mismatch")
    expected_bindings = {
        "source": _sha256_file(source_path),
        "descriptor_inventory": _sha256_file(inventory_resolved),
        "benchmark_config": _sha256_file(config_resolved),
    }
    for field, digest in expected_bindings.items():
        record = manifest.get(field)
        if not isinstance(record, dict) or record.get("sha256") != digest:
            raise MaterialsProjectBenchmarkError(
                f"benchmark manifest checksum binding mismatch: {field}"
            )

    inventory = pd.read_csv(inventory_resolved)
    features = _primary_features(
        inventory, config["expected_source"]["primary_feature_count"]
    )
    source = _validate_source(pd.read_csv(source_path), config, features)
    membership = _membership(source, config)
    _assert_disjoint_groups(membership, config["required_disjoint_group_columns"])
    partitions = _selected_rows(source, membership, config, features)

    outputs = manifest.get("outputs")
    checksums = manifest.get("output_sha256")
    if not isinstance(outputs, dict) or not isinstance(checksums, dict):
        raise MaterialsProjectBenchmarkError("benchmark manifest outputs are invalid")
    expected_frames = {
        "seed_evidence": partitions["seed_evidence"],
        "acquisition_catalog": partitions["acquisition_pool"],
        "acquisition_labels": partitions["acquisition_labels"],
        "partition_membership": membership,
        "locked_test": partitions["locked_test"],
    }
    for key, expected in expected_frames.items():
        relative = outputs.get(key)
        if not isinstance(relative, str) or not relative:
            raise MaterialsProjectBenchmarkError(f"missing output path in manifest: {key}")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise MaterialsProjectBenchmarkError(f"unsafe output path in manifest: {key}")
        path = root / candidate
        if not path.is_file():
            raise MaterialsProjectBenchmarkError(f"missing benchmark output: {path}")
        if checksums.get(key) != _sha256_file(path):
            raise MaterialsProjectBenchmarkError(f"benchmark output checksum mismatch: {key}")
        _assert_csv_matches(path, expected, key)

    target = config["target_column"]
    acquisition_catalog = pd.read_csv(root / outputs["acquisition_catalog"])
    if target in acquisition_catalog.columns:
        raise MaterialsProjectBenchmarkError("acquisition target is planner-visible")
    locked_relative = Path(outputs["locked_test"])
    if not locked_relative.parts or locked_relative.parts[0] == "planner":
        raise MaterialsProjectBenchmarkError("locked test is exposed in planner directory")

    return {
        "valid": True,
        "benchmark_id": config["benchmark_id"],
        "execution_status": manifest.get("execution_status"),
        "source_sha256": expected_bindings["source"],
        "partition_rows": {
            name: int((membership["benchmark_partition"] == name).sum())
            for name in PARTITIONS
        },
        "target_blind_partition_recomputed": True,
        "required_group_disjointness_verified": True,
        "locked_test_not_planner_visible": True,
        "scientific_evidence_created": False,
    }
