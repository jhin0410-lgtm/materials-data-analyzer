"""Non-locked policy-development replay for Materials Project acquisition policies.

This module intentionally excludes the benchmark-v1 locked test. It reconstructs a
671-row development corpus from the verified seed and acquisition partitions,
creates multiple target-blind group-disjoint development replays, and replays the
frozen v1 strategy class plus repeated random baselines. Results are development
diagnostics only and cannot promote policy-v2 without new independent evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

from materials_data_analyzer.research_loop.materials_project_acquisition_loop import (
    MaterialsProjectAcquisitionError,
    _build_model,
    _seed_scaling,
    _select_group,
)
from platform_core.output_safety import transactional_output_directory


SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "development_replay_manifest.json"
DEV_PARTITIONS = ("development_seed", "development_pool", "development_validation")


class MaterialsProjectPolicyReplayError(ValueError):
    """Raised when the development replay contract is violated."""


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise MaterialsProjectPolicyReplayError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise MaterialsProjectPolicyReplayError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise MaterialsProjectPolicyReplayError(f"JSON root must be an object: {resolved}")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_text(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterialsProjectPolicyReplayError(f"{field} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MaterialsProjectPolicyReplayError(f"{field} must be a positive integer")
    return value


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MaterialsProjectPolicyReplayError(f"{field} must be a non-empty list")
    result = [_require_string(item, f"{field} item") for item in value]
    if len(result) != len(set(result)):
        raise MaterialsProjectPolicyReplayError(f"{field} must not contain duplicates")
    return result


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "replay_id",
        "source_benchmark_id",
        "development_source",
        "partition_group_column",
        "required_disjoint_group_columns",
        "partition_fractions",
        "replay_salts",
        "max_label_cost",
        "random_seeds",
        "fixed_strategy_seed",
        "strategies",
        "evaluation_models",
        "development_questions",
        "scientific_boundary",
    }
    if set(value) != required or value.get("schema_version") != SCHEMA_VERSION:
        raise MaterialsProjectPolicyReplayError("development replay config keys/schema mismatch")

    source = value["development_source"]
    if not isinstance(source, dict) or set(source) != {
        "allowed_partitions",
        "expected_rows",
        "locked_test_read_authorized",
    }:
        raise MaterialsProjectPolicyReplayError("development_source contract is invalid")
    if source.get("allowed_partitions") != ["seed_evidence", "acquisition_pool"]:
        raise MaterialsProjectPolicyReplayError("only benchmark seed/acquisition partitions may be used")
    if source.get("locked_test_read_authorized") is not False:
        raise MaterialsProjectPolicyReplayError("locked-test access must remain prohibited")
    expected_rows = _require_positive_int(source.get("expected_rows"), "development_source.expected_rows")

    fractions = value["partition_fractions"]
    if not isinstance(fractions, dict) or set(fractions) != set(DEV_PARTITIONS):
        raise MaterialsProjectPolicyReplayError("development partition fractions are invalid")
    normalized: dict[str, float] = {}
    for name in DEV_PARTITIONS:
        raw = fractions[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise MaterialsProjectPolicyReplayError(f"partition fraction is not numeric: {name}")
        number = float(raw)
        if not math.isfinite(number) or number <= 0.0 or number >= 1.0:
            raise MaterialsProjectPolicyReplayError(f"partition fraction out of range: {name}")
        normalized[name] = number
    if not math.isclose(sum(normalized.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise MaterialsProjectPolicyReplayError("development partition fractions must sum to one")

    random_seeds = value["random_seeds"]
    if not isinstance(random_seeds, list) or not random_seeds:
        raise MaterialsProjectPolicyReplayError("random_seeds must be a non-empty list")
    if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in random_seeds):
        raise MaterialsProjectPolicyReplayError("random_seeds must contain integers")
    if len(random_seeds) != len(set(random_seeds)):
        raise MaterialsProjectPolicyReplayError("random_seeds must be unique")

    strategies = _require_string_list(value["strategies"], "strategies")
    if strategies != ["fixed_catalog", "random", "diversity", "uncertainty"]:
        raise MaterialsProjectPolicyReplayError("strategy inventory must match frozen v1 policies")

    return {
        **value,
        "replay_id": _require_string(value["replay_id"], "replay_id"),
        "source_benchmark_id": _require_string(value["source_benchmark_id"], "source_benchmark_id"),
        "partition_group_column": _require_string(value["partition_group_column"], "partition_group_column"),
        "required_disjoint_group_columns": _require_string_list(
            value["required_disjoint_group_columns"], "required_disjoint_group_columns"
        ),
        "partition_fractions": normalized,
        "replay_salts": _require_string_list(value["replay_salts"], "replay_salts"),
        "max_label_cost": _require_positive_int(value["max_label_cost"], "max_label_cost"),
        "fixed_strategy_seed": int(value["fixed_strategy_seed"]),
        "random_seeds": [int(seed) for seed in random_seeds],
        "strategies": strategies,
        "evaluation_models": _require_string_list(value["evaluation_models"], "evaluation_models"),
        "development_questions": _require_string_list(value["development_questions"], "development_questions"),
        "scientific_boundary": _require_string_list(value["scientific_boundary"], "scientific_boundary"),
        "development_source": {**source, "expected_rows": expected_rows},
    }


def _safe_child(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise MaterialsProjectPolicyReplayError(f"missing benchmark output path: {label}")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MaterialsProjectPolicyReplayError(f"unsafe benchmark output path: {label}")
    path = root / candidate
    if not path.is_file():
        raise MaterialsProjectPolicyReplayError(f"missing benchmark output: {label}")
    return path


def _load_development_corpus(
    benchmark_root: Path,
    benchmark_config_path: Path,
    replay_config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], list[str]]:
    manifest = _load_json(benchmark_root / "benchmark_manifest.json")
    benchmark_config = _load_json(benchmark_config_path)
    if manifest.get("benchmark_id") != replay_config["source_benchmark_id"]:
        raise MaterialsProjectPolicyReplayError("benchmark manifest id differs from replay contract")
    if benchmark_config.get("benchmark_id") != replay_config["source_benchmark_id"]:
        raise MaterialsProjectPolicyReplayError("benchmark config id differs from replay contract")

    identifier = _require_string(benchmark_config.get("identifier_column"), "identifier_column")
    target = _require_string(benchmark_config.get("target_column"), "target_column")
    groups = replay_config["required_disjoint_group_columns"]
    if benchmark_config.get("partition_group_column") != replay_config["partition_group_column"]:
        raise MaterialsProjectPolicyReplayError("development replay partition group differs from benchmark")
    if benchmark_config.get("required_disjoint_group_columns") != groups:
        raise MaterialsProjectPolicyReplayError("development replay disjoint-group contract differs from benchmark")

    outputs = manifest.get("outputs")
    hashes = manifest.get("output_sha256")
    if not isinstance(outputs, dict) or not isinstance(hashes, dict):
        raise MaterialsProjectPolicyReplayError("benchmark output inventory is invalid")

    # Deliberately resolve and read only the non-locked development inputs.
    paths = {
        key: _safe_child(benchmark_root, outputs.get(key), key)
        for key in ("seed_evidence", "acquisition_catalog", "acquisition_labels")
    }
    for key, path in paths.items():
        if hashes.get(key) != _sha256_file(path):
            raise MaterialsProjectPolicyReplayError(f"benchmark checksum mismatch: {key}")

    seed = pd.read_csv(paths["seed_evidence"])
    catalog = pd.read_csv(paths["acquisition_catalog"])
    labels = pd.read_csv(paths["acquisition_labels"])
    if list(labels.columns) != [identifier, target]:
        raise MaterialsProjectPolicyReplayError("acquisition label schema differs from benchmark contract")
    if labels[identifier].astype(str).duplicated().any():
        raise MaterialsProjectPolicyReplayError("acquisition labels contain duplicate identifiers")
    pool = catalog.merge(labels, on=identifier, how="left", validate="one_to_one", sort=False)
    if pool[target].isna().any():
        raise MaterialsProjectPolicyReplayError("acquisition labels do not cover development pool")

    expected_prefix = [identifier, *groups]
    if list(seed.columns[: len(expected_prefix)]) != expected_prefix:
        raise MaterialsProjectPolicyReplayError("seed metadata columns differ from expected contract")
    features = [column for column in seed.columns if column not in {identifier, target, *groups}]
    expected_seed_columns = [identifier, *groups, *features, target]
    if list(seed.columns) != expected_seed_columns:
        raise MaterialsProjectPolicyReplayError("seed column order is not canonical")
    if list(pool.columns) != expected_seed_columns:
        raise MaterialsProjectPolicyReplayError("development pool column order is not canonical")

    development = pd.concat([seed, pool], ignore_index=True)
    if len(development) != int(replay_config["development_source"]["expected_rows"]):
        raise MaterialsProjectPolicyReplayError("development corpus row count differs from replay contract")
    ids = development[identifier].astype(str)
    if ids.duplicated().any():
        raise MaterialsProjectPolicyReplayError("development corpus identifiers overlap")
    return development, manifest, benchmark_config, features


def _stable_hash(salt: str, value: str) -> str:
    return hashlib.sha256(f"{salt}\0{value}".encode("utf-8")).hexdigest()


def _partition_map(
    frame: pd.DataFrame,
    *,
    group_column: str,
    fractions: dict[str, float],
    salt: str,
) -> dict[str, str]:
    sizes = frame[group_column].astype(str).value_counts(sort=False).to_dict()
    records = sorted(
        ((str(group), int(size)) for group, size in sizes.items()),
        key=lambda item: (-item[1], _stable_hash(salt, item[0]), item[0]),
    )
    targets = {name: len(frame) * fractions[name] for name in DEV_PARTITIONS}
    counts = {name: 0 for name in DEV_PARTITIONS}
    assignment: dict[str, str] = {}
    for group, size in records:
        scored: list[tuple[tuple[float, ...], str]] = []
        for order, name in enumerate(DEV_PARTITIONS):
            target = targets[name]
            projected = counts[name] + size
            overflow = max(0.0, projected - target)
            score = (
                1.0 if overflow > 0.0 else 0.0,
                overflow / target,
                counts[name] / target,
                float(order),
            )
            scored.append((score, name))
        selected = min(scored, key=lambda item: item[0])[1]
        assignment[group] = selected
        counts[selected] += size
    if any(counts[name] == 0 for name in DEV_PARTITIONS):
        raise MaterialsProjectPolicyReplayError("development replay produced an empty partition")
    return assignment


def _partition_frame(
    frame: pd.DataFrame,
    *,
    assignment: dict[str, str],
    group_column: str,
    required_groups: list[str],
) -> dict[str, pd.DataFrame]:
    membership = frame[group_column].astype(str).map(assignment)
    if membership.isna().any():
        raise MaterialsProjectPolicyReplayError("development group assignment is incomplete")
    partitions = {
        name: frame.loc[membership.eq(name)].copy().reset_index(drop=True)
        for name in DEV_PARTITIONS
    }
    for column in required_groups:
        mapping = pd.DataFrame({"partition": membership, "group": frame[column].astype(str)})
        counts = mapping.groupby("group")["partition"].nunique()
        if bool((counts > 1).any()):
            raise MaterialsProjectPolicyReplayError(
                f"required development group crosses partitions: {column}"
            )
    return partitions


def _safe_spearman(actual: np.ndarray, prediction: np.ndarray) -> float:
    if len(actual) < 2 or np.all(actual == actual[0]) or np.all(prediction == prediction[0]):
        return float("nan")
    return float(pd.Series(actual).corr(pd.Series(prediction), method="spearman"))


def _evaluate(
    *,
    seed: pd.DataFrame,
    training: pd.DataFrame,
    validation: pd.DataFrame,
    target: str,
    features: list[str],
    models: Iterable[str],
    random_seed: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    x_validation = validation[features]
    y_validation = pd.to_numeric(validation[target], errors="raise").to_numpy(dtype=float)
    for model_name in models:
        scope_values: dict[str, dict[str, float]] = {}
        for scope_name, scope in (("seed", seed), ("final", training)):
            model, treatment = _build_model(model_name, random_seed)
            y_train = pd.to_numeric(scope[target], errors="raise").to_numpy(dtype=float)
            y_fit = np.log1p(y_train) if treatment == "log1p" else y_train
            model.fit(scope[features], y_fit)
            prediction = np.asarray(model.predict(x_validation), dtype=float)
            if treatment == "log1p":
                prediction = np.expm1(prediction)
            prediction = np.maximum(prediction, 0.0)
            scope_values[scope_name] = {
                "mae": float(mean_absolute_error(y_validation, prediction)),
                "r2": float(r2_score(y_validation, prediction)) if len(validation) >= 2 else float("nan"),
                "spearman": _safe_spearman(y_validation, prediction),
            }
        seed_mae = scope_values["seed"]["mae"]
        final_mae = scope_values["final"]["mae"]
        results.append(
            {
                "model_variant": model_name,
                "seed_mae": seed_mae,
                "final_mae": final_mae,
                "relative_mae_improvement_fraction": (
                    (seed_mae - final_mae) / seed_mae if seed_mae > 0 else float("nan")
                ),
                "final_r2": scope_values["final"]["r2"],
                "final_spearman": scope_values["final"]["spearman"],
            }
        )
    return results


def _run_sequence(
    *,
    seed: pd.DataFrame,
    pool: pd.DataFrame,
    validation: pd.DataFrame,
    strategy: str,
    random_seed: int,
    identifier: str,
    target: str,
    groups: list[str],
    features: list[str],
    group_column: str,
    max_cost: int,
    models: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    training = seed.copy()
    remaining = pool.drop(columns=[target]).copy()
    oracle = pool[[identifier, target]].copy()
    medians, std = _seed_scaling(seed, features)
    history: list[dict[str, Any]] = []
    cumulative = 0
    step = 0
    while cumulative < max_cost and not remaining.empty:
        budget = max_cost - cumulative
        selected = _select_group(
            strategy=strategy,
            training=training,
            catalog=remaining,
            group_column=group_column,
            target=target,
            features=features,
            remaining_budget=budget,
            random_seed=random_seed,
            medians=medians,
            std=std,
        )
        if selected is None:
            break
        selected_group, score, reason = selected
        selected_catalog = remaining[remaining[group_column].astype(str).eq(selected_group)].copy()
        cost = len(selected_catalog)
        if cost <= 0 or cost > budget:
            raise MaterialsProjectPolicyReplayError("development strategy violated label budget")
        selected_ids = set(selected_catalog[identifier].astype(str))
        selected_labels = oracle[oracle[identifier].astype(str).isin(selected_ids)].copy()
        if set(selected_labels[identifier].astype(str)) != selected_ids:
            raise MaterialsProjectPolicyReplayError("development oracle does not cover selected group")
        acquired = selected_catalog.merge(selected_labels, on=identifier, how="left", validate="one_to_one")
        acquired = acquired[[identifier, *groups, *features, target]]
        training = pd.concat([training, acquired], ignore_index=True)
        remaining = remaining[~remaining[identifier].astype(str).isin(selected_ids)].copy()
        cumulative += cost
        step += 1
        target_values = pd.to_numeric(acquired[target], errors="raise")
        history.append(
            {
                "step": step,
                "selected_group": selected_group,
                "step_cost": int(cost),
                "cumulative_cost": int(cumulative),
                "selection_score": score,
                "selection_reason": reason,
                "acquired_target_mean": float(target_values.mean()),
                "acquired_target_median": float(target_values.median()),
            }
        )
    metrics = _evaluate(
        seed=seed,
        training=training,
        validation=validation,
        target=target,
        features=features,
        models=models,
        random_seed=random_seed,
    )
    return metrics, history


def _summary(results: pd.DataFrame) -> pd.DataFrame:
    grouped = results.groupby(["strategy", "model_variant"], sort=True)
    rows: list[dict[str, Any]] = []
    for (strategy, model), frame in grouped:
        improvement = pd.to_numeric(frame["relative_mae_improvement_fraction"], errors="coerce")
        final_mae = pd.to_numeric(frame["final_mae"], errors="coerce")
        rows.append(
            {
                "strategy": strategy,
                "model_variant": model,
                "sequence_count": int(len(frame)),
                "final_mae_mean": float(final_mae.mean()),
                "final_mae_median": float(final_mae.median()),
                "final_mae_std": float(final_mae.std(ddof=0)),
                "relative_mae_improvement_mean": float(improvement.mean()),
                "relative_mae_improvement_median": float(improvement.median()),
                "improvement_positive_fraction": float((improvement > 0).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["model_variant", "final_mae_mean", "strategy"])


def run_materials_project_policy_development_replay(
    *,
    benchmark_dir: str | Path,
    benchmark_config_path: str | Path,
    replay_config_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Run multi-replay development diagnostics without reading benchmark-v1 locked data."""
    benchmark_root = Path(benchmark_dir).expanduser().resolve(strict=True)
    benchmark_config_resolved = Path(benchmark_config_path).expanduser().resolve(strict=True)
    replay_config_resolved = Path(replay_config_path).expanduser().resolve(strict=True)
    replay_config = _validate_config(_load_json(replay_config_resolved))
    development, benchmark_manifest, benchmark_config, features = _load_development_corpus(
        benchmark_root,
        benchmark_config_resolved,
        replay_config,
    )
    identifier = str(benchmark_config["identifier_column"])
    target = str(benchmark_config["target_column"])
    groups = list(replay_config["required_disjoint_group_columns"])
    group_column = replay_config["partition_group_column"]

    result_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    partition_rows: list[dict[str, Any]] = []
    for replay_index, salt in enumerate(replay_config["replay_salts"], start=1):
        assignment = _partition_map(
            development,
            group_column=group_column,
            fractions=replay_config["partition_fractions"],
            salt=salt,
        )
        partitions = _partition_frame(
            development,
            assignment=assignment,
            group_column=group_column,
            required_groups=groups,
        )
        for name, frame in partitions.items():
            partition_rows.append(
                {
                    "replay": replay_index,
                    "salt": salt,
                    "partition": name,
                    "rows": int(len(frame)),
                    "chemical_system_groups": int(frame[group_column].astype(str).nunique()),
                }
            )

        sequence_specs = [
            ("fixed_catalog", replay_config["fixed_strategy_seed"], "fixed_catalog"),
            ("diversity", replay_config["fixed_strategy_seed"], "diversity"),
            ("uncertainty", replay_config["fixed_strategy_seed"], "uncertainty"),
        ]
        sequence_specs.extend(
            ("random", seed_value, f"random_seed_{seed_value}")
            for seed_value in replay_config["random_seeds"]
        )
        for strategy, random_seed, sequence_variant in sequence_specs:
            metrics, history = _run_sequence(
                seed=partitions["development_seed"],
                pool=partitions["development_pool"],
                validation=partitions["development_validation"],
                strategy=strategy,
                random_seed=int(random_seed),
                identifier=identifier,
                target=target,
                groups=groups,
                features=features,
                group_column=group_column,
                max_cost=int(replay_config["max_label_cost"]),
                models=replay_config["evaluation_models"],
            )
            sequence_id = f"replay_{replay_index}:{sequence_variant}"
            for metric in metrics:
                result_rows.append(
                    {
                        "replay": replay_index,
                        "salt": salt,
                        "sequence_id": sequence_id,
                        "strategy": strategy,
                        "random_seed": int(random_seed),
                        **metric,
                    }
                )
            for row in history:
                history_rows.append(
                    {
                        "replay": replay_index,
                        "salt": salt,
                        "sequence_id": sequence_id,
                        "strategy": strategy,
                        "random_seed": int(random_seed),
                        **row,
                    }
                )

    results = pd.DataFrame(result_rows)
    history = pd.DataFrame(history_rows)
    partitions_frame = pd.DataFrame(partition_rows)
    summary = _summary(results)

    diagnostics: dict[str, Any] = {
        "replay_id": replay_config["replay_id"],
        "execution_status": "development_replay_completed",
        "development_rows": int(len(development)),
        "replay_count": int(len(replay_config["replay_salts"])),
        "random_replicates_per_replay": int(len(replay_config["random_seeds"])),
        "benchmark_v1_locked_test_read": False,
        "policy_v2_freeze_authorized": False,
        "scientific_evidence_level": "DevelopmentDiagnostic",
        "next_stage": (
            "Use these non-locked replay diagnostics to predeclare a policy-v2 candidate and "
            "independent evaluation source; do not evaluate policy-v2 on benchmark-v1 locked data."
        ),
    }

    output_paths = {
        "sequence_model_results": "sequence_model_results.csv",
        "selection_history": "selection_history.csv",
        "partition_summary": "partition_summary.csv",
        "strategy_model_summary": "strategy_model_summary.csv",
        "diagnostic_summary": "diagnostic_summary.json",
    }
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(benchmark_root, benchmark_config_resolved, replay_config_resolved),
        recognized_markers=(MANIFEST_NAME,),
    ) as staging:
        _write_text(staging / output_paths["sequence_model_results"], _csv_text(results))
        _write_text(staging / output_paths["selection_history"], _csv_text(history))
        _write_text(staging / output_paths["partition_summary"], _csv_text(partitions_frame))
        _write_text(staging / output_paths["strategy_model_summary"], _csv_text(summary))
        _write_text(
            staging / output_paths["diagnostic_summary"],
            json.dumps(diagnostics, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        hashes = {key: _sha256_file(staging / relative) for key, relative in output_paths.items()}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "replay_id": replay_config["replay_id"],
            "execution_status": "development_replay_completed",
            "source_benchmark_id": replay_config["source_benchmark_id"],
            "benchmark_manifest_sha256": _sha256_file(benchmark_root / "benchmark_manifest.json"),
            "benchmark_config_sha256": _sha256_file(benchmark_config_resolved),
            "replay_config_sha256": _sha256_file(replay_config_resolved),
            "development_source": {
                "rows": int(len(development)),
                "partitions_used": ["seed_evidence", "acquisition_pool"],
                "locked_test_read": False,
                "locked_test_target_used": False,
            },
            "design": {
                "replay_count": len(replay_config["replay_salts"]),
                "random_replicates_per_replay": len(replay_config["random_seeds"]),
                "max_label_cost": replay_config["max_label_cost"],
                "partition_group_column": group_column,
                "required_disjoint_group_columns": groups,
                "target_used_for_partition_assignment": False,
                "strategy_class": "frozen benchmark-v1 strategy implementations",
            },
            "outputs": output_paths,
            "output_sha256": hashes,
            "scientific_boundary": replay_config["scientific_boundary"],
            "scientific_evidence_created": False,
            "policy_v2_freeze_authorized": False,
        }
        _write_text(
            staging / MANIFEST_NAME,
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    return {**diagnostics, "outputs": output_paths}
