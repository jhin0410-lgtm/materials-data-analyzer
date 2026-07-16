"""Controlled Materials Project structure enrichment and readiness helpers.

The functions in this module are bounded to existing Materials Project
material IDs. They never construct broad chemistry queries, never overwrite the
v1.3 target, and keep row-level structure artifacts local-only under outputs/.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from .entity_serialization import serialize_entity
from .materials_project_acquisition import (
    DEFAULT_ACQUIRED_PATH,
    DEFAULT_SCOPE_SUMMARY_PATH,
    parse_composition_mapping,
    reduced_composition_key,
)
from .materials_project_adapters import (
    MaterialsProjectStructureAdapter,
    MaterialsProjectSummaryAdapter,
    composition_structure_consistency,
    validate_crystal_structure_entity,
)


SCHEMA_VERSION = "2.2.4"
LOCAL_OUTPUT_ROOT = Path("outputs/materials_project_structure_v2_2")
ALLOWED_ENRICHMENT_FIELDS = (
    "material_id",
    "structure",
    "formula_pretty",
    "composition",
    "composition_reduced",
    "chemsys",
    "nelements",
    "energy_above_hull",
    "density",
    "volume",
    "symmetry",
    "last_updated",
)
TARGET_TOLERANCE = 1e-8


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))
    if hasattr(value, "as_dict"):
        return _json_safe(value.as_dict())
    if hasattr(value, "dict"):
        return _json_safe(value.dict())
    if hasattr(value, "value"):
        return _json_safe(value.value)
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _canonical_sha(payload: Any) -> str:
    canonical = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _write_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(_json_safe(row), sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    temp.replace(path)
    return count


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _chunks(values: list[str], size: int) -> Iterable[tuple[int, list[str]]]:
    for start in range(0, len(values), size):
        yield start // size + 1, values[start : start + size]


def _safe_requested_fields(fields: Iterable[str] | None) -> tuple[str, ...]:
    requested = tuple(dict.fromkeys(str(field) for field in (fields or ALLOWED_ENRICHMENT_FIELDS)))
    unsupported = sorted(set(requested) - set(ALLOWED_ENRICHMENT_FIELDS))
    if unsupported:
        raise ValueError("unsupported Materials Project field(s): " + ", ".join(unsupported))
    if "structure" not in requested or "material_id" not in requested:
        raise ValueError("requested fields must include material_id and structure")
    return requested


def load_existing_material_rows(root: Path | str = ".") -> pd.DataFrame:
    """Load existing v1.3 material rows and sort by material_id."""
    root_path = Path(root)
    acquired_path = root_path / DEFAULT_ACQUIRED_PATH
    if not acquired_path.exists():
        raise FileNotFoundError(
            f"{DEFAULT_ACQUIRED_PATH} is required for actual existing-ID structure enrichment."
        )
    rows = pd.read_csv(acquired_path)
    if "material_id" not in rows.columns:
        raise ValueError("existing Materials Project table is missing material_id")
    if rows["material_id"].isna().any():
        raise ValueError("existing Materials Project table contains missing material_id")
    return rows.sort_values("material_id").reset_index(drop=True)


def existing_material_ids(root: Path | str = ".") -> list[str]:
    rows = load_existing_material_rows(root)
    ids = rows["material_id"].astype(str).drop_duplicates().sort_values().tolist()
    if not ids:
        raise ValueError("no existing material IDs are available")
    return ids


@dataclass(frozen=True)
class StructureEnrichmentPlan:
    mode: str
    material_ids: tuple[str, ...]
    requested_fields: tuple[str, ...]
    chunk_size: int
    max_records: int
    execute: bool
    output_root: str = LOCAL_OUTPUT_ROOT.as_posix()

    def __post_init__(self) -> None:
        if self.mode != "enrich_existing_ids":
            raise ValueError("only enrich_existing_ids mode is allowed")
        if not self.material_ids:
            raise ValueError("material_ids must be non-empty")
        if len(self.material_ids) != len(set(self.material_ids)):
            raise ValueError("material_ids must be unique")
        if self.max_records <= 0 or len(self.material_ids) > self.max_records:
            raise ValueError("material_ids exceed max_records")
        if self.chunk_size <= 0 or self.chunk_size > 100:
            raise ValueError("chunk_size must be in the range 1..100")
        _safe_requested_fields(self.requested_fields)
        output_path = Path(self.output_root)
        if output_path.is_absolute() or ".." in output_path.parts or output_path.parts[:1] != ("outputs",):
            raise ValueError("output_root must be a repository-relative outputs/ path")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "existing_id_only": True,
            "material_id_count": len(self.material_ids),
            "material_ids_preview": list(self.material_ids[:5]),
            "requested_fields": list(self.requested_fields),
            "chunk_size": self.chunk_size,
            "max_records": self.max_records,
            "execute": self.execute,
            "output_root": self.output_root,
            "network_required": bool(self.execute),
            "broad_query_allowed": False,
        }

    def checksum(self) -> str:
        return _canonical_sha(self.to_dict())


def plan_existing_id_structure_enrichment(
    config: Mapping[str, Any],
    *,
    root: Path | str = ".",
    execute_override: bool | None = None,
) -> StructureEnrichmentPlan:
    root_path = Path(root)
    if config.get("mode", "enrich_existing_ids") != "enrich_existing_ids":
        raise ValueError("only enrich_existing_ids mode is allowed")
    existing_ids = set(existing_material_ids(root_path))
    configured_ids = [str(item) for item in config.get("material_ids", ()) if str(item).strip()]
    ids = configured_ids or sorted(existing_ids)
    unknown = sorted(set(ids) - existing_ids)
    if unknown:
        raise ValueError("material_ids contain IDs outside the existing v1.3 dataset")
    ids = sorted(dict.fromkeys(ids))
    max_records = int(config.get("max_records", len(ids)))
    if max_records > len(existing_ids):
        raise ValueError("max_records cannot exceed existing unique material IDs")
    if len(ids) > max_records:
        raise ValueError("configured material_ids exceed max_records")
    execute = bool(config.get("execute", False)) if execute_override is None else bool(execute_override)
    requested_fields = _safe_requested_fields(config.get("requested_fields"))
    return StructureEnrichmentPlan(
        mode="enrich_existing_ids",
        material_ids=tuple(ids),
        requested_fields=requested_fields,
        chunk_size=int(config.get("chunk_size", 50)),
        max_records=max_records,
        execute=execute,
        output_root=str(config.get("output_root", LOCAL_OUTPUT_ROOT.as_posix())),
    )


def preview_structure_enrichment(config: Mapping[str, Any], *, root: Path | str = ".") -> dict[str, Any]:
    try:
        plan = plan_existing_id_structure_enrichment(config, root=root, execute_override=False)
    except FileNotFoundError:
        root_path = Path(root)
        scope_path = root_path / DEFAULT_SCOPE_SUMMARY_PATH
        if not scope_path.exists():
            raise
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
        requested_count = int(scope.get("unique_material_id_count", 0))
        max_records = int(config.get("max_records", requested_count))
        if max_records > requested_count:
            raise ValueError("max_records cannot exceed existing unique material ID count")
        fields = _safe_requested_fields(config.get("requested_fields"))
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "preview_only_no_network_missing_local_id_table",
            "network_called": False,
            "query_plan": {
                "schema_version": SCHEMA_VERSION,
                "mode": "enrich_existing_ids",
                "existing_id_only": True,
                "material_id_count": requested_count,
                "requested_fields": list(fields),
                "chunk_size": int(config.get("chunk_size", 50)),
                "max_records": max_records,
                "execute": False,
                "output_root": str(config.get("output_root", LOCAL_OUTPUT_ROOT.as_posix())),
                "network_required": False,
                "broad_query_allowed": False,
                "material_ids_available_in_clean_checkout": False,
            },
            "query_plan_checksum": _canonical_sha({"requested_count": requested_count, "fields": fields, "max_records": max_records}),
            "credential_value_logged": False,
            "raw_structure_tracked": False,
        }
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "preview_only_no_network",
        "network_called": False,
        "query_plan": plan.to_dict(),
        "query_plan_checksum": plan.checksum(),
        "credential_value_logged": False,
        "raw_structure_tracked": False,
    }


def _serialize_doc(doc: Any) -> dict[str, Any]:
    if hasattr(doc, "model_dump"):
        return _json_safe(doc.model_dump(mode="json"))
    if hasattr(doc, "dict"):
        return _json_safe(doc.dict())
    if isinstance(doc, Mapping):
        return _json_safe(dict(doc))
    return _json_safe({field: getattr(doc, field, None) for field in ALLOWED_ENRICHMENT_FIELDS})


def _make_mp_client() -> Any:
    api_key = os.getenv("MP_API_KEY")
    if not api_key:
        raise RuntimeError("MP_API_KEY is required for --execute structure enrichment")
    try:
        from mp_api.client import MPRester
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("mp-api is required for --execute structure enrichment") from exc
    if "mute_progress_bars" in inspect.signature(MPRester).parameters:
        return MPRester(api_key, mute_progress_bars=True)
    return MPRester(api_key)


def _client_context(client: Any) -> Any:
    return client if hasattr(client, "__enter__") else _NullContext(client)


class _NullContext:
    def __init__(self, value: Any) -> None:
        self.value = value

    def __enter__(self) -> Any:
        return self.value

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        close = getattr(self.value, "close", None)
        if callable(close):
            close()


def run_structure_enrichment(
    config: Mapping[str, Any],
    *,
    root: Path | str = ".",
    execute: bool = False,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run bounded existing-ID structure enrichment into ignored outputs/."""
    root_path = Path(root)
    plan = plan_existing_id_structure_enrichment(config, root=root_path, execute_override=execute)
    output_root = root_path / plan.output_root
    query_plan_path = output_root / "acquisition" / "query_plan.json"
    id_manifest_path = output_root / "acquisition" / "material_ids_manifest.json"
    manifest_path = output_root / "acquisition" / "acquisition_manifest.json"
    chunk_dir = output_root / "acquisition" / "chunks"

    _write_json_atomic(query_plan_path, {"query_plan": plan.to_dict(), "query_plan_checksum": plan.checksum()})
    _write_json_atomic(
        id_manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "material_id_count": len(plan.material_ids),
            "material_ids_checksum": _canonical_sha(list(plan.material_ids)),
            "existing_ids_only": True,
        },
    )
    if not execute:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "preview_only_no_network",
            "network_called": False,
            "requested_count": len(plan.material_ids),
            "returned_count": 0,
            "missing_count": len(plan.material_ids),
            "query_plan_checksum": plan.checksum(),
            "output_root": plan.output_root,
        }
        _write_json_atomic(manifest_path, manifest)
        return manifest

    if client_factory is None:
        client_factory = _make_mp_client
    returned_docs: list[dict[str, Any]] = []
    errors: list[str] = []
    start = time.perf_counter()
    with _client_context(client_factory()) as client:
        summary = client.materials.summary
        for chunk_index, ids in _chunks(list(plan.material_ids), plan.chunk_size):
            chunk_path = chunk_dir / f"structure_chunk_{chunk_index:05d}.jsonl"
            chunk_manifest_path = chunk_path.with_suffix(".manifest.json")
            requested_ids_checksum = _canonical_sha(ids)
            if chunk_path.exists():
                if not chunk_manifest_path.exists():
                    errors.append(f"chunk_{chunk_index:05d}: existing_chunk_missing_manifest")
                    continue
                chunk_manifest = json.loads(chunk_manifest_path.read_text(encoding="utf-8"))
                if chunk_manifest.get("requested_ids_checksum") != requested_ids_checksum:
                    errors.append(f"chunk_{chunk_index:05d}: existing_chunk_query_mismatch")
                    continue
                existing_rows = [json.loads(line) for line in chunk_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                existing_ids = [str(row.get("material_id")) for row in existing_rows if row.get("material_id") is not None]
                unexpected_existing = sorted(set(existing_ids) - set(ids))
                if unexpected_existing:
                    errors.append(f"chunk_{chunk_index:05d}: existing_chunk_unexpected_material_ids")
                    continue
                returned_docs.extend(existing_rows)
                continue
            try:
                docs = summary.search(
                    material_ids=ids,
                    fields=list(plan.requested_fields),
                    all_fields=False,
                    chunk_size=len(ids),
                    num_chunks=1,
                )
            except Exception as exc:  # pragma: no cover - live service condition
                errors.append(f"chunk_{chunk_index:05d}: {type(exc).__name__}")
                continue
            rows = [_serialize_doc(doc) for doc in docs]
            rows = sorted(rows, key=lambda row: str(row.get("material_id", "")))
            returned_chunk_ids = [str(row.get("material_id")) for row in rows if row.get("material_id") is not None]
            unexpected_ids = sorted(set(returned_chunk_ids) - set(ids))
            if unexpected_ids:
                errors.append(f"chunk_{chunk_index:05d}: unexpected_material_ids_returned")
                continue
            if len(returned_chunk_ids) != len(set(returned_chunk_ids)):
                errors.append(f"chunk_{chunk_index:05d}: duplicate_material_ids_returned")
                continue
            _write_jsonl_atomic(chunk_path, rows)
            _write_json_atomic(
                chunk_manifest_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "chunk_index": chunk_index,
                    "requested_count": len(ids),
                    "requested_ids_checksum": requested_ids_checksum,
                    "returned_count": len(rows),
                    "returned_ids_subset_of_requested": True,
                    "chunk_checksum": _canonical_sha(rows),
                },
            )
            returned_docs.extend(rows)
    returned_docs = sorted(returned_docs, key=lambda row: str(row.get("material_id", "")))
    returned_ids = {str(row.get("material_id")) for row in returned_docs if row.get("material_id") is not None}
    missing_ids = sorted(set(plan.material_ids) - returned_ids)
    status = "success" if not errors and not missing_ids else "partial_success" if returned_docs else "failed"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "network_called": True,
        "requested_count": len(plan.material_ids),
        "returned_count": len(returned_docs),
        "missing_count": len(missing_ids),
        "duplicate_returned_id_count": len(returned_docs) - len(returned_ids),
        "query_plan_checksum": plan.checksum(),
        "output_root": plan.output_root,
        "chunk_count": math.ceil(len(plan.material_ids) / plan.chunk_size),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "errors": errors,
        "credential_included": False,
        "absolute_path_included": False,
        "created_at": _utc_now(),
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest


def load_structure_docs(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path)
    if source.is_dir():
        rows: list[dict[str, Any]] = []
        for jsonl_path in sorted(source.rglob("structure_chunk_*.jsonl")):
            rows.extend(json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip())
        return sorted(rows, key=lambda row: str(row.get("material_id", "")))
    if source.suffix == ".jsonl":
        return [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("documents"), list):
        return payload["documents"]
    if isinstance(payload, list):
        return payload
    raise ValueError("structure docs path must be a directory, JSONL file, or JSON list/documents object")


def snapshot_alignment_rows(existing_rows: pd.DataFrame, docs: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    original_by_id = {str(row["material_id"]): row for _, row in existing_rows.iterrows()}
    current_by_id = {str(doc.get("material_id")): doc for doc in docs if doc.get("material_id") is not None}
    rows: list[dict[str, Any]] = []
    for material_id in sorted(original_by_id):
        original = original_by_id[material_id]
        current = current_by_id.get(material_id)
        original_target = _float_or_none(original.get("energy_above_hull"))
        current_target = None if current is None else _float_or_none(current.get("energy_above_hull"))
        if current is None:
            status = "material_id_missing"
        elif original_target is None:
            status = "original_target_missing"
        elif current_target is None:
            status = "current_target_missing"
        else:
            diff = abs(original_target - current_target)
            status = "target_exact_match" if diff == 0 else "target_within_numeric_tolerance" if diff <= TARGET_TOLERANCE else "target_drift"
        rows.append(
            {
                "material_id": material_id,
                "original_target": original_target,
                "current_target": current_target,
                "absolute_difference": None if original_target is None or current_target is None else abs(original_target - current_target),
                "relative_difference": _relative_difference(original_target, current_target),
                "tolerance": TARGET_TOLERANCE,
                "comparison_status": status,
                "source_version_status": "source_version_unavailable",
            }
        )
    return rows


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _relative_difference(original: float | None, current: float | None) -> float | None:
    if original is None or current is None or original == 0:
        return None
    return abs(original - current) / abs(original)


def compact_snapshot_alignment_summary(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row["comparison_status"]) for row in rows)
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "comparison_status": status,
            "row_count": int(count),
            "tracked_row_level_targets": False,
            "original_target_overwritten": False,
        }
        for status, count in sorted(counts.items())
    ]


def convert_structure_docs_to_entities(
    docs: list[Mapping[str, Any]],
    existing_rows: pd.DataFrame,
    *,
    output_path: Path,
    acquisition_manifest_ref: str = "outputs/materials_project_structure_v2_2/acquisition/acquisition_manifest.json",
) -> dict[str, Any]:
    by_id = {str(row["material_id"]): row.to_dict() for _, row in existing_rows.iterrows()}
    adapter = MaterialsProjectStructureAdapter()
    summary_adapter = MaterialsProjectSummaryAdapter()
    status_counts: Counter[str] = Counter()
    consistency_counts: Counter[str] = Counter()
    entity_rows = []
    for doc in sorted(docs, key=lambda row: str(row.get("material_id", ""))):
        material_id = str(doc.get("material_id", ""))
        structure = doc.get("structure")
        if not material_id or structure is None:
            status_counts["adapter_failure"] += 1
            continue
        summary_row = {**by_id.get(material_id, {}), **dict(doc)}
        try:
            composition_entity = summary_adapter.to_composition_entity(summary_row)
            structure_entity = adapter.to_crystal_structure_entity(
                material_id=material_id,
                structure=structure,
                summary_row=summary_row,
                acquisition_manifest_ref=acquisition_manifest_ref,
            )
            integrity = validate_crystal_structure_entity(structure_entity)
            consistency = composition_structure_consistency(composition_entity, structure_entity)
        except (KeyError, TypeError, ValueError) as exc:
            status_counts["adapter_failure"] += 1
            entity_rows.append({"material_id": material_id, "status": "adapter_failure", "error": type(exc).__name__})
            continue
        status_counts[integrity["status"]] += 1
        consistency_counts[consistency["status"]] += 1
        record = serialize_entity(structure_entity)
        record["source_record_checksum"] = _canonical_sha(doc)
        record["integrity_status"] = integrity["status"]
        record["composition_consistency_status"] = consistency["status"]
        entity_rows.append(record)
    count = _write_jsonl_atomic(output_path, entity_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "entities_written",
        "entity_count": count,
        "integrity_status_counts": dict(sorted(status_counts.items())),
        "composition_consistency_counts": dict(sorted(consistency_counts.items())),
        "output_policy": "local_only",
    }


def summarize_v2_2_4_readiness(
    *,
    requested_count: int,
    docs: list[Mapping[str, Any]],
    alignment_rows: list[Mapping[str, Any]],
    entity_summary: Mapping[str, Any] | None,
    descriptor_summary: Mapping[str, Any] | None,
    graph_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    returned_ids = {str(doc.get("material_id")) for doc in docs if doc.get("material_id") is not None}
    structure_available = sum(1 for doc in docs if doc.get("structure") is not None)
    alignment_counts = Counter(str(row["comparison_status"]) for row in alignment_rows)
    aligned = alignment_counts["target_exact_match"] + alignment_counts["target_within_numeric_tolerance"]
    valid_entities = 0 if entity_summary is None else int(entity_summary.get("integrity_status_counts", {}).get("valid", 0))
    descriptor_eligible = 0 if descriptor_summary is None else int(descriptor_summary.get("descriptor_eligible_entities", 0))
    graph_eligible = 0 if graph_summary is None else int(graph_summary.get("graph_eligible_entities", 0))
    if not docs:
        decision = "blocked_no_api_data"
    elif aligned == 0:
        decision = "blocked_snapshot_drift"
    elif valid_entities == 0:
        decision = "blocked_integrity_failures"
    elif descriptor_eligible == 0:
        decision = "blocked_structure_coverage"
    else:
        decision = "structure_prediction_ready_with_restrictions"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "requested_unique_material_ids": requested_count,
        "api_returned_ids": len(returned_ids),
        "missing_ids": max(0, requested_count - len(returned_ids)),
        "structure_available": structure_available,
        "snapshot_aligned_count": aligned,
        "valid_structure_entities": valid_entities,
        "descriptor_eligible_entities": descriptor_eligible,
        "graph_eligible_entities": graph_eligible,
        "structure_prediction_readiness": decision,
        "model_training_run": False,
        "predictive_claim_made": False,
        "original_target_overwritten": False,
    }
