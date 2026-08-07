"""Costed retrospective acquisition sequences for the Materials Project Stage 4 benchmark.

Sequence execution is planner-side: it may read seed labels and planner-visible
acquisition descriptors, and may request labels from the simulated oracle only
after a chemical-system group has been selected. It never reads locked-test
content. Locked evaluation is a separate function that runs only after a sequence
has completed.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from platform_core.output_safety import transactional_output_directory


SEQUENCE_MANIFEST = "sequence_manifest.json"
EVALUATION_MANIFEST = "evaluation_manifest.json"
SEQUENCE_SCHEMA_VERSION = "1.0"
EVALUATION_SCHEMA_VERSION = "1.0"
_ALLOWED_STRATEGIES = ("fixed_catalog", "random", "diversity", "uncertainty")
_ALLOWED_MODELS = (
    "dummy_median",
    "ridge_raw",
    "ridge_log1p",
    "histogram_gradient_boosting_raw",
    "histogram_gradient_boosting_log1p",
)


class MaterialsProjectAcquisitionError(ValueError):
    """Raised when a retrospective acquisition contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterialsProjectAcquisitionError(
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
        raise MaterialsProjectAcquisitionError(
            f"invalid JSON in {resolved}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MaterialsProjectAcquisitionError(f"JSON root must be an object: {resolved}")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _csv_text(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n")


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterialsProjectAcquisitionError(f"{field} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MaterialsProjectAcquisitionError(f"{field} must be a positive integer")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise MaterialsProjectAcquisitionError(f"{field} must be boolean")
    return value


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MaterialsProjectAcquisitionError(f"{field} must be a non-empty list")
    normalized = [_require_nonempty_string(item, f"{field} item") for item in value]
    if len(normalized) != len(set(normalized)):
        raise MaterialsProjectAcquisitionError(f"{field} must not contain duplicates")
    return normalized


def _validate_acquisition_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "benchmark_id",
        "sequence_version",
        "selection_unit",
        "cost_definition",
        "max_label_cost",
        "random_seed",
        "strategies",
        "primary_evaluation_model",
        "evaluation_models",
        "acquisition_policy",
        "strategy_contracts",
        "scientific_boundary",
    }
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing or unknown:
        raise MaterialsProjectAcquisitionError(
            f"invalid acquisition config keys: missing={missing}, unknown={unknown}"
        )
    if value["schema_version"] != SEQUENCE_SCHEMA_VERSION:
        raise MaterialsProjectAcquisitionError("unsupported acquisition config schema_version")
    strategies = _require_string_list(value["strategies"], "strategies")
    if tuple(strategies) != _ALLOWED_STRATEGIES:
        raise MaterialsProjectAcquisitionError(
            "strategies must match the predeclared Stage 4 strategy inventory"
        )
    evaluation_models = _require_string_list(value["evaluation_models"], "evaluation_models")
    if tuple(evaluation_models) != _ALLOWED_MODELS:
        raise MaterialsProjectAcquisitionError(
            "evaluation_models must match the fixed model inventory"
        )
    primary = _require_nonempty_string(
        value["primary_evaluation_model"], "primary_evaluation_model"
    )
    if primary not in evaluation_models:
        raise MaterialsProjectAcquisitionError(
            "primary_evaluation_model must be in evaluation_models"
        )
    policy = value["acquisition_policy"]
    if not isinstance(policy, dict):
        raise MaterialsProjectAcquisitionError("acquisition_policy must be an object")
    policy_keys = {
        "whole_group_only",
        "target_visible_before_selection",
        "locked_test_visible_before_sequence_completion",
        "allow_budget_overshoot",
        "stop_when_no_remaining_group_fits_budget",
    }
    if set(policy) != policy_keys:
        raise MaterialsProjectAcquisitionError("acquisition_policy keys do not match contract")
    if not _require_bool(policy["whole_group_only"], "whole_group_only"):
        raise MaterialsProjectAcquisitionError("whole-group acquisition is required")
    if _require_bool(policy["target_visible_before_selection"], "target_visible_before_selection"):
        raise MaterialsProjectAcquisitionError("target must remain hidden before selection")
    if _require_bool(
        policy["locked_test_visible_before_sequence_completion"],
        "locked_test_visible_before_sequence_completion",
    ):
        raise MaterialsProjectAcquisitionError("locked test must remain hidden during sequence")
    if _require_bool(policy["allow_budget_overshoot"], "allow_budget_overshoot"):
        raise MaterialsProjectAcquisitionError("budget overshoot is prohibited")
    if not _require_bool(
        policy["stop_when_no_remaining_group_fits_budget"],
        "stop_when_no_remaining_group_fits_budget",
    ):
        raise MaterialsProjectAcquisitionError("fail-closed budget stop is required")
    strategy_contracts = value["strategy_contracts"]
    if not isinstance(strategy_contracts, dict) or set(strategy_contracts) != set(strategies):
        raise MaterialsProjectAcquisitionError("strategy_contracts must cover every strategy exactly")
    for strategy, text in strategy_contracts.items():
        _require_nonempty_string(text, f"strategy_contracts.{strategy}")
    boundary = _require_string_list(value["scientific_boundary"], "scientific_boundary")
    random_seed = value["random_seed"]
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise MaterialsProjectAcquisitionError("random_seed must be an integer")
    return {
        **value,
        "benchmark_id": _require_nonempty_string(value["benchmark_id"], "benchmark_id"),
        "sequence_version": _require_nonempty_string(value["sequence_version"], "sequence_version"),
        "selection_unit": _require_nonempty_string(value["selection_unit"], "selection_unit"),
        "cost_definition": _require_nonempty_string(value["cost_definition"], "cost_definition"),
        "max_label_cost": _require_positive_int(value["max_label_cost"], "max_label_cost"),
        "random_seed": random_seed,
        "strategies": strategies,
        "primary_evaluation_model": primary,
        "evaluation_models": evaluation_models,
        "scientific_boundary": boundary,
    }


def _validate_instance_receipt(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "benchmark_id",
        "dataset_version",
        "source",
        "descriptor_inventory",
        "benchmark_config",
        "partitions",
        "output_sha256",
        "verified_execution",
        "scientific_boundary",
    }
    if set(value) != required:
        raise MaterialsProjectAcquisitionError("benchmark instance receipt keys do not match contract")
    if value["schema_version"] != "1.0":
        raise MaterialsProjectAcquisitionError("unsupported benchmark instance schema_version")
    for field in ("source", "descriptor_inventory", "benchmark_config"):
        record = value[field]
        if not isinstance(record, dict) or not isinstance(record.get("sha256"), str):
            raise MaterialsProjectAcquisitionError(f"invalid instance binding: {field}")
    outputs = value["output_sha256"]
    required_outputs = {
        "seed_evidence",
        "acquisition_catalog",
        "acquisition_labels",
        "partition_membership",
        "locked_test",
    }
    if not isinstance(outputs, dict) or set(outputs) != required_outputs:
        raise MaterialsProjectAcquisitionError("instance output_sha256 inventory is invalid")
    for key, digest in outputs.items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise MaterialsProjectAcquisitionError(f"invalid instance output SHA-256: {key}")
    return value


def _benchmark_paths(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise MaterialsProjectAcquisitionError("benchmark manifest outputs are invalid")
    result: dict[str, Path] = {}
    for key in (
        "seed_evidence",
        "acquisition_catalog",
        "acquisition_labels",
        "partition_membership",
        "locked_test",
    ):
        relative = outputs.get(key)
        if not isinstance(relative, str) or not relative:
            raise MaterialsProjectAcquisitionError(f"missing benchmark output path: {key}")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise MaterialsProjectAcquisitionError(f"unsafe benchmark output path: {key}")
        result[key] = root / candidate
    return result


def _validate_benchmark_binding(
    *,
    benchmark_dir: str | Path,
    instance_path: str | Path,
    benchmark_config_path: str | Path,
    acquisition_config_path: str | Path,
    include_locked_bytes: bool,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    root = Path(benchmark_dir).expanduser().resolve(strict=True)
    instance_resolved = Path(instance_path).expanduser().resolve(strict=True)
    benchmark_config_resolved = Path(benchmark_config_path).expanduser().resolve(strict=True)
    acquisition_config_resolved = Path(acquisition_config_path).expanduser().resolve(strict=True)
    manifest = _load_json(root / "benchmark_manifest.json")
    instance = _validate_instance_receipt(_load_json(instance_resolved))
    benchmark_config = _load_json(benchmark_config_resolved)
    acquisition_config = _validate_acquisition_config(_load_json(acquisition_config_resolved))

    benchmark_id = manifest.get("benchmark_id")
    if benchmark_id != instance["benchmark_id"] or benchmark_id != acquisition_config["benchmark_id"]:
        raise MaterialsProjectAcquisitionError("benchmark id mismatch across manifest, receipt, and acquisition config")
    if benchmark_config.get("benchmark_id") != benchmark_id:
        raise MaterialsProjectAcquisitionError("benchmark config id mismatch")
    if _sha256_file(benchmark_config_resolved) != instance["benchmark_config"]["sha256"]:
        raise MaterialsProjectAcquisitionError("benchmark config SHA-256 differs from pinned instance")

    for field in ("source", "descriptor_inventory", "benchmark_config"):
        manifest_record = manifest.get(field)
        receipt_record = instance[field]
        if not isinstance(manifest_record, dict) or manifest_record.get("sha256") != receipt_record["sha256"]:
            raise MaterialsProjectAcquisitionError(f"benchmark manifest differs from pinned {field}")

    paths = _benchmark_paths(root, manifest)
    manifest_hashes = manifest.get("output_sha256")
    if not isinstance(manifest_hashes, dict):
        raise MaterialsProjectAcquisitionError("benchmark manifest output hashes are invalid")
    for key, expected in instance["output_sha256"].items():
        if manifest_hashes.get(key) != expected:
            raise MaterialsProjectAcquisitionError(f"benchmark manifest output hash drift: {key}")
        if key == "locked_test" and not include_locked_bytes:
            continue
        path = paths[key]
        if not path.is_file() or _sha256_file(path) != expected:
            raise MaterialsProjectAcquisitionError(f"benchmark output bytes differ from pinned instance: {key}")

    manifest_partitions = manifest.get("partitions")
    if not isinstance(manifest_partitions, dict):
        raise MaterialsProjectAcquisitionError("benchmark manifest partitions are invalid")
    for name, receipt_partition in instance["partitions"].items():
        manifest_partition = manifest_partitions.get(name)
        if not isinstance(manifest_partition, dict):
            raise MaterialsProjectAcquisitionError(f"missing benchmark partition: {name}")
        for key in ("rows", "partition_group_count"):
            if manifest_partition.get(key) != receipt_partition.get(key):
                raise MaterialsProjectAcquisitionError(f"pinned partition count drift: {name}.{key}")

    return (
        root,
        manifest,
        instance,
        benchmark_config,
        acquisition_config,
        paths,
    )


def _feature_columns(
    catalog: pd.DataFrame,
    benchmark_config: dict[str, Any],
    expected_count: int,
) -> list[str]:
    identifier = _require_nonempty_string(benchmark_config.get("identifier_column"), "identifier_column")
    target = _require_nonempty_string(benchmark_config.get("target_column"), "target_column")
    groups = _require_string_list(
        benchmark_config.get("required_disjoint_group_columns"),
        "required_disjoint_group_columns",
    )
    reserved = {identifier, target, *groups}
    features = [column for column in catalog.columns if column not in reserved]
    if len(features) != expected_count:
        raise MaterialsProjectAcquisitionError(
            f"planner catalog exposes {len(features)} features; expected {expected_count}"
        )
    if len(features) != len(set(features)):
        raise MaterialsProjectAcquisitionError("planner catalog feature columns must be unique")
    return features


def _numeric_frame(frame: pd.DataFrame, columns: list[str], *, label: str) -> pd.DataFrame:
    converted = frame[columns].apply(pd.to_numeric, errors="coerce")
    values = converted.to_numpy(dtype=float)
    if not bool(np.all(np.isfinite(values) | np.isnan(values))):
        raise MaterialsProjectAcquisitionError(f"{label} contains non-finite feature values")
    return converted


def _validate_planner_inputs(
    seed: pd.DataFrame,
    catalog: pd.DataFrame,
    benchmark_config: dict[str, Any],
    instance: dict[str, Any],
) -> tuple[str, str, list[str], list[str]]:
    identifier = _require_nonempty_string(benchmark_config.get("identifier_column"), "identifier_column")
    target = _require_nonempty_string(benchmark_config.get("target_column"), "target_column")
    groups = _require_string_list(
        benchmark_config.get("required_disjoint_group_columns"),
        "required_disjoint_group_columns",
    )
    features = _feature_columns(
        catalog,
        benchmark_config,
        int(instance["descriptor_inventory"]["primary_feature_count"]),
    )
    required_catalog = [identifier, *groups, *features]
    if list(catalog.columns) != required_catalog:
        raise MaterialsProjectAcquisitionError("planner acquisition catalog column order drifted")
    required_seed = [*required_catalog, target]
    if list(seed.columns) != required_seed:
        raise MaterialsProjectAcquisitionError("seed evidence column order drifted")
    if target in catalog.columns:
        raise MaterialsProjectAcquisitionError("acquisition target leaked into planner catalog")
    if seed[identifier].isna().any() or catalog[identifier].isna().any():
        raise MaterialsProjectAcquisitionError("planner identifiers must not be missing")
    if seed[identifier].astype(str).duplicated().any() or catalog[identifier].astype(str).duplicated().any():
        raise MaterialsProjectAcquisitionError("planner identifiers must be unique within each partition")
    if set(seed[identifier].astype(str)).intersection(set(catalog[identifier].astype(str))):
        raise MaterialsProjectAcquisitionError("seed and acquisition identifiers overlap")
    selection_unit = _require_nonempty_string(benchmark_config.get("partition_group_column"), "partition_group_column")
    if selection_unit not in groups:
        raise MaterialsProjectAcquisitionError("selection unit is not a required disjoint group")
    for column in groups:
        if seed[column].isna().any() or catalog[column].isna().any():
            raise MaterialsProjectAcquisitionError(f"group metadata are missing: {column}")
    target_values = pd.to_numeric(seed[target], errors="coerce").to_numpy(dtype=float)
    if not bool(np.all(np.isfinite(target_values))) or bool(np.any(target_values < 0)):
        raise MaterialsProjectAcquisitionError("seed target must be finite and nonnegative")
    _numeric_frame(seed, features, label="seed evidence")
    _numeric_frame(catalog, features, label="acquisition catalog")
    return identifier, target, groups, features


def _stable_hash_order(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest()


def _seed_scaling(seed: pd.DataFrame, features: list[str]) -> tuple[pd.Series, pd.Series]:
    numeric = _numeric_frame(seed, features, label="seed evidence")
    medians = numeric.median(axis=0, skipna=True)
    if medians.isna().any():
        missing = medians[medians.isna()].index.tolist()
        raise MaterialsProjectAcquisitionError(
            "seed evidence cannot define imputation medians for: " + ", ".join(missing)
        )
    imputed = numeric.fillna(medians)
    std = imputed.std(axis=0, ddof=0)
    std = std.where(std > 0, 1.0)
    return medians, std


def _scaled_group_centroids(
    frame: pd.DataFrame,
    *,
    group_column: str,
    features: list[str],
    medians: pd.Series,
    std: pd.Series,
) -> dict[str, np.ndarray]:
    numeric = _numeric_frame(frame, features, label="descriptor frame").fillna(medians)
    scaled = (numeric - medians) / std
    scaled[group_column] = frame[group_column].astype(str).to_numpy()
    return {
        str(group): group_frame[features].mean(axis=0).to_numpy(dtype=float)
        for group, group_frame in scaled.groupby(group_column, sort=False)
    }


def _diversity_scores(
    *,
    training: pd.DataFrame,
    catalog: pd.DataFrame,
    group_column: str,
    features: list[str],
    medians: pd.Series,
    std: pd.Series,
) -> dict[str, float]:
    labelled = _scaled_group_centroids(
        training,
        group_column=group_column,
        features=features,
        medians=medians,
        std=std,
    )
    candidates = _scaled_group_centroids(
        catalog,
        group_column=group_column,
        features=features,
        medians=medians,
        std=std,
    )
    if not labelled:
        raise MaterialsProjectAcquisitionError("no labelled groups are available for diversity scoring")
    labelled_vectors = list(labelled.values())
    result: dict[str, float] = {}
    for group, vector in candidates.items():
        result[group] = min(float(np.linalg.norm(vector - reference)) for reference in labelled_vectors)
    return result


def _fit_selection_models(
    training: pd.DataFrame,
    *,
    target: str,
    features: list[str],
    random_seed: int,
) -> tuple[Any, Any]:
    x = training[features]
    y = pd.to_numeric(training[target], errors="coerce").to_numpy(dtype=float)
    if len(training) < 10 or len(np.unique(y)) < 2:
        raise MaterialsProjectAcquisitionError("insufficient labelled variation for uncertainty scoring")
    ridge = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]
    )
    hgb = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingRegressor(
                    random_state=random_seed,
                    max_iter=60,
                    learning_rate=0.1,
                    max_leaf_nodes=31,
                ),
            ),
        ]
    )
    ridge.fit(x, y)
    hgb.fit(x, y)
    return ridge, hgb


def _uncertainty_scores(
    *,
    training: pd.DataFrame,
    catalog: pd.DataFrame,
    group_column: str,
    target: str,
    features: list[str],
    random_seed: int,
) -> dict[str, float]:
    ridge, hgb = _fit_selection_models(
        training,
        target=target,
        features=features,
        random_seed=random_seed,
    )
    ridge_pred = np.maximum(np.asarray(ridge.predict(catalog[features]), dtype=float), 0.0)
    hgb_pred = np.maximum(np.asarray(hgb.predict(catalog[features]), dtype=float), 0.0)
    scored = pd.DataFrame(
        {
            group_column: catalog[group_column].astype(str).to_numpy(),
            "model_disagreement": np.abs(ridge_pred - hgb_pred),
        }
    )
    return {
        str(group): float(group_frame["model_disagreement"].mean())
        for group, group_frame in scored.groupby(group_column, sort=False)
    }


def _candidate_group_costs(catalog: pd.DataFrame, group_column: str) -> dict[str, int]:
    return {
        str(group): int(count)
        for group, count in catalog[group_column].astype(str).value_counts(sort=False).items()
    }


def _select_group(
    *,
    strategy: str,
    training: pd.DataFrame,
    catalog: pd.DataFrame,
    group_column: str,
    target: str,
    features: list[str],
    remaining_budget: int,
    random_seed: int,
    medians: pd.Series,
    std: pd.Series,
) -> tuple[str, float | None, str] | None:
    costs = _candidate_group_costs(catalog, group_column)
    eligible = sorted(group for group, cost in costs.items() if cost <= remaining_budget)
    if not eligible:
        return None
    if strategy == "fixed_catalog":
        return eligible[0], None, "stable lexical non-adaptive baseline"
    if strategy == "random":
        selected = min(eligible, key=lambda group: (_stable_hash_order(random_seed, group), group))
        return selected, None, "deterministic seeded hash baseline"
    if strategy == "diversity":
        scores = _diversity_scores(
            training=training,
            catalog=catalog[catalog[group_column].astype(str).isin(eligible)],
            group_column=group_column,
            features=features,
            medians=medians,
            std=std,
        )
        selected = min(eligible, key=lambda group: (-scores[group], group))
        return selected, scores[selected], "maximin descriptor-centroid diversity"
    if strategy == "uncertainty":
        eligible_catalog = catalog[catalog[group_column].astype(str).isin(eligible)]
        try:
            scores = _uncertainty_scores(
                training=training,
                catalog=eligible_catalog,
                group_column=group_column,
                target=target,
                features=features,
                random_seed=random_seed,
            )
            selected = min(eligible, key=lambda group: (-scores[group], group))
            return selected, scores[selected], "mean fixed-model disagreement"
        except (MaterialsProjectAcquisitionError, ValueError, FloatingPointError):
            scores = _diversity_scores(
                training=training,
                catalog=eligible_catalog,
                group_column=group_column,
                features=features,
                medians=medians,
                std=std,
            )
            selected = min(eligible, key=lambda group: (-scores[group], group))
            return selected, scores[selected], "uncertainty fallback to descriptor diversity"
    raise MaterialsProjectAcquisitionError(f"unsupported acquisition strategy: {strategy}")


def _oracle_labels_for_selected_ids(
    *,
    labels_path: Path,
    selected_ids: set[str],
    identifier: str,
    target: str,
) -> pd.DataFrame:
    """Return labels only for already-selected identifiers from the simulated oracle."""
    labels = pd.read_csv(labels_path, usecols=[identifier, target])
    labels[identifier] = labels[identifier].astype(str)
    if labels[identifier].duplicated().any():
        raise MaterialsProjectAcquisitionError("oracle labels contain duplicate identifiers")
    selected = labels[labels[identifier].isin(selected_ids)].copy()
    if set(selected[identifier]) != selected_ids:
        raise MaterialsProjectAcquisitionError("oracle labels do not cover the selected group exactly")
    values = pd.to_numeric(selected[target], errors="coerce").to_numpy(dtype=float)
    if not bool(np.all(np.isfinite(values))) or bool(np.any(values < 0)):
        raise MaterialsProjectAcquisitionError("oracle target contains invalid values")
    return selected


def run_materials_project_acquisition_sequence(
    *,
    benchmark_dir: str | Path,
    instance_path: str | Path,
    benchmark_config_path: str | Path,
    acquisition_config_path: str | Path,
    strategy: str,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Run one cost-bounded sequence without reading locked-test content."""
    if strategy not in _ALLOWED_STRATEGIES:
        raise MaterialsProjectAcquisitionError(f"unsupported acquisition strategy: {strategy}")
    (
        benchmark_root,
        benchmark_manifest,
        instance,
        benchmark_config,
        acquisition_config,
        paths,
    ) = _validate_benchmark_binding(
        benchmark_dir=benchmark_dir,
        instance_path=instance_path,
        benchmark_config_path=benchmark_config_path,
        acquisition_config_path=acquisition_config_path,
        include_locked_bytes=False,
    )
    if strategy not in acquisition_config["strategies"]:
        raise MaterialsProjectAcquisitionError("strategy is not enabled by acquisition config")

    seed = pd.read_csv(paths["seed_evidence"])
    catalog = pd.read_csv(paths["acquisition_catalog"])
    identifier, target, groups, features = _validate_planner_inputs(
        seed,
        catalog,
        benchmark_config,
        instance,
    )
    group_column = acquisition_config["selection_unit"]
    if group_column != benchmark_config.get("partition_group_column"):
        raise MaterialsProjectAcquisitionError("acquisition selection unit differs from locked partition group")
    medians, std = _seed_scaling(seed, features)

    training = seed.copy()
    remaining = catalog.copy()
    history_rows: list[dict[str, Any]] = []
    cumulative_cost = 0
    max_cost = int(acquisition_config["max_label_cost"])
    step = 0

    while cumulative_cost < max_cost and not remaining.empty:
        remaining_budget = max_cost - cumulative_cost
        selected = _select_group(
            strategy=strategy,
            training=training,
            catalog=remaining,
            group_column=group_column,
            target=target,
            features=features,
            remaining_budget=remaining_budget,
            random_seed=int(acquisition_config["random_seed"]),
            medians=medians,
            std=std,
        )
        if selected is None:
            break
        selected_group, selection_score, reason = selected
        selected_catalog = remaining[remaining[group_column].astype(str).eq(selected_group)].copy()
        selected_ids = set(selected_catalog[identifier].astype(str))
        cost = len(selected_catalog)
        if cost <= 0 or cost > remaining_budget:
            raise MaterialsProjectAcquisitionError("selected group violates label budget")
        selected_labels = _oracle_labels_for_selected_ids(
            labels_path=paths["acquisition_labels"],
            selected_ids=selected_ids,
            identifier=identifier,
            target=target,
        )
        acquired = selected_catalog.merge(
            selected_labels,
            on=identifier,
            how="left",
            validate="one_to_one",
            sort=False,
        )
        expected_columns = [identifier, *groups, *features, target]
        acquired = acquired[expected_columns]
        training = pd.concat([training, acquired], ignore_index=True)
        remaining = remaining[~remaining[identifier].astype(str).isin(selected_ids)].copy()
        cumulative_cost += cost
        step += 1
        history_rows.append(
            {
                "step": step,
                "strategy": strategy,
                "selected_group": selected_group,
                "acquired_rows": int(cost),
                "step_cost": int(cost),
                "cumulative_cost": int(cumulative_cost),
                "remaining_budget": int(max_cost - cumulative_cost),
                "selection_score": selection_score,
                "selection_reason": reason,
            }
        )

    stop_reason = "label_budget_exhausted"
    if cumulative_cost < max_cost:
        if remaining.empty:
            stop_reason = "acquisition_pool_exhausted"
        else:
            stop_reason = "no_remaining_group_fits_budget"
    history = pd.DataFrame(
        history_rows,
        columns=[
            "step",
            "strategy",
            "selected_group",
            "acquired_rows",
            "step_cost",
            "cumulative_cost",
            "remaining_budget",
            "selection_score",
            "selection_reason",
        ],
    )
    training = training.sort_values(identifier, kind="mergesort").reset_index(drop=True)
    remaining = remaining.sort_values(identifier, kind="mergesort").reset_index(drop=True)

    instance_resolved = Path(instance_path).expanduser().resolve(strict=True)
    benchmark_config_resolved = Path(benchmark_config_path).expanduser().resolve(strict=True)
    acquisition_config_resolved = Path(acquisition_config_path).expanduser().resolve(strict=True)
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(
            benchmark_root,
            instance_resolved,
            benchmark_config_resolved,
            acquisition_config_resolved,
        ),
        recognized_markers=(SEQUENCE_MANIFEST,),
    ) as staging:
        output_paths = {
            "training_evidence": "training_evidence.csv",
            "acquisition_history": "acquisition_history.csv",
            "remaining_catalog": "remaining_catalog.csv",
        }
        _write_text(staging / output_paths["training_evidence"], _csv_text(training))
        _write_text(staging / output_paths["acquisition_history"], _csv_text(history))
        _write_text(staging / output_paths["remaining_catalog"], _csv_text(remaining))
        output_hashes = {
            key: _sha256_file(staging / relative)
            for key, relative in output_paths.items()
        }
        sequence_manifest: dict[str, Any] = {
            "schema_version": SEQUENCE_SCHEMA_VERSION,
            "benchmark_id": acquisition_config["benchmark_id"],
            "sequence_version": acquisition_config["sequence_version"],
            "execution_status": "completed",
            "strategy": strategy,
            "strategy_contract": acquisition_config["strategy_contracts"][strategy],
            "benchmark_instance": {
                "path": instance_resolved.name,
                "sha256": _sha256_file(instance_resolved),
                "source_sha256": instance["source"]["sha256"],
                "benchmark_manifest_benchmark_id": benchmark_manifest["benchmark_id"],
            },
            "acquisition_contract": {
                "path": acquisition_config_resolved.name,
                "sha256": _sha256_file(acquisition_config_resolved),
                "selection_unit": group_column,
                "max_label_cost": max_cost,
                "cost_definition": acquisition_config["cost_definition"],
            },
            "counts": {
                "seed_rows": int(len(seed)),
                "acquired_rows": int(len(training) - len(seed)),
                "final_training_rows": int(len(training)),
                "remaining_catalog_rows": int(len(remaining)),
                "acquisition_steps": int(len(history)),
                "cost_used": int(cumulative_cost),
                "cost_remaining": int(max_cost - cumulative_cost),
            },
            "stop_reason": stop_reason,
            "planner_boundary": {
                "seed_target_visible": True,
                "acquisition_target_visible_before_selection": False,
                "oracle_labels_revealed_only_for_selected_ids": True,
                "locked_test_content_read": False,
                "locked_test_used_for_selection": False,
            },
            "feature_count": int(len(features)),
            "outputs": output_paths,
            "output_sha256": output_hashes,
            "scientific_evidence_created": False,
            "next_stage": "Run locked evaluation only after sequence completion.",
        }
        _write_text(
            staging / SEQUENCE_MANIFEST,
            json.dumps(sequence_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    return sequence_manifest


def _validate_sequence_outputs(
    sequence_dir: Path,
    sequence_manifest: dict[str, Any],
) -> dict[str, Path]:
    if sequence_manifest.get("schema_version") != SEQUENCE_SCHEMA_VERSION:
        raise MaterialsProjectAcquisitionError("unsupported sequence manifest schema_version")
    if sequence_manifest.get("execution_status") != "completed":
        raise MaterialsProjectAcquisitionError("locked evaluation requires a completed sequence")
    boundary = sequence_manifest.get("planner_boundary")
    if not isinstance(boundary, dict) or boundary.get("locked_test_content_read") is not False:
        raise MaterialsProjectAcquisitionError("sequence does not certify the locked-test boundary")
    outputs = sequence_manifest.get("outputs")
    hashes = sequence_manifest.get("output_sha256")
    if not isinstance(outputs, dict) or not isinstance(hashes, dict):
        raise MaterialsProjectAcquisitionError("sequence output inventory is invalid")
    paths: dict[str, Path] = {}
    for key in ("training_evidence", "acquisition_history", "remaining_catalog"):
        relative = outputs.get(key)
        if not isinstance(relative, str) or not relative:
            raise MaterialsProjectAcquisitionError(f"sequence output path missing: {key}")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise MaterialsProjectAcquisitionError(f"unsafe sequence output path: {key}")
        path = sequence_dir / candidate
        if not path.is_file() or hashes.get(key) != _sha256_file(path):
            raise MaterialsProjectAcquisitionError(f"sequence output checksum mismatch: {key}")
        paths[key] = path
    return paths


def _build_model(name: str, random_seed: int) -> tuple[Any, str]:
    if name == "dummy_median":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", DummyRegressor(strategy="median"))]), "raw"
    if name == "ridge_raw":
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        ), "raw"
    if name == "ridge_log1p":
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        ), "log1p"
    if name == "histogram_gradient_boosting_raw":
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        random_state=random_seed,
                        max_iter=60,
                        learning_rate=0.1,
                        max_leaf_nodes=31,
                    ),
                ),
            ]
        ), "raw"
    if name == "histogram_gradient_boosting_log1p":
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        random_state=random_seed,
                        max_iter=60,
                        learning_rate=0.1,
                        max_leaf_nodes=31,
                    ),
                ),
            ]
        ), "log1p"
    raise MaterialsProjectAcquisitionError(f"unsupported evaluation model: {name}")


def _precision_at_fraction(actual: np.ndarray, prediction: np.ndarray, fraction: float) -> float:
    if len(actual) == 0:
        return float("nan")
    count = max(1, int(math.ceil(len(actual) * fraction)))
    actual_order = np.argsort(actual, kind="mergesort")[:count]
    pred_order = np.argsort(prediction, kind="mergesort")[:count]
    actual_set = set(int(value) for value in actual_order)
    pred_set = set(int(value) for value in pred_order)
    return float(len(actual_set.intersection(pred_set)) / len(pred_set))


def _evaluate_training_scope(
    *,
    scope_name: str,
    training: pd.DataFrame,
    locked: pd.DataFrame,
    identifier: str,
    target: str,
    features: list[str],
    model_names: Iterable[str],
    random_seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    x_train = training[features]
    y_train_raw = pd.to_numeric(training[target], errors="coerce").to_numpy(dtype=float)
    x_test = locked[features]
    y_test = pd.to_numeric(locked[target], errors="coerce").to_numpy(dtype=float)
    metrics: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    for model_name in model_names:
        model, target_treatment = _build_model(model_name, random_seed)
        y_fit = np.log1p(y_train_raw) if target_treatment == "log1p" else y_train_raw
        model.fit(x_train, y_fit)
        raw_prediction = np.asarray(model.predict(x_test), dtype=float)
        if target_treatment == "log1p":
            raw_prediction = np.expm1(raw_prediction)
        constrained = np.maximum(raw_prediction, 0.0)
        mae = float(mean_absolute_error(y_test, constrained))
        rmse = float(math.sqrt(mean_squared_error(y_test, constrained)))
        r2 = float(r2_score(y_test, constrained)) if len(y_test) >= 2 else float("nan")
        spearman = float(pd.Series(y_test).corr(pd.Series(constrained), method="spearman"))
        metrics.append(
            {
                "training_scope": scope_name,
                "model_variant": model_name,
                "training_rows": int(len(training)),
                "locked_rows": int(len(locked)),
                "mae": mae,
                "rmse": rmse,
                "r2": r2,
                "spearman": spearman,
                "prediction_bias_mean": float(np.mean(constrained - y_test)),
                "negative_raw_prediction_rate": float(np.mean(raw_prediction < 0.0)),
                "precision_at_10pct": _precision_at_fraction(y_test, constrained, 0.10),
                "precision_at_20pct": _precision_at_fraction(y_test, constrained, 0.20),
            }
        )
        for row_index, (_, row) in enumerate(locked.iterrows()):
            predictions.append(
                {
                    "training_scope": scope_name,
                    "model_variant": model_name,
                    identifier: row[identifier],
                    "actual_target": float(y_test[row_index]),
                    "raw_prediction": float(raw_prediction[row_index]),
                    "constrained_prediction": float(constrained[row_index]),
                    "absolute_error": float(abs(y_test[row_index] - constrained[row_index])),
                }
            )
    return metrics, predictions


def evaluate_materials_project_acquisition_sequence(
    *,
    benchmark_dir: str | Path,
    instance_path: str | Path,
    benchmark_config_path: str | Path,
    acquisition_config_path: str | Path,
    sequence_dir: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Evaluate a completed sequence on locked data without feeding metrics back to it."""
    (
        benchmark_root,
        _,
        instance,
        benchmark_config,
        acquisition_config,
        paths,
    ) = _validate_benchmark_binding(
        benchmark_dir=benchmark_dir,
        instance_path=instance_path,
        benchmark_config_path=benchmark_config_path,
        acquisition_config_path=acquisition_config_path,
        include_locked_bytes=True,
    )
    sequence_root = Path(sequence_dir).expanduser().resolve(strict=True)
    sequence_manifest = _load_json(sequence_root / SEQUENCE_MANIFEST)
    if sequence_manifest.get("benchmark_id") != acquisition_config["benchmark_id"]:
        raise MaterialsProjectAcquisitionError("sequence benchmark id mismatch")
    sequence_paths = _validate_sequence_outputs(sequence_root, sequence_manifest)

    seed = pd.read_csv(paths["seed_evidence"])
    catalog = pd.read_csv(paths["acquisition_catalog"])
    identifier, target, groups, features = _validate_planner_inputs(
        seed,
        catalog,
        benchmark_config,
        instance,
    )
    final_training = pd.read_csv(sequence_paths["training_evidence"])
    expected_training_columns = [identifier, *groups, *features, target]
    if list(final_training.columns) != expected_training_columns:
        raise MaterialsProjectAcquisitionError("sequence training evidence columns drifted")
    if set(seed[identifier].astype(str)) - set(final_training[identifier].astype(str)):
        raise MaterialsProjectAcquisitionError("sequence training evidence lost seed rows")
    if final_training[identifier].astype(str).duplicated().any():
        raise MaterialsProjectAcquisitionError("sequence training evidence contains duplicate identifiers")
    if len(final_training) != int(sequence_manifest["counts"]["final_training_rows"]):
        raise MaterialsProjectAcquisitionError("sequence training row count differs from manifest")

    locked = pd.read_csv(paths["locked_test"])
    expected_locked_columns = [identifier, *groups, *features, target]
    if list(locked.columns) != expected_locked_columns:
        raise MaterialsProjectAcquisitionError("locked-test column order drifted")
    if len(locked) != int(instance["partitions"]["locked_test"]["rows"]):
        raise MaterialsProjectAcquisitionError("locked-test row count differs from pinned instance")
    if set(locked[identifier].astype(str)).intersection(set(final_training[identifier].astype(str))):
        raise MaterialsProjectAcquisitionError("training and locked-test identifiers overlap")
    locked_target = pd.to_numeric(locked[target], errors="coerce").to_numpy(dtype=float)
    if not bool(np.all(np.isfinite(locked_target))) or bool(np.any(locked_target < 0)):
        raise MaterialsProjectAcquisitionError("locked-test target contains invalid values")

    model_names = acquisition_config["evaluation_models"]
    seed_metrics, seed_predictions = _evaluate_training_scope(
        scope_name="seed_only",
        training=seed,
        locked=locked,
        identifier=identifier,
        target=target,
        features=features,
        model_names=model_names,
        random_seed=int(acquisition_config["random_seed"]),
    )
    final_metrics, final_predictions = _evaluate_training_scope(
        scope_name="final_sequence",
        training=final_training,
        locked=locked,
        identifier=identifier,
        target=target,
        features=features,
        model_names=model_names,
        random_seed=int(acquisition_config["random_seed"]),
    )
    metrics = pd.DataFrame(seed_metrics + final_metrics)
    predictions = pd.DataFrame(seed_predictions + final_predictions)
    primary = acquisition_config["primary_evaluation_model"]
    primary_seed = metrics[
        metrics["training_scope"].eq("seed_only") & metrics["model_variant"].eq(primary)
    ].iloc[0]
    primary_final = metrics[
        metrics["training_scope"].eq("final_sequence") & metrics["model_variant"].eq(primary)
    ].iloc[0]
    delta_mae = float(primary_final["mae"] - primary_seed["mae"])
    improvement_fraction = (
        float((primary_seed["mae"] - primary_final["mae"]) / primary_seed["mae"])
        if float(primary_seed["mae"]) > 0
        else float("nan")
    )
    primary_result = {
        "model_variant": primary,
        "seed_only_mae": float(primary_seed["mae"]),
        "final_sequence_mae": float(primary_final["mae"]),
        "delta_mae_final_minus_seed": delta_mae,
        "relative_mae_improvement_fraction": improvement_fraction,
        "improved": bool(delta_mae < 0),
        "seed_only_r2": float(primary_seed["r2"]),
        "final_sequence_r2": float(primary_final["r2"]),
        "seed_only_spearman": float(primary_seed["spearman"]),
        "final_sequence_spearman": float(primary_final["spearman"]),
    }

    instance_resolved = Path(instance_path).expanduser().resolve(strict=True)
    benchmark_config_resolved = Path(benchmark_config_path).expanduser().resolve(strict=True)
    acquisition_config_resolved = Path(acquisition_config_path).expanduser().resolve(strict=True)
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(
            benchmark_root,
            sequence_root,
            instance_resolved,
            benchmark_config_resolved,
            acquisition_config_resolved,
        ),
        recognized_markers=(EVALUATION_MANIFEST,),
    ) as staging:
        output_paths = {
            "locked_metrics": "locked_metrics.csv",
            "locked_predictions": "locked_predictions.csv",
        }
        _write_text(staging / output_paths["locked_metrics"], _csv_text(metrics))
        _write_text(staging / output_paths["locked_predictions"], _csv_text(predictions))
        output_hashes = {
            key: _sha256_file(staging / relative)
            for key, relative in output_paths.items()
        }
        evaluation_manifest: dict[str, Any] = {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "benchmark_id": acquisition_config["benchmark_id"],
            "evaluation_status": "completed",
            "strategy": sequence_manifest["strategy"],
            "sequence_manifest_sha256": _sha256_file(sequence_root / SEQUENCE_MANIFEST),
            "cost_used": int(sequence_manifest["counts"]["cost_used"]),
            "acquired_rows": int(sequence_manifest["counts"]["acquired_rows"]),
            "locked_test_sha256": instance["output_sha256"]["locked_test"],
            "primary_model_result": primary_result,
            "all_evaluation_models": model_names,
            "outputs": output_paths,
            "output_sha256": output_hashes,
            "locked_boundary": {
                "sequence_completed_before_locked_read": True,
                "locked_metrics_not_available_to_sequence": True,
                "primary_model_predeclared": True,
            },
            "scientific_evidence_level": "Diagnostic",
            "scientific_boundary": (
                "This is retrospective locked-test research-efficiency evidence for a computed "
                "Materials Project target. It is not experimental synthesizability, causality, "
                "or production-screening evidence."
            ),
        }
        _write_text(
            staging / EVALUATION_MANIFEST,
            json.dumps(evaluation_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    return evaluation_manifest


def compare_materials_project_acquisition_evaluations(
    *,
    evaluation_dirs: Iterable[str | Path],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compare completed strategy evaluations using only their frozen manifests."""
    rows: list[dict[str, Any]] = []
    benchmark_ids: set[str] = set()
    primary_models: set[str] = set()
    seen_strategies: set[str] = set()
    for value in evaluation_dirs:
        root = Path(value).expanduser().resolve(strict=True)
        manifest = _load_json(root / EVALUATION_MANIFEST)
        if manifest.get("schema_version") != EVALUATION_SCHEMA_VERSION:
            raise MaterialsProjectAcquisitionError("unsupported evaluation manifest schema_version")
        if manifest.get("evaluation_status") != "completed":
            raise MaterialsProjectAcquisitionError("comparison requires completed evaluations")
        primary = manifest.get("primary_model_result")
        if not isinstance(primary, dict):
            raise MaterialsProjectAcquisitionError("evaluation primary model result is invalid")
        strategy = _require_nonempty_string(manifest.get("strategy"), "strategy")
        if strategy in seen_strategies:
            raise MaterialsProjectAcquisitionError(f"duplicate strategy evaluation: {strategy}")
        seen_strategies.add(strategy)
        benchmark_ids.add(_require_nonempty_string(manifest.get("benchmark_id"), "benchmark_id"))
        primary_models.add(_require_nonempty_string(primary.get("model_variant"), "model_variant"))
        rows.append(
            {
                "strategy": strategy,
                "cost_used": int(manifest["cost_used"]),
                "acquired_rows": int(manifest["acquired_rows"]),
                "primary_model": primary["model_variant"],
                "seed_only_mae": float(primary["seed_only_mae"]),
                "final_sequence_mae": float(primary["final_sequence_mae"]),
                "delta_mae_final_minus_seed": float(primary["delta_mae_final_minus_seed"]),
                "relative_mae_improvement_fraction": float(primary["relative_mae_improvement_fraction"]),
                "improved": bool(primary["improved"]),
                "final_sequence_r2": float(primary["final_sequence_r2"]),
                "final_sequence_spearman": float(primary["final_sequence_spearman"]),
            }
        )
    if len(benchmark_ids) != 1 or len(primary_models) != 1:
        raise MaterialsProjectAcquisitionError(
            "evaluation manifests must share one benchmark and one predeclared primary model"
        )
    frame = pd.DataFrame(rows).sort_values(
        ["final_sequence_mae", "cost_used", "strategy"],
        kind="mergesort",
    )
    best_strategy = str(frame.iloc[0]["strategy"]) if not frame.empty else None
    result = {
        "benchmark_id": next(iter(benchmark_ids)),
        "primary_model": next(iter(primary_models)),
        "strategy_count": int(len(frame)),
        "strategies": frame.to_dict(orient="records"),
        "lowest_locked_mae_strategy": best_strategy,
        "scientific_evidence_level": "Diagnostic",
        "selection_warning": (
            "The lowest locked-test MAE is a retrospective comparison result and must not be "
            "used to retune or redefine the already evaluated strategies on benchmark v1."
        ),
    }
    if output_path is not None:
        path = Path(output_path).expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(path, json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return result
