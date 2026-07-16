"""Materials Project acquisition-scope audit and enrichment contracts.

This module reconstructs the existing tracked Materials Project dataset scope
from local artifacts. It does not call the Materials Project API. Existing-ID
structure enrichment is represented as a bounded plan/preview unless a separate
caller explicitly implements credential-gated execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


QUERY_PLAN_SCHEMA_VERSION = "2.2.3"
DEFAULT_ACQUIRED_PATH = "data/processed/materials_project_v1_3_acquired.csv"
DEFAULT_ANALYSIS_READY_PATH = "data/processed/materials_project_v1_3_analysis_ready.csv"
DEFAULT_MANIFEST_PATH = "data/processed/materials_project_v1_3_acquisition_manifest.json"
DEFAULT_DECISION_PATH = "data/processed/materials_physics_v2_2_predictive_value_decision.json"
DEFAULT_SCOPE_SUMMARY_PATH = "data/processed/materials_project_v2_2_acquisition_scope_summary.json"


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def parse_element_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    return re.findall(r"[A-Z][a-z]?", text)


def parse_composition_mapping(value: Any) -> dict[str, float]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return {}
    if isinstance(value, Mapping):
        return {str(key): float(item) for key, item in value.items()}
    text = str(value)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, Mapping):
            return {str(key): float(item) for key, item in parsed.items()}
    except json.JSONDecodeError:
        pass
    return {}


def reduced_composition_key(composition: Mapping[str, float], *, precision: int = 8) -> dict[str, float]:
    positive = {str(key): float(value) for key, value in composition.items() if float(value) > 0}
    if not positive:
        return {}
    min_value = min(positive.values())
    return {key: round(value / min_value, precision) for key, value in sorted(positive.items())}


@dataclass(frozen=True)
class MaterialsProjectFieldSelection:
    requested_fields: tuple[str, ...]
    mandatory_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_fields": list(self.requested_fields),
            "mandatory_fields": list(self.mandatory_fields),
            "optional_fields": list(self.optional_fields),
        }


@dataclass(frozen=True)
class MaterialsProjectQueryPlan:
    query_plan_id: str
    query_plan_version: str
    endpoint: str
    collection: str
    filters: Mapping[str, Any]
    requested_fields: tuple[str, ...]
    expected_entity_types: tuple[str, ...] = ("MaterialCompositionEntity",)
    max_records: int | None = None
    chunk_size: int = 1000
    cache_policy: str = "local_only"
    credential_source: str = "environment_variable:MP_API_KEY"
    network_required: bool = False
    dry_run: bool = True
    provenance_policy: str = "record_manifest_without_credentials"

    def __post_init__(self) -> None:
        if not self.query_plan_id or "/" in self.query_plan_id or "\\" in self.query_plan_id:
            raise ValueError("query_plan_id must be a stable identifier")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.max_records is not None and self.max_records <= 0:
            raise ValueError("max_records must be positive when supplied")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "query_plan_id": self.query_plan_id,
            "query_plan_version": self.query_plan_version,
            "endpoint": self.endpoint,
            "collection": self.collection,
            "filters": _json_safe(dict(self.filters)),
            "requested_fields": list(self.requested_fields),
            "expected_entity_types": list(self.expected_entity_types),
            "max_records": self.max_records,
            "chunk_size": self.chunk_size,
            "cache_policy": self.cache_policy,
            "credential_source": self.credential_source,
            "network_required": self.network_required,
            "dry_run": self.dry_run,
            "provenance_policy": self.provenance_policy,
        }

    def checksum(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaterialsProjectAcquisitionManifest:
    source_system: str
    endpoint: str
    query_plan_checksum: str
    requested_fields: tuple[str, ...]
    execution_status: str
    material_count: int
    source_sha256: str | None = None
    database_version: str | None = None
    client_versions: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "source_system": self.source_system,
            "endpoint": self.endpoint,
            "query_plan_checksum": self.query_plan_checksum,
            "requested_fields": list(self.requested_fields),
            "execution_status": self.execution_status,
            "material_count": self.material_count,
            "source_sha256": self.source_sha256,
            "database_version": self.database_version,
            "client_versions": dict(self.client_versions),
        }


@dataclass(frozen=True)
class MaterialsProjectEnrichmentRequest:
    mode: str
    material_ids: tuple[str, ...]
    requested_fields: tuple[str, ...]
    max_records: int
    execute: bool = False
    network_required: bool = True

    def __post_init__(self) -> None:
        if self.mode not in {"audit_existing", "enrich_existing_ids", "expand_query_universe"}:
            raise ValueError(f"unsupported enrichment mode: {self.mode}")
        if self.execute and self.mode != "enrich_existing_ids":
            raise ValueError("only enrich_existing_ids can be executed")
        if self.max_records <= 0:
            raise ValueError("max_records must be positive")
        if len(self.material_ids) > self.max_records:
            raise ValueError("material_ids exceed max_records")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "mode": self.mode,
            "material_id_count": len(self.material_ids),
            "material_ids_preview": list(self.material_ids[:5]),
            "requested_fields": list(self.requested_fields),
            "max_records": self.max_records,
            "execute": self.execute,
            "network_required": self.network_required,
        }


@dataclass(frozen=True)
class MaterialsProjectEnrichmentResult:
    status: str
    requested_count: int
    acquired_count: int = 0
    missing_count: int = 0
    output_policy: str = "local_only"
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "status": self.status,
            "requested_count": self.requested_count,
            "acquired_count": self.acquired_count,
            "missing_count": self.missing_count,
            "output_policy": self.output_policy,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def query_plan_from_existing_manifest(manifest: Mapping[str, Any]) -> MaterialsProjectQueryPlan:
    parameters = manifest.get("exact_query_parameters", {})
    fields = tuple(str(item) for item in manifest.get("exact_requested_fields", ()))
    filters = {key: value for key, value in parameters.items() if key != "fields"}
    return MaterialsProjectQueryPlan(
        query_plan_id="materials_project_v1_3_fe_si_containing_summary",
        query_plan_version="1.3",
        endpoint=str(manifest.get("query_method", "MPRester.materials.summary.search")),
        collection=str(manifest.get("endpoint", "materials.summary")),
        filters=filters,
        requested_fields=fields,
        expected_entity_types=("MaterialCompositionEntity", "ScientificQuantity"),
        max_records=None,
        chunk_size=int(parameters.get("chunk_size", 1000)),
        cache_policy="tracked_compact_manifest_local_full_table",
        credential_source="environment_variable:MP_API_KEY",
        network_required=bool(manifest.get("network_called", False)),
        dry_run=False,
        provenance_policy="exact_query_manifest_without_credentials",
    )


def load_materials_project_artifacts(root: Path | str = ".") -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    root_path = Path(root)
    acquired = pd.read_csv(root_path / DEFAULT_ACQUIRED_PATH)
    analysis_ready = pd.read_csv(root_path / DEFAULT_ANALYSIS_READY_PATH)
    manifest = _read_json(root_path / DEFAULT_MANIFEST_PATH)
    return acquired, analysis_ready, manifest


def audit_current_materials_scope(root: Path | str = ".") -> dict[str, Any]:
    root_path = Path(root)
    if not (root_path / DEFAULT_ACQUIRED_PATH).exists() or not (root_path / DEFAULT_ANALYSIS_READY_PATH).exists():
        fallback_path = root_path / DEFAULT_SCOPE_SUMMARY_PATH
        if fallback_path.exists():
            return _json_safe(_read_json(fallback_path))
    acquired, analysis_ready, manifest = load_materials_project_artifacts(root_path)
    elements = acquired["elements"].map(parse_element_list)
    element_frequency = Counter(element for row in elements for element in set(row))
    nelements = acquired["nelements"].astype(int)
    target = acquired["energy_above_hull"]
    formula_unique = int(acquired["formula_pretty"].nunique())
    reduced_unique = int(acquired["composition_reduced"].nunique())
    query_plan = query_plan_from_existing_manifest(manifest)
    decision_path = root_path / DEFAULT_DECISION_PATH
    decision = _read_json(decision_path)
    shas = {
        "acquired": _sha256_path(root_path / DEFAULT_ACQUIRED_PATH),
        "analysis_ready": _sha256_path(root_path / DEFAULT_ANALYSIS_READY_PATH),
        "raw_jsonl": _sha256_path(root_path / "data/processed/materials_project_v1_3_raw.jsonl"),
        "predictive_value_decision": _sha256_path(decision_path),
    }
    summary = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "audit_id": "materials_project_v2_2_acquisition_scope_audit",
        "lineage_verdict": "exact_query_reconstructed",
        "dataset_scope_verdict": "fe_si_containing_multinary_modeling_subset",
        "fe_si_binary_only": False,
        "row_count": int(len(acquired)),
        "analysis_ready_row_count": int(len(analysis_ready)),
        "unique_material_id_count": int(acquired["material_id"].nunique()),
        "missing_material_id_count": int(acquired["material_id"].isna().sum()),
        "unique_formula_count": formula_unique,
        "unique_reduced_formula_count": reduced_unique,
        "unique_chemical_system_count": int(acquired["chemsys"].nunique()),
        "unique_element_count": int(len(element_frequency)),
        "element_frequency": dict(sorted(element_frequency.items())),
        "nelements_distribution": {str(key): int(value) for key, value in nelements.value_counts().sort_index().items()},
        "scope_distribution": {
            "binary": int((nelements == 2).sum()),
            "ternary": int((nelements == 3).sum()),
            "quaternary_plus": int((nelements >= 4).sum()),
        },
        "duplicated_material_id_count": int(acquired["material_id"].duplicated().sum()),
        "target": {
            "column": "energy_above_hull",
            "unit": "eV/atom",
            "missing_count": int(target.isna().sum()),
            "zero_count": int((target == 0).sum()),
            "summary": {key: float(value) for key, value in target.describe().items()},
        },
        "structure_metadata_availability": {
            column: {
                "non_missing": int(acquired[column].notna().sum()),
                "missing": int(acquired[column].isna().sum()),
            }
            for column in ("symmetry", "density", "volume", "nsites")
            if column in acquired
        },
        "structure_body_availability": {
            "structure_field_requested": "structure" in query_plan.requested_fields,
            "structure_body_rows": 0,
            "status": "not_acquired_in_v1_3_summary_table",
        },
        "query_universe_vs_modeling_subset": {
            "query_universe": "Materials Project summary documents matching elements=[Fe, Si], num_elements=[2,5], deprecated=false, include_gnome=false, target not filtered",
            "returned_query_result_count": int(manifest.get("raw_row_count", len(acquired))),
            "modeling_subset_count": int(len(analysis_ready)),
            "subset_explanation": "All returned rows had material_id and non-null energy_above_hull; descriptor normalization retained 838 rows.",
        },
        "query_plan_checksum": query_plan.checksum(),
        "query_plan": query_plan.to_dict(),
        "manifest_source": {
            "path": DEFAULT_MANIFEST_PATH,
            "materials_project_database_version": manifest.get("materials_project_database_version", "unavailable"),
            "mp_api_version": manifest.get("mp_api_version", "unavailable"),
            "emmet_core_version": manifest.get("emmet_core_version", "unavailable"),
            "pymatgen_version": manifest.get("pymatgen_version", "unavailable"),
            "acquisition_utc_timestamp": manifest.get("acquisition_utc_timestamp", "unavailable"),
            "raw_sha256": manifest.get("raw_sha256"),
            "sorted_table_sha256": manifest.get("sorted_table_sha256"),
        },
        "predictive_value_preservation": {
            "schema_version": decision.get("schema_version"),
            "predictive_value_status": decision.get("predictive_value_status"),
            "representative_model_selected": decision.get("representative_model_selected"),
            "combined_primary_mae_improvement_median": decision.get("combined_primary_mae_improvement_median"),
            "claim_boundary": decision.get("claim_boundary", {}),
        },
        "input_shas": shas,
        "actual_structure_enrichment_status": "unavailable_no_local_api_data",
        "v2_2_3_audit_execution": {
            "network_called": False,
            "model_training_run": False,
            "raw_structure_artifacts_created": False,
        },
        "notes": [
            "The 838 rows are the v1.3 query result and modeling subset, not the entire Materials Project universe.",
            "The dataset is Fe/Si-containing and multinary; only 13 rows are binary Fe-Si.",
            "No new network/API acquisition is performed by this audit.",
        ],
    }
    return _json_safe(summary)


def structure_coverage_rows(scope_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "coverage_item": "material_id",
            "available_rows": scope_summary["unique_material_id_count"],
            "total_rows": scope_summary["row_count"],
            "coverage": 1.0,
            "status": "available",
            "notes": "Existing-ID structure enrichment can be keyed by material_id.",
        },
        {
            "coverage_item": "summary_symmetry_metadata",
            "available_rows": scope_summary["structure_metadata_availability"].get("symmetry", {}).get("non_missing", 0),
            "total_rows": scope_summary["row_count"],
            "coverage": 1.0,
            "status": "available_metadata_only",
            "notes": "Summary symmetry metadata is not an independently re-derived symmetry analysis.",
        },
        {
            "coverage_item": "structure_body",
            "available_rows": 0,
            "total_rows": scope_summary["row_count"],
            "coverage": 0.0,
            "status": "unavailable_no_local_api_data",
            "notes": "The v1.3 summary query did not request the full structure field.",
        },
        {
            "coverage_item": "crystal_structure_entities",
            "available_rows": 0,
            "total_rows": scope_summary["row_count"],
            "coverage": 0.0,
            "status": "not_generated_without_structure_enrichment",
            "notes": "No row-level structures or entities are tracked.",
        },
    ]
    return rows


def preview_existing_id_enrichment(
    material_ids: list[str] | tuple[str, ...],
    *,
    max_records: int = 100,
    execute: bool = False,
) -> MaterialsProjectEnrichmentResult:
    if execute:
        return MaterialsProjectEnrichmentResult(
            status="blocked_execution_not_implemented_in_platform_core",
            requested_count=len(material_ids),
            warnings=("Use a credential-gated script layer for actual API calls.",),
        )
    request = MaterialsProjectEnrichmentRequest(
        mode="enrich_existing_ids",
        material_ids=tuple(material_ids[:max_records]),
        requested_fields=(
            "material_id",
            "formula_pretty",
            "composition",
            "composition_reduced",
            "chemsys",
            "nelements",
            "structure",
            "symmetry",
            "density",
            "volume",
            "energy_above_hull",
        ),
        max_records=max_records,
        execute=False,
        network_required=True,
    )
    return MaterialsProjectEnrichmentResult(
        status="preview_only_no_network",
        requested_count=len(request.material_ids),
        warnings=("Structure artifacts remain local-only when acquisition is later executed.",),
    )


def build_broader_expansion_plans() -> list[dict[str, Any]]:
    return [
        {
            "plan_id": "existing_838_material_id_structure_enrichment",
            "scope": "Existing 838 material IDs only",
            "execution_status": "planned_not_executed",
            "priority": "highest",
            "storage_policy": "local_only_structures_tracked_compact_summaries",
            "bias_risk": "inherits v1.3 Fe/Si-containing query bias",
        },
        {
            "plan_id": "same_target_broader_query_universe",
            "scope": "Broader Materials Project query for documents with energy_above_hull and explicit target provenance",
            "execution_status": "plan_only",
            "priority": "future",
            "storage_policy": "requires separate access gate and size review",
            "bias_risk": "query and target availability may bias chemistry distribution",
        },
        {
            "plan_id": "structure_aware_curated_subset",
            "scope": "Target available, structure available, provenance valid, bounded quality filters",
            "execution_status": "plan_only",
            "priority": "future",
            "storage_policy": "local structures plus compact tracked coverage summaries",
            "bias_risk": "structure availability and quality filters may shrink/shift the dataset",
        },
    ]


def write_scope_audit_outputs(root: Path | str = ".") -> dict[str, Any]:
    root_path = Path(root)
    scope = audit_current_materials_scope(root_path)
    processed = root_path / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "materials_project_v2_2_acquisition_scope_summary.json").write_text(
        json.dumps(scope, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    pd.DataFrame(structure_coverage_rows(scope)).to_csv(
        processed / "materials_project_v2_2_structure_coverage_summary.csv",
        index=False,
    )
    adapter_summary = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "adapter_status": "implemented_with_synthetic_and_future_enrichment_inputs",
        "actual_structure_enrichment_status": scope["actual_structure_enrichment_status"],
        "structure_entity_count": 0,
        "structure_integrity_status": "not_run_no_local_structure_data",
        "composition_consistency_status": "not_run_no_local_structure_data",
        "uncertainty_policy": "source_uncertainty_unavailable_not_zero",
        "runtime_object_persistence": False,
    }
    (processed / "materials_project_v2_2_structure_adapter_summary.json").write_text(
        json.dumps(adapter_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return scope
