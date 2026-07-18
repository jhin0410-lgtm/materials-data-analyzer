"""Materials composition feature builders and matched predictive-value checks.

This module implements a bounded v2.2 Materials feature builder.  It computes
explicitly registered composition descriptors only from formula/composition
metadata available at prediction time.  It does not acquire data, call network
APIs, tune models, run SHAP, or select features from target association.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from pymatgen.core import Composition, Element

from .grouped_regression_validation import (
    SplitConfig,
    ValidationConfig,
    default_model_configs,
    evaluate_validation,
    generate_splits,
)


SCHEMA_VERSION = "2.2.1"
GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324
DEFAULT_OUTPUT_DIR = Path("outputs/materials_physics_v2_2")
DEFAULT_COMPOSITION_SOURCES = ("composition_reduced", "composition", "formula_pretty")
PHYSICS_FEATURE_COLUMNS = (
    "atomic_radius_weighted_mean",
    "atomic_radius_weighted_variance",
    "atomic_radius_mismatch",
    "electronegativity_weighted_mean",
    "electronegativity_weighted_variance",
    "electronegativity_mismatch",
    "configurational_mixing_entropy_j_per_mol_k",
    "valence_electron_concentration",
)
CONTROL_FEATURE_COLUMNS = ("number_of_elements",)
METADATA_COLUMNS = (
    "feature_property_coverage",
    "unsupported_element_count",
    "composition_normalization_residual",
)
REQUIRED_FEATURE_ARTIFACT_COLUMNS = (
    "material_id",
    "feature_build_status",
    "composition_parse_status",
    *PHYSICS_FEATURE_COLUMNS,
    *CONTROL_FEATURE_COLUMNS,
    *METADATA_COLUMNS,
)


@dataclass(frozen=True)
class FeatureValue:
    """One computed feature value plus definition metadata."""

    feature_id: str
    column_name: str
    value: float | int | None
    unit: str
    status: str
    role: str
    definition_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "column_name": self.column_name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "role": self.role,
            "definition_version": self.definition_version,
        }


@dataclass(frozen=True)
class FeatureBuildFinding:
    """Row-level or artifact-level feature build finding."""

    finding_id: str
    severity: str
    status: str
    message: str
    row_index: int | None = None
    material_id: str | None = None
    feature_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "row_index": self.row_index,
            "material_id": self.material_id,
            "feature_id": self.feature_id,
        }


@dataclass(frozen=True)
class PropertySourceMetadata:
    """Element-property source metadata used by v2.2 feature builders."""

    source_name: str
    source_version: str
    source_reference: str
    property_table_version: str
    checksum_sha256: str
    supported_elements: tuple[str, ...]
    properties: tuple[dict[str, Any], ...]
    license_note: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_version": self.source_version,
            "source_reference": self.source_reference,
            "property_table_version": self.property_table_version,
            "checksum_sha256": self.checksum_sha256,
            "supported_elements": list(self.supported_elements),
            "properties": list(self.properties),
            "license_note": self.license_note,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class MaterialsFeatureBuildRequest:
    """Request for local Materials physics-feature generation."""

    input_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR
    material_id_column: str = "material_id"
    target_column: str = "energy_above_hull"
    composition_sources: tuple[str, ...] = DEFAULT_COMPOSITION_SOURCES
    local_feature_matrix_path: Path | None = None
    tracked_definition_path: Path = Path("data/processed/materials_physics_v2_2_feature_definitions.csv")
    tracked_property_source_path: Path = Path("data/processed/materials_physics_v2_2_property_source_metadata.json")
    tracked_coverage_path: Path = Path("data/processed/materials_physics_v2_2_feature_coverage_summary.csv")
    tracked_evidence_path: Path = Path("data/processed/materials_physics_v2_2_feature_use_evidence.json")
    overwrite: bool = True


@dataclass(frozen=True)
class MaterialsFeatureBuildResult:
    """Feature build outputs and summaries."""

    feature_matrix: pd.DataFrame
    feature_definitions: pd.DataFrame
    feature_coverage: pd.DataFrame
    findings: tuple[FeatureBuildFinding, ...]
    property_source: PropertySourceMetadata
    summary: dict[str, Any]


@dataclass(frozen=True)
class MaterialsPredictiveComparisonRequest:
    """Request for matched feature-set predictive-value validation."""

    feature_matrix_path: Path
    analysis_ready_path: Path = Path("data/processed/materials_project_v1_3_analysis_ready.csv")
    descriptor_inventory_path: Path = Path("data/processed/materials_project_v1_3_descriptor_inventory.csv")
    ambiguity_summary_path: Path = Path("data/processed/materials_project_v1_3_composition_ambiguity_summary.csv")
    validation_spec_path: Path = Path("data/case_studies/materials_project/validation_spec_v1_3.json")
    output_dir: Path = DEFAULT_OUTPUT_DIR
    tracked_metric_summary_path: Path = Path("data/processed/materials_physics_v2_2_predictive_comparison_summary.csv")
    tracked_decision_path: Path = Path("data/processed/materials_physics_v2_2_predictive_value_decision.json")
    tracked_evidence_path: Path = Path("data/processed/materials_physics_v2_2_feature_use_evidence.json")
    tracked_report_summary_path: Path = Path("data/processed/materials_physics_v2_2_report_summary.md")
    overwrite: bool = True


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate a file SHA-256 without modifying the file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON config must contain an object: {path}")
    return payload


def build_request_from_config(config: dict[str, Any]) -> MaterialsFeatureBuildRequest:
    """Build a feature-build request from a small JSON config."""
    required = ("input_path",)
    missing = [field for field in required if field not in config]
    if missing:
        raise ValueError("missing feature-build config field(s): " + ", ".join(missing))
    return MaterialsFeatureBuildRequest(
        input_path=Path(config["input_path"]),
        output_dir=Path(config.get("output_dir", DEFAULT_OUTPUT_DIR.as_posix())),
        material_id_column=str(config.get("material_id_column", "material_id")),
        target_column=str(config.get("target_column", "energy_above_hull")),
        composition_sources=tuple(config.get("composition_sources", DEFAULT_COMPOSITION_SOURCES)),
        local_feature_matrix_path=Path(config["local_feature_matrix_path"])
        if config.get("local_feature_matrix_path")
        else None,
        tracked_definition_path=Path(
            config.get(
                "tracked_definition_path",
                "data/processed/materials_physics_v2_2_feature_definitions.csv",
            )
        ),
        tracked_property_source_path=Path(
            config.get(
                "tracked_property_source_path",
                "data/processed/materials_physics_v2_2_property_source_metadata.json",
            )
        ),
        tracked_coverage_path=Path(
            config.get(
                "tracked_coverage_path",
                "data/processed/materials_physics_v2_2_feature_coverage_summary.csv",
            )
        ),
        tracked_evidence_path=Path(
            config.get(
                "tracked_evidence_path",
                "data/processed/materials_physics_v2_2_feature_use_evidence.json",
            )
        ),
        overwrite=bool(config.get("overwrite", True)),
    )


def comparison_request_from_config(config: dict[str, Any]) -> MaterialsPredictiveComparisonRequest:
    """Build a predictive comparison request from JSON config."""
    required = ("feature_matrix_path",)
    missing = [field for field in required if field not in config]
    if missing:
        raise ValueError("missing comparison config field(s): " + ", ".join(missing))
    return MaterialsPredictiveComparisonRequest(
        feature_matrix_path=Path(config["feature_matrix_path"]),
        analysis_ready_path=Path(config.get("analysis_ready_path", "data/processed/materials_project_v1_3_analysis_ready.csv")),
        descriptor_inventory_path=Path(config.get("descriptor_inventory_path", "data/processed/materials_project_v1_3_descriptor_inventory.csv")),
        ambiguity_summary_path=Path(config.get("ambiguity_summary_path", "data/processed/materials_project_v1_3_composition_ambiguity_summary.csv")),
        validation_spec_path=Path(config.get("validation_spec_path", "data/case_studies/materials_project/validation_spec_v1_3.json")),
        output_dir=Path(config.get("output_dir", DEFAULT_OUTPUT_DIR.as_posix())),
        tracked_metric_summary_path=Path(
            config.get(
                "tracked_metric_summary_path",
                "data/processed/materials_physics_v2_2_predictive_comparison_summary.csv",
            )
        ),
        tracked_decision_path=Path(
            config.get(
                "tracked_decision_path",
                "data/processed/materials_physics_v2_2_predictive_value_decision.json",
            )
        ),
        tracked_evidence_path=Path(
            config.get(
                "tracked_evidence_path",
                "data/processed/materials_physics_v2_2_feature_use_evidence.json",
            )
        ),
        tracked_report_summary_path=Path(
            config.get(
                "tracked_report_summary_path",
                "data/processed/materials_physics_v2_2_report_summary.md",
            )
        ),
        overwrite=bool(config.get("overwrite", True)),
    )


def feature_definitions() -> pd.DataFrame:
    """Return deterministic v2.2 feature-definition metadata."""
    rows = [
        {
            "feature_id": "materials.atomic_radius_weighted_mean",
            "column_name": "atomic_radius_weighted_mean",
            "role": "physics_informed_feature",
            "formula": "sum(c_i * r_i)",
            "unit": "angstrom",
            "property_source": "pymatgen.core.Element.atomic_radius",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Composition-only scalar; not crystal-structure, phase, or synthesis evidence.",
        },
        {
            "feature_id": "materials.atomic_radius_weighted_variance",
            "column_name": "atomic_radius_weighted_variance",
            "role": "physics_informed_feature",
            "formula": "sum(c_i * (r_i - r_mean)^2)",
            "unit": "angstrom^2",
            "property_source": "pymatgen.core.Element.atomic_radius",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Weighted spread descriptor; not a thermodynamic model.",
        },
        {
            "feature_id": "materials.atomic_radius_mismatch",
            "column_name": "atomic_radius_mismatch",
            "role": "physics_informed_feature",
            "formula": "sqrt(sum(c_i * (1 - r_i / r_mean)^2))",
            "unit": "dimensionless",
            "property_source": "pymatgen.core.Element.atomic_radius",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Dimensionless size-mismatch descriptor; not phase-stability proof.",
        },
        {
            "feature_id": "materials.electronegativity_weighted_mean",
            "column_name": "electronegativity_weighted_mean",
            "role": "physics_informed_feature",
            "formula": "sum(c_i * chi_i)",
            "unit": "Pauling",
            "property_source": "pymatgen.core.Element.X",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Composition-only electronegativity summary.",
        },
        {
            "feature_id": "materials.electronegativity_weighted_variance",
            "column_name": "electronegativity_weighted_variance",
            "role": "physics_informed_feature",
            "formula": "sum(c_i * (chi_i - chi_mean)^2)",
            "unit": "Pauling^2",
            "property_source": "pymatgen.core.Element.X",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Weighted spread descriptor; not bonding mechanism evidence.",
        },
        {
            "feature_id": "materials.electronegativity_mismatch",
            "column_name": "electronegativity_mismatch",
            "role": "physics_informed_feature",
            "formula": "sqrt(sum(c_i * (chi_i - chi_mean)^2))",
            "unit": "Pauling",
            "property_source": "pymatgen.core.Element.X",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Composition-only spread descriptor.",
        },
        {
            "feature_id": "materials.configurational_mixing_entropy",
            "column_name": "configurational_mixing_entropy_j_per_mol_k",
            "role": "physics_informed_feature",
            "formula": "-R * sum(c_i * ln(c_i))",
            "unit": "J/mol/K",
            "property_source": "composition fractions; R=8.31446261815324 J/mol/K",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Ideal configurational entropy only; not full thermodynamic entropy.",
        },
        {
            "feature_id": "materials.valence_electron_concentration",
            "column_name": "valence_electron_concentration",
            "role": "physics_informed_feature",
            "formula": "sum(c_i * VEC_i)",
            "unit": "electrons/atom",
            "property_source": "pymatgen.core.Element.group with documented VEC convention",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Group-based VEC convention; not oxidation-state or bonding-state resolved.",
        },
        {
            "feature_id": "materials.number_of_elements",
            "column_name": "number_of_elements",
            "role": "control_composition_feature",
            "formula": "count(unique elements)",
            "unit": "count",
            "property_source": "parsed composition",
            "definition_version": SCHEMA_VERSION,
            "interpretation_limit": "Simple composition control feature, not overclaimed as physics evidence.",
        },
    ]
    return pd.DataFrame(rows)


def get_feature_definition(feature_id: str) -> dict[str, Any]:
    """Inspect one registered v2.2 feature builder."""
    definitions = feature_definitions()
    match = definitions[definitions["feature_id"].eq(feature_id)]
    if match.empty:
        raise KeyError(f"unknown materials physics feature_id: {feature_id}")
    return match.iloc[0].to_dict()


def parse_composition_value(value: Any) -> tuple[Composition | None, str]:
    """Parse a composition value without silent fallback side effects."""
    if value is None or pd.isna(value):
        return None, "missing_value"
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        parsed = value
    try:
        if isinstance(parsed, dict):
            cleaned = {str(key): float(amount) for key, amount in parsed.items() if float(amount) > 0}
            return (Composition(cleaned), "parsed") if cleaned else (None, "empty_mapping")
        if isinstance(parsed, str) and parsed.strip():
            composition = Composition(parsed.strip())
            if not composition.elements or composition.num_atoms <= 0:
                return None, "parse_error:empty_composition"
            return composition, "parsed"
    except Exception as exc:
        return None, f"parse_error:{type(exc).__name__}"
    return None, "unsupported_value"


def parse_composition_from_row(
    row: pd.Series,
    *,
    composition_sources: Iterable[str] = DEFAULT_COMPOSITION_SOURCES,
) -> tuple[Composition | None, str, tuple[str, ...]]:
    """Parse one row using declared source priority."""
    issues: list[str] = []
    for source in composition_sources:
        composition, status = parse_composition_value(row.get(source))
        if composition is not None:
            return composition, source, tuple(issues)
        issues.append(f"{source}:{status}")
    return None, "none", tuple(issues + ["composition_unavailable"])


def normalized_atomic_fractions(composition: Composition) -> dict[str, float]:
    """Return deterministic atomic fractions and keep residual separately."""
    fractional = composition.fractional_composition
    fractions = {
        element.symbol: float(fractional[element])
        for element in sorted(fractional.elements, key=lambda item: item.symbol)
    }
    return fractions


def composition_residual(fractions: dict[str, float]) -> float:
    return float(abs(sum(fractions.values()) - 1.0))


def element_property_value(element_symbol: str, property_name: str) -> float | None:
    """Return one vetted element property or None when unsupported."""
    try:
        element = Element(element_symbol)
    except Exception:
        return None
    if property_name == "atomic_radius":
        value = element.atomic_radius
    elif property_name == "electronegativity":
        value = element.X
    elif property_name == "valence_electron_count":
        return _valence_electron_count(element)
    else:
        raise KeyError(f"unknown element property: {property_name}")
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _valence_electron_count(element: Element) -> float | None:
    """Group-based VEC convention.

    s-block: group 1-2, d-block: group 3-12, p-block: group minus 10.
    f-block elements exposed by pymatgen as group 3 are treated as 3 by this
    convention.  This is a documented descriptor convention, not an
    oxidation-state-resolved valence assignment.
    """
    try:
        group = int(element.group)
    except (TypeError, ValueError):
        return None
    if group <= 0:
        return None
    if group <= 12:
        return float(group)
    if group <= 18:
        return float(group - 10)
    return None


def build_property_source_metadata(observed_elements: Iterable[str] | None = None) -> PropertySourceMetadata:
    """Build deterministic element-property provenance metadata."""
    elements = tuple(sorted(set(observed_elements or [element.symbol for element in Element])))
    rows: list[dict[str, Any]] = []
    for element_symbol in elements:
        rows.append(
            {
                "element": element_symbol,
                "atomic_radius": element_property_value(element_symbol, "atomic_radius"),
                "electronegativity": element_property_value(element_symbol, "electronegativity"),
                "valence_electron_count": element_property_value(element_symbol, "valence_electron_count"),
            }
        )
    checksum = hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()
    try:
        source_version = importlib.metadata.version("pymatgen")
    except importlib.metadata.PackageNotFoundError:
        source_version = "unknown"
    return PropertySourceMetadata(
        source_name="pymatgen.core.Element",
        source_version=source_version,
        source_reference="pymatgen periodic-table metadata accessed through Element attributes",
        property_table_version=f"materials_physics_v2_2_pymatgen_{source_version}",
        checksum_sha256=checksum,
        supported_elements=elements,
        properties=(
            {
                "property_name": "atomic_radius",
                "definition": "Element.atomic_radius as provided by pymatgen; not an inferred ionic radius.",
                "unit": "angstrom",
                "missing_policy": "row unavailable when any constituent element lacks the value",
            },
            {
                "property_name": "electronegativity",
                "definition": "Element.X Pauling electronegativity as provided by pymatgen.",
                "unit": "Pauling",
                "missing_policy": "row unavailable when any constituent element lacks the value",
            },
            {
                "property_name": "valence_electron_count",
                "definition": "Documented group-based VEC convention derived from pymatgen Element.group.",
                "unit": "electrons/atom",
                "missing_policy": "row unavailable when periodic-table group is unavailable",
            },
        ),
        license_note="pymatgen is a project dependency; consult pymatgen project metadata for license terms.",
        limitations=(
            "VEC is a descriptor convention, not an oxidation-state assignment.",
            "Features are composition-only and do not encode crystal structure or calculation settings.",
            "No element-property value is imputed or zero-filled.",
        ),
    )


def compute_feature_values(fractions: dict[str, float]) -> tuple[list[FeatureValue], list[str], float, int]:
    """Compute registered v2.2 feature values for one normalized composition."""
    issues: list[str] = []
    elements = tuple(fractions)
    property_names = ("atomic_radius", "electronegativity", "valence_electron_count")
    property_values: dict[str, dict[str, float | None]] = {
        name: {element: element_property_value(element, name) for element in elements}
        for name in property_names
    }
    unsupported = sorted(
        {
            element
            for name in property_names
            for element, value in property_values[name].items()
            if value is None or not math.isfinite(float(value))
        }
    )
    coverage_denominator = max(len(elements) * len(property_names), 1)
    supported_count = coverage_denominator - sum(
        1
        for name in property_names
        for value in property_values[name].values()
        if value is None or not math.isfinite(float(value))
    )
    coverage = float(supported_count / coverage_denominator)
    if unsupported:
        issues.append("unsupported_element_property:" + ",".join(unsupported))
        return _nan_feature_values(), issues, coverage, len(unsupported)

    radius = {element: float(property_values["atomic_radius"][element]) for element in elements}
    eneg = {element: float(property_values["electronegativity"][element]) for element in elements}
    vec = {element: float(property_values["valence_electron_count"][element]) for element in elements}
    entropy = _configurational_entropy(fractions)
    values = [
        FeatureValue(
            "materials.atomic_radius_weighted_mean",
            "atomic_radius_weighted_mean",
            _weighted_mean(fractions, radius),
            "angstrom",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.atomic_radius_weighted_variance",
            "atomic_radius_weighted_variance",
            _weighted_variance(fractions, radius),
            "angstrom^2",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.atomic_radius_mismatch",
            "atomic_radius_mismatch",
            _radius_mismatch(fractions, radius),
            "dimensionless",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.electronegativity_weighted_mean",
            "electronegativity_weighted_mean",
            _weighted_mean(fractions, eneg),
            "Pauling",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.electronegativity_weighted_variance",
            "electronegativity_weighted_variance",
            _weighted_variance(fractions, eneg),
            "Pauling^2",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.electronegativity_mismatch",
            "electronegativity_mismatch",
            math.sqrt(_weighted_variance(fractions, eneg)),
            "Pauling",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.configurational_mixing_entropy",
            "configurational_mixing_entropy_j_per_mol_k",
            entropy,
            "J/mol/K",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.valence_electron_concentration",
            "valence_electron_concentration",
            _weighted_mean(fractions, vec),
            "electrons/atom",
            "available",
            "physics_informed_feature",
        ),
        FeatureValue(
            "materials.number_of_elements",
            "number_of_elements",
            len(elements),
            "count",
            "available",
            "control_composition_feature",
        ),
    ]
    return values, issues, coverage, 0


def build_feature_matrix(df: pd.DataFrame, request: MaterialsFeatureBuildRequest) -> MaterialsFeatureBuildResult:
    """Build a local row-level feature matrix and compact summaries."""
    rows: list[dict[str, Any]] = []
    findings: list[FeatureBuildFinding] = []
    observed_elements: set[str] = set()
    for row_index, row in df.reset_index(drop=True).iterrows():
        material_id = str(row.get(request.material_id_column, f"row-{row_index}"))
        composition, source, parse_issues = parse_composition_from_row(
            row,
            composition_sources=request.composition_sources,
        )
        base: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_row_index": int(row_index),
            "material_id": material_id,
            "formula_pretty": row.get("formula_pretty", pd.NA),
            "composition_source": source,
            "composition_parse_status": "parsed" if composition is not None else "failed",
            "reduced_formula_group": pd.NA,
            "chemical_system_group": pd.NA,
            "feature_build_status": "unavailable",
            "feature_build_issues": ";".join(parse_issues),
            "feature_property_coverage": 0.0,
            "unsupported_element_count": 0,
            "composition_normalization_residual": pd.NA,
        }
        if request.target_column in row.index:
            base[request.target_column] = row.get(request.target_column)
        if "theoretical" in row.index:
            base["theoretical"] = row.get("theoretical")
        if composition is None:
            base.update({column: np.nan for column in PHYSICS_FEATURE_COLUMNS + CONTROL_FEATURE_COLUMNS})
            rows.append(base)
            findings.append(
                FeatureBuildFinding(
                    "composition_parse_failure",
                    "error",
                    "unavailable",
                    "Composition could not be parsed from declared sources.",
                    int(row_index),
                    material_id,
                )
            )
            continue
        fractions = normalized_atomic_fractions(composition)
        observed_elements.update(fractions)
        residual = composition_residual(fractions)
        feature_values, issues, coverage, unsupported_count = compute_feature_values(fractions)
        base.update(
            {
                "reduced_formula_group": composition.reduced_formula,
                "chemical_system_group": composition.chemical_system,
                "feature_build_status": "generated" if not issues else "unavailable_missing_property",
                "feature_build_issues": ";".join(parse_issues + tuple(issues)),
                "feature_property_coverage": coverage,
                "unsupported_element_count": unsupported_count,
                "composition_normalization_residual": residual,
            }
        )
        for feature in feature_values:
            base[feature.column_name] = feature.value
        rows.append(base)
        if issues:
            findings.append(
                FeatureBuildFinding(
                    "feature_unavailable_missing_property",
                    "warning",
                    "unavailable",
                    ";".join(issues),
                    int(row_index),
                    material_id,
                )
            )
    feature_df = pd.DataFrame(rows)
    definitions = feature_definitions()
    coverage_df = build_feature_coverage_summary(feature_df, definitions)
    property_source = build_property_source_metadata(observed_elements)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "input_rows": int(len(df)),
        "feature_rows": int(len(feature_df)),
        "generated_rows": int(feature_df["feature_build_status"].eq("generated").sum()) if not feature_df.empty else 0,
        "unavailable_rows": int(feature_df["feature_build_status"].ne("generated").sum()) if not feature_df.empty else 0,
        "physics_feature_count": len(PHYSICS_FEATURE_COLUMNS),
        "control_feature_count": len(CONTROL_FEATURE_COLUMNS),
        "observed_element_count": len(observed_elements),
        "feature_property_coverage_min": float(pd.to_numeric(feature_df["feature_property_coverage"]).min()) if not feature_df.empty else np.nan,
        "feature_property_coverage_median": float(pd.to_numeric(feature_df["feature_property_coverage"]).median()) if not feature_df.empty else np.nan,
        "feature_property_coverage_max": float(pd.to_numeric(feature_df["feature_property_coverage"]).max()) if not feature_df.empty else np.nan,
        "claim_boundary": {
            "physics_informed_feature_available": bool(len(PHYSICS_FEATURE_COLUMNS) > 0),
            "physics_informed_feature_used": False,
            "physics_constrained_model": False,
            "hybrid_physics_ml": False,
        },
    }
    return MaterialsFeatureBuildResult(
        feature_matrix=feature_df,
        feature_definitions=definitions,
        feature_coverage=coverage_df,
        findings=tuple(findings),
        property_source=property_source,
        summary=summary,
    )


def run_feature_build(request: MaterialsFeatureBuildRequest) -> dict[str, Any]:
    """Run local feature generation and write local plus compact artifacts."""
    input_sha_before = calculate_file_sha256(request.input_path)
    source = pd.read_csv(request.input_path)
    result = build_feature_matrix(source, request)
    input_sha_after = calculate_file_sha256(request.input_path)
    if input_sha_before != input_sha_after:
        raise RuntimeError("Materials source file changed during feature build.")

    output_dir = request.output_dir
    feature_matrix_path = request.local_feature_matrix_path or output_dir / "materials_physics_v2_2_feature_matrix.csv"
    manifest_path = output_dir / "materials_physics_v2_2_feature_manifest.json"
    findings_path = output_dir / "materials_physics_v2_2_feature_findings.csv"
    _write_csv(result.feature_matrix, feature_matrix_path, overwrite=request.overwrite)
    _write_csv(pd.DataFrame([finding.to_dict() for finding in result.findings]), findings_path, overwrite=request.overwrite)
    _write_csv(result.feature_definitions, request.tracked_definition_path, overwrite=request.overwrite)
    _write_csv(result.feature_coverage, request.tracked_coverage_path, overwrite=request.overwrite)
    _write_json(result.property_source.to_dict(), request.tracked_property_source_path, overwrite=request.overwrite)

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "case_study_id": "materials_project",
        "source_artifact": request.input_path.as_posix(),
        "source_sha256": input_sha_after,
        "feature_matrix": feature_matrix_path.as_posix(),
        "feature_build_status": "success",
        "physics_informed_feature_available": True,
        "physics_informed_feature_used": False,
        "physics_constrained_model": False,
        "hybrid_physics_ml": False,
        "usage_note": "Feature build completed; predictive use is established only by matched comparison output.",
    }
    _write_json(evidence, request.tracked_evidence_path, overwrite=request.overwrite)
    manifest = {
        **result.summary,
        "case_study_id": "materials_project",
        "run_stage": "feature_build",
        "source_artifact": request.input_path.as_posix(),
        "source_sha256_before": input_sha_before,
        "source_sha256_after": input_sha_after,
        "local_outputs": {
            "feature_matrix": feature_matrix_path.as_posix(),
            "findings": findings_path.as_posix(),
            "manifest": manifest_path.as_posix(),
        },
        "tracked_outputs": {
            "definitions": request.tracked_definition_path.as_posix(),
            "property_source": request.tracked_property_source_path.as_posix(),
            "coverage": request.tracked_coverage_path.as_posix(),
            "feature_use_evidence": request.tracked_evidence_path.as_posix(),
        },
        "local_only_policy": "row-level feature matrix and findings remain under outputs/materials_physics_v2_2.",
    }
    _write_json(manifest, manifest_path, overwrite=request.overwrite)
    return manifest


def validate_feature_artifact(path: str | Path) -> dict[str, Any]:
    """Validate a feature matrix artifact for schema and finite values."""
    target = Path(path)
    df = pd.read_csv(target)
    missing = [column for column in REQUIRED_FEATURE_ARTIFACT_COLUMNS if column not in df.columns]
    numeric_columns = list(PHYSICS_FEATURE_COLUMNS + CONTROL_FEATURE_COLUMNS + METADATA_COLUMNS)
    nonfinite: list[str] = []
    for column in numeric_columns:
        if column in df.columns:
            values = pd.to_numeric(df.loc[df["feature_build_status"].eq("generated"), column], errors="coerce")
            if values.isna().any() or not np.isfinite(values).all():
                nonfinite.append(column)
    text = target.read_text(encoding="utf-8", errors="ignore")
    sensitive = _contains_sensitive_or_absolute_path(text)
    return {
        "schema_version": SCHEMA_VERSION,
        "path": target.as_posix(),
        "valid": not missing and not nonfinite and not sensitive,
        "row_count": int(len(df)),
        "generated_rows": int(df["feature_build_status"].eq("generated").sum()) if "feature_build_status" in df else 0,
        "missing_columns": missing,
        "nonfinite_generated_columns": nonfinite,
        "sensitive_or_absolute_path_detected": sensitive,
    }


def run_predictive_comparison(request: MaterialsPredictiveComparisonRequest) -> dict[str, Any]:
    """Run matched baseline/physics/combined predictive-value comparison."""
    input_shas = {
        "feature_matrix": calculate_file_sha256(request.feature_matrix_path),
        "analysis_ready": calculate_file_sha256(request.analysis_ready_path),
        "descriptor_inventory": calculate_file_sha256(request.descriptor_inventory_path),
        "validation_spec": calculate_file_sha256(request.validation_spec_path),
    }
    feature_matrix = pd.read_csv(request.feature_matrix_path)
    analysis = pd.read_csv(request.analysis_ready_path)
    inventory = pd.read_csv(request.descriptor_inventory_path)
    ambiguity = pd.read_csv(request.ambiguity_summary_path)
    spec = load_json(request.validation_spec_path)
    baseline_features = _feature_columns_from_inventory(inventory)
    physics_features = list(PHYSICS_FEATURE_COLUMNS + CONTROL_FEATURE_COLUMNS)
    valid_feature_rows = feature_matrix[feature_matrix["feature_build_status"].eq("generated")].copy()
    matched = analysis.merge(
        valid_feature_rows[["material_id", *physics_features]],
        on="material_id",
        how="inner",
        suffixes=("", "__physics"),
        validate="one_to_one",
    )
    physics_feature_columns = [
        f"{column}__physics" if column in analysis.columns else column
        for column in physics_features
    ]
    analysis_with_ambiguity = _add_ambiguity_group_status(analysis, ambiguity)
    matched = _add_ambiguity_group_status(matched, ambiguity)
    _validate_matched_inputs(matched, baseline_features, physics_feature_columns, spec)

    split_configs = _split_configs_from_spec(spec)
    model_configs = default_model_configs(random_state=int(spec.get("random_state", 42)))
    feature_sets = {
        "original_baseline_full": {
            "df": analysis_with_ambiguity,
            "features": baseline_features,
            "comparison_role": "reference_only_full_v1_3_rows",
        },
        "matched_baseline": {
            "df": matched,
            "features": baseline_features,
            "comparison_role": "primary_matched_baseline",
        },
        "physics_only": {
            "df": matched,
            "features": physics_feature_columns,
            "comparison_role": "primary_physics_only",
        },
        "combined_baseline_physics": {
            "df": matched,
            "features": baseline_features + physics_feature_columns,
            "comparison_role": "primary_combined",
        },
    }
    all_metrics: list[pd.DataFrame] = []
    all_comparisons: list[pd.DataFrame] = []
    all_split_diagnostics: list[pd.DataFrame] = []
    all_screening: list[pd.DataFrame] = []
    prediction_outputs: list[pd.DataFrame] = []
    split_assignment_rows: list[dict[str, Any]] = []
    for feature_set_id, item in feature_sets.items():
        frame = item["df"].copy().reset_index(drop=True)
        config = ValidationConfig(
            identifier_column=spec["identifier_column"],
            target_column=spec["target_column"],
            feature_columns=list(item["features"]),
            split_configs=split_configs,
            model_configs=model_configs,
            theoretical_column="theoretical" if "theoretical" in frame.columns else None,
            formula_group_column="reduced_formula_group",
            chemical_system_group_column="chemical_system_group",
            ambiguity_group_column="ambiguity_group_status",
        )
        outputs = evaluate_validation(
            frame,
            config,
            forbidden_features=spec["forbidden_features"] + spec.get("evaluation_only_columns", []),
        )
        for name in ("metrics", "model_comparison", "split_diagnostics", "screening_metrics", "predictions"):
            outputs[name]["feature_set_id"] = feature_set_id
            outputs[name]["comparison_role"] = item["comparison_role"]
            outputs[name]["feature_count"] = len(item["features"])
        all_metrics.append(outputs["metrics"])
        all_comparisons.append(outputs["model_comparison"])
        all_split_diagnostics.append(outputs["split_diagnostics"])
        all_screening.append(outputs["screening_metrics"])
        prediction_outputs.append(outputs["predictions"])
        if feature_set_id == "matched_baseline":
            split_assignment_rows.extend(_split_assignment_rows(frame, split_configs))

    metrics = pd.concat(all_metrics, ignore_index=True)
    model_comparison = pd.concat(all_comparisons, ignore_index=True)
    split_diagnostics = pd.concat(all_split_diagnostics, ignore_index=True)
    screening = pd.concat(all_screening, ignore_index=True)
    predictions = pd.concat(prediction_outputs, ignore_index=True)
    paired = build_paired_metric_deltas(metrics)
    compact_summary = build_predictive_comparison_summary(model_comparison, paired)
    decision = build_predictive_value_decision(
        feature_matrix=feature_matrix,
        matched=matched,
        summary=compact_summary,
        input_shas=input_shas,
    )

    output_dir = request.output_dir
    paths = {
        "local_metrics": output_dir / "materials_physics_v2_2_fold_metrics.csv",
        "local_predictions": output_dir / "materials_physics_v2_2_predictions.csv",
        "local_model_comparison": output_dir / "materials_physics_v2_2_model_comparison.csv",
        "local_split_diagnostics": output_dir / "materials_physics_v2_2_split_diagnostics.csv",
        "local_screening": output_dir / "materials_physics_v2_2_screening_metrics.csv",
        "local_paired_deltas": output_dir / "materials_physics_v2_2_paired_metric_deltas.csv",
        "local_split_assignments": output_dir / "materials_physics_v2_2_split_assignments.csv",
        "local_manifest": output_dir / "materials_physics_v2_2_comparison_manifest.json",
    }
    _write_csv(metrics, paths["local_metrics"], overwrite=request.overwrite)
    _write_csv(predictions, paths["local_predictions"], overwrite=request.overwrite)
    _write_csv(model_comparison, paths["local_model_comparison"], overwrite=request.overwrite)
    _write_csv(split_diagnostics, paths["local_split_diagnostics"], overwrite=request.overwrite)
    _write_csv(screening, paths["local_screening"], overwrite=request.overwrite)
    _write_csv(paired, paths["local_paired_deltas"], overwrite=request.overwrite)
    _write_csv(pd.DataFrame(split_assignment_rows), paths["local_split_assignments"], overwrite=request.overwrite)
    _write_csv(compact_summary, request.tracked_metric_summary_path, overwrite=request.overwrite)
    _write_json(decision, request.tracked_decision_path, overwrite=request.overwrite)
    report = render_predictive_value_report(decision, compact_summary)
    _write_text(report, request.tracked_report_summary_path, overwrite=request.overwrite)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_study_id": "materials_project",
        "run_stage": "predictive_value_validation",
        "input_shas": input_shas,
        "rows": {
            "feature_matrix_rows": int(len(feature_matrix)),
            "matched_rows": int(len(matched)),
            "analysis_ready_rows": int(len(analysis)),
        },
        "feature_sets": {
            key: {
                "feature_count": len(value["features"]),
                "comparison_role": value["comparison_role"],
            }
            for key, value in feature_sets.items()
        },
        "local_outputs": {key: value.as_posix() for key, value in paths.items()},
        "tracked_outputs": {
            "predictive_comparison_summary": request.tracked_metric_summary_path.as_posix(),
            "predictive_value_decision": request.tracked_decision_path.as_posix(),
            "report_summary": request.tracked_report_summary_path.as_posix(),
        },
        "decision_status": decision["predictive_value_status"],
        "claim_boundary": decision["claim_boundary"],
    }
    _write_json(manifest, paths["local_manifest"], overwrite=request.overwrite)
    _update_feature_use_evidence(request.tracked_evidence_path, decision)
    for name, path in request.__dict__.items():
        if name.endswith("_path") and isinstance(path, Path) and path.exists():
            if _contains_sensitive_or_absolute_path(path.read_text(encoding="utf-8", errors="ignore")):
                raise ValueError(f"sensitive or absolute path detected in output: {path}")
    return manifest


def build_feature_coverage_summary(feature_df: pd.DataFrame, definitions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total = len(feature_df)
    generated = feature_df["feature_build_status"].eq("generated") if "feature_build_status" in feature_df else pd.Series(dtype=bool)
    for _, definition in definitions.iterrows():
        column = str(definition["column_name"])
        if column not in feature_df:
            finite_count = 0
            non_null_count = 0
        else:
            values = pd.to_numeric(feature_df[column], errors="coerce")
            non_null_count = int(values.notna().sum())
            finite_count = int(np.isfinite(values.dropna()).sum())
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "feature_id": definition["feature_id"],
                "column_name": column,
                "role": definition["role"],
                "unit": definition["unit"],
                "row_count": total,
                "generated_row_count": int(generated.sum()) if total else 0,
                "non_null_count": non_null_count,
                "finite_count": finite_count,
                "coverage_rate": float(finite_count / total) if total else 0.0,
                "coverage_status": "complete" if finite_count == total and total else "partial_or_unavailable",
            }
        )
    for status, count in feature_df["feature_build_status"].value_counts(dropna=False).items():
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "feature_id": f"row_status:{status}",
                "column_name": "feature_build_status",
                "role": "quality_metadata",
                "unit": "count",
                "row_count": total,
                "generated_row_count": int(generated.sum()) if total else 0,
                "non_null_count": int(count),
                "finite_count": int(count),
                "coverage_rate": float(count / total) if total else 0.0,
                "coverage_status": "status_count",
            }
        )
    return pd.DataFrame(rows)


def build_paired_metric_deltas(metrics: pd.DataFrame) -> pd.DataFrame:
    """Build fold-level paired deltas against the matched baseline."""
    keys = ["split_strategy", "split_index", "model_variant"]
    baseline = metrics[metrics["feature_set_id"].eq("matched_baseline")].copy()
    rows: list[dict[str, Any]] = []
    for feature_set in ["physics_only", "combined_baseline_physics"]:
        candidate = metrics[metrics["feature_set_id"].eq(feature_set)].copy()
        merged = baseline.merge(
            candidate,
            on=keys,
            suffixes=("_matched_baseline", f"_{feature_set}"),
            how="inner",
        )
        for _, row in merged.iterrows():
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "feature_set_id": feature_set,
                    "split_strategy": row["split_strategy"],
                    "split_index": int(row["split_index"]),
                    "model_variant": row["model_variant"],
                    "r2_delta_vs_matched_baseline": _numeric(row.get(f"r2_{feature_set}")) - _numeric(row.get("r2_matched_baseline")),
                    "mae_improvement_vs_matched_baseline": _numeric(row.get("mae_matched_baseline")) - _numeric(row.get(f"mae_{feature_set}")),
                    "rmse_improvement_vs_matched_baseline": _numeric(row.get("rmse_matched_baseline")) - _numeric(row.get(f"rmse_{feature_set}")),
                    "matched_baseline_r2": _numeric(row.get("r2_matched_baseline")),
                    "candidate_r2": _numeric(row.get(f"r2_{feature_set}")),
                    "matched_baseline_mae": _numeric(row.get("mae_matched_baseline")),
                    "candidate_mae": _numeric(row.get(f"mae_{feature_set}")),
                }
            )
    return pd.DataFrame(rows)


def build_predictive_comparison_summary(model_comparison: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    """Build tracked compact summary from local model-comparison outputs."""
    summary_rows: list[dict[str, Any]] = []
    for _, row in model_comparison.iterrows():
        if row.get("metric") not in {"mae", "rmse", "r2", "spearman"}:
            continue
        summary_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "feature_set_metric",
                "feature_set_id": row["feature_set_id"],
                "split_strategy": row["strategy"],
                "model_variant": row["model_variant"],
                "metric": row["metric"],
                "median": row["median"],
                "mean": row["mean"],
                "min": row["min"],
                "max": row["max"],
                "valid_split_count": row["valid_split_count"],
                "status": "valid",
            }
        )
    for (feature_set, split_strategy, model_variant), group in paired.groupby(
        ["feature_set_id", "split_strategy", "model_variant"]
    ):
        for metric in [
            "r2_delta_vs_matched_baseline",
            "mae_improvement_vs_matched_baseline",
            "rmse_improvement_vs_matched_baseline",
        ]:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            summary_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "paired_delta",
                    "feature_set_id": feature_set,
                    "split_strategy": split_strategy,
                    "model_variant": model_variant,
                    "metric": metric,
                    "median": float(values.median()) if not values.empty else np.nan,
                    "mean": float(values.mean()) if not values.empty else np.nan,
                    "min": float(values.min()) if not values.empty else np.nan,
                    "max": float(values.max()) if not values.empty else np.nan,
                    "valid_split_count": int(len(values)),
                    "status": "valid" if not values.empty else "unavailable",
                }
            )
    return pd.DataFrame(summary_rows)


def build_predictive_value_decision(
    *,
    feature_matrix: pd.DataFrame,
    matched: pd.DataFrame,
    summary: pd.DataFrame,
    input_shas: dict[str, str],
) -> dict[str, Any]:
    """Make a bounded predictive-value decision from compact metrics."""
    generated_rows = int(feature_matrix["feature_build_status"].eq("generated").sum())
    coverage = generated_rows / len(feature_matrix) if len(feature_matrix) else 0.0
    primary_splits = {"reduced_formula_group", "chemical_system_group"}
    combined = summary[
        summary["record_type"].eq("paired_delta")
        & summary["feature_set_id"].eq("combined_baseline_physics")
        & summary["split_strategy"].isin(primary_splits)
        & summary["metric"].eq("mae_improvement_vs_matched_baseline")
    ]
    physics = summary[
        summary["record_type"].eq("paired_delta")
        & summary["feature_set_id"].eq("physics_only")
        & summary["split_strategy"].isin(primary_splits)
        & summary["metric"].eq("mae_improvement_vs_matched_baseline")
    ]
    random_combined = summary[
        summary["record_type"].eq("paired_delta")
        & summary["feature_set_id"].eq("combined_baseline_physics")
        & summary["split_strategy"].eq("random")
        & summary["metric"].eq("mae_improvement_vs_matched_baseline")
    ]
    combined_median = _median_of_medians(combined)
    physics_median = _median_of_medians(physics)
    random_median = _median_of_medians(random_combined)
    status = "no_material_improvement"
    reasons: list[str] = []
    if coverage < 0.95:
        status = "blocked_feature_coverage"
        reasons.append("feature coverage below 0.95")
    elif len(matched) < 100:
        status = "inconclusive_low_sample"
        reasons.append("matched sample below 100 rows")
    elif math.isfinite(combined_median) and combined_median < -1e-9:
        status = "performance_degraded"
        reasons.append("combined matched comparison degrades median primary MAE")
    elif math.isfinite(combined_median) and combined_median > 1e-4 and math.isfinite(physics_median) and physics_median > 0:
        status = "predictive_value_supported"
        reasons.append("physics-only and combined feature sets improve median primary MAE")
    elif math.isfinite(combined_median) and combined_median > 1e-4:
        status = "predictive_value_limited"
        reasons.append("combined feature set improves median primary MAE, but physics-only evidence is limited")
    elif math.isfinite(random_median) and random_median > 1e-4:
        status = "random_only_improvement"
        reasons.append("improvement appears only in optimistic random reference")
    else:
        reasons.append("no material primary group-aware improvement over matched baseline")
    return {
        "schema_version": SCHEMA_VERSION,
        "case_study_id": "materials_project",
        "task": "matched predictive-value validation for composition physics-informed features",
        "target": "energy_above_hull",
        "feature_rows": int(len(feature_matrix)),
        "matched_rows": int(len(matched)),
        "generated_rows": generated_rows,
        "feature_coverage": coverage,
        "primary_splits": sorted(primary_splits),
        "matched_baseline_reference": "same rows, same split/model policy",
        "combined_primary_mae_improvement_median": combined_median,
        "physics_only_primary_mae_improvement_median": physics_median,
        "random_reference_combined_mae_improvement_median": random_median,
        "predictive_value_status": status,
        "reason_codes": reasons,
        "representative_model_selected": False,
        "shap_status": "deferred_not_justified",
        "claim_boundary": {
            "physics_informed_feature_available": True,
            "physics_informed_feature_used": True,
            "physics_constrained_model": False,
            "hybrid_physics_ml": False,
            "df_t_replacement": False,
            "new_material_discovery": False,
        },
        "allowed_claims": [
            "composition-derived physics-informed features were built with documented property provenance",
            "matched feature-set comparisons were run with the existing v1.3 split/model policy",
            "predictive value is bounded by the recorded status and group-aware validation results",
        ],
        "prohibited_claims": [
            "physics-constrained model",
            "hybrid physics ML",
            "DFT replacement",
            "new material discovery",
            "experimental synthesizability",
            "causal mechanism",
            "SHAP or feature importance explanation",
        ],
        "input_shas": input_shas,
    }


def render_predictive_value_report(decision: dict[str, Any], summary: pd.DataFrame) -> str:
    """Render a short tracked Markdown summary."""
    top_rows = summary[
        summary["record_type"].eq("paired_delta")
        & summary["feature_set_id"].eq("combined_baseline_physics")
        & summary["metric"].eq("mae_improvement_vs_matched_baseline")
    ].copy()
    lines = [
        "# Materials Physics Feature Predictive-Value Summary",
        "",
        f"- Status: `{decision['predictive_value_status']}`",
        f"- Matched rows: `{decision['matched_rows']}`",
        f"- Generated feature rows: `{decision['generated_rows']}`",
        f"- Feature coverage: `{decision['feature_coverage']:.6f}`",
        f"- Combined primary median MAE improvement: `{decision['combined_primary_mae_improvement_median']}`",
        f"- Physics-only primary median MAE improvement: `{decision['physics_only_primary_mae_improvement_median']}`",
        "",
        "## Claim Boundary",
        "",
        "- These are `physics_informed_feature_available` and `physics_informed_feature_used` features only.",
        "- They are not a physics-constrained model, hybrid physics ML model, DFT replacement, or discovery claim.",
        "- SHAP and feature-importance interpretation remain deferred.",
        "",
        "## Combined Feature-Set Delta Snapshot",
        "",
        "| Split | Model | Median MAE Improvement | Valid Splits |",
        "| --- | --- | ---: | ---: |",
    ]
    for _, row in top_rows.sort_values(["split_strategy", "model_variant"]).iterrows():
        lines.append(
            f"| {row['split_strategy']} | {row['model_variant']} | {row['median']} | {row['valid_split_count']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _nan_feature_values() -> list[FeatureValue]:
    values = []
    for _, definition in feature_definitions().iterrows():
        values.append(
            FeatureValue(
                str(definition["feature_id"]),
                str(definition["column_name"]),
                np.nan,
                str(definition["unit"]),
                "unavailable",
                str(definition["role"]),
            )
        )
    return values


def _weighted_mean(fractions: dict[str, float], values: dict[str, float]) -> float:
    return float(sum(fractions[element] * values[element] for element in fractions))


def _weighted_variance(fractions: dict[str, float], values: dict[str, float]) -> float:
    mean = _weighted_mean(fractions, values)
    return float(sum(fractions[element] * (values[element] - mean) ** 2 for element in fractions))


def _radius_mismatch(fractions: dict[str, float], radii: dict[str, float]) -> float:
    mean = _weighted_mean(fractions, radii)
    if mean <= 0:
        return np.nan
    return float(math.sqrt(sum(fractions[element] * (1 - radii[element] / mean) ** 2 for element in fractions)))


def _configurational_entropy(fractions: dict[str, float]) -> float:
    values = np.array([value for value in fractions.values() if value > 0], dtype=float)
    return float(-GAS_CONSTANT_J_PER_MOL_K * np.sum(values * np.log(values)))


def _write_csv(df: pd.DataFrame, path: str | Path, *, overwrite: bool) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)


def _write_json(payload: dict[str, Any], path: str | Path, *, overwrite: bool) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(content: str, path: str | Path, *, overwrite: bool) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def _contains_sensitive_or_absolute_path(text: str) -> bool:
    lowered = text.lower()
    credential_markers = (
        "kaggle" + "_key",
        "api" + "_key",
        "pass" + "word",
        "sec" + "ret",
        "tok" + "en=",
    )
    windows_drive_markers = ("c:" + "\\", "c:" + "/")
    return any(marker in lowered for marker in credential_markers) or any(
        marker in lowered for marker in windows_drive_markers
    )


def _feature_columns_from_inventory(inventory: pd.DataFrame) -> list[str]:
    mask = inventory["primary_feature"].astype(str).str.lower().eq("true")
    return inventory.loc[mask, "column_name"].tolist()


def _split_configs_from_spec(spec: dict[str, Any]) -> list[SplitConfig]:
    return [
        SplitConfig("random", "shuffle", None, int(spec["n_splits"]), float(spec["test_size"]), int(spec["random_state"])),
        SplitConfig(
            "reduced_formula_group",
            "group_shuffle",
            "reduced_formula_group",
            int(spec["n_splits"]),
            float(spec["test_size"]),
            int(spec["random_state"]),
        ),
        SplitConfig(
            "chemical_system_group",
            "group_shuffle",
            "chemical_system_group",
            int(spec["n_splits"]),
            float(spec["test_size"]),
            int(spec["random_state"]),
        ),
    ]


def _add_ambiguity_group_status(analysis: pd.DataFrame, ambiguity: pd.DataFrame) -> pd.DataFrame:
    output = analysis.copy()
    ambiguous = set(
        ambiguity.loc[
            ambiguity["ambiguity_flag"].astype(str).str.lower().eq("true"),
            "reduced_formula_group",
        ].astype(str)
    )
    row_counts = dict(zip(ambiguity["reduced_formula_group"].astype(str), ambiguity["row_count"]))
    statuses = []
    for formula in output["reduced_formula_group"].astype(str):
        if formula in ambiguous:
            statuses.append("ambiguous_formula_group")
        elif int(row_counts.get(formula, 0)) <= 1:
            statuses.append("singleton_formula_group")
        else:
            statuses.append("non_ambiguous_formula_group")
    output["ambiguity_group_status"] = statuses
    return output


def _validate_matched_inputs(
    matched: pd.DataFrame,
    baseline_features: list[str],
    physics_features: list[str],
    spec: dict[str, Any],
) -> None:
    if matched.empty:
        raise ValueError("No matched Materials rows with generated physics features.")
    missing = [column for column in baseline_features + physics_features if column not in matched.columns]
    if missing:
        raise ValueError("Matched table missing feature columns: " + ", ".join(missing))
    forbidden = set(spec["forbidden_features"]) | set(spec.get("evaluation_only_columns", [])) | {spec["target_column"]}
    leaked = sorted(set(physics_features).intersection(forbidden))
    if leaked:
        raise ValueError("Physics feature set includes forbidden features: " + ", ".join(leaked))


def _split_assignment_rows(frame: pd.DataFrame, split_configs: list[SplitConfig]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split_config in split_configs:
        for split in generate_splits(frame, split_config):
            if split["status"] != "valid":
                rows.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "split_strategy": split["split_strategy"],
                        "split_index": split["split_index"],
                        "material_id": "",
                        "assignment": "invalid",
                        "status": split["status"],
                        "invalid_reason": split["invalid_reason"],
                    }
                )
                continue
            for assignment, indexes in [("train", split["train_index"]), ("test", split["test_index"])]:
                for idx in indexes:
                    rows.append(
                        {
                            "schema_version": SCHEMA_VERSION,
                            "split_strategy": split["split_strategy"],
                            "split_index": split["split_index"],
                            "material_id": frame.iloc[int(idx)]["material_id"],
                            "assignment": assignment,
                            "status": "valid",
                            "invalid_reason": "",
                        }
                    )
    return rows


def _numeric(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    return numeric if math.isfinite(numeric) else np.nan


def _median_of_medians(rows: pd.DataFrame) -> float:
    if rows.empty:
        return np.nan
    values = pd.to_numeric(rows["median"], errors="coerce").dropna()
    return float(values.median()) if not values.empty else np.nan


def _update_feature_use_evidence(path: Path, decision: dict[str, Any]) -> None:
    if not path.exists():
        return
    payload = load_json(path)
    payload.update(
        {
            "physics_informed_feature_used": True,
            "predictive_value_status": decision["predictive_value_status"],
            "comparison_evidence": {
                "matched_rows": decision["matched_rows"],
                "primary_splits": decision["primary_splits"],
                "combined_primary_mae_improvement_median": decision["combined_primary_mae_improvement_median"],
            },
            "usage_note": "Feature build and matched predictive comparison completed; claim remains bounded.",
        }
    )
    _write_json(payload, path, overwrite=True)
