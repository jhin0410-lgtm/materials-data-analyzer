"""Explicit registry for scientific feature-candidate metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from .domain_knowledge import DomainKnowledgeRegistry, build_default_domain_knowledge_registry
from .scientific_constraint_registry import (
    ScientificConstraintRegistry,
    build_default_scientific_constraint_registry,
)
from .scientific_feature_candidates import ScientificFeatureCandidate, default_scientific_feature_candidates
from .units import UnitRegistry, build_default_unit_registry


@dataclass
class ScientificFeatureRegistry:
    constraint_registry: ScientificConstraintRegistry
    knowledge_registry: DomainKnowledgeRegistry
    unit_registry: UnitRegistry
    _features: dict[str, ScientificFeatureCandidate] = field(default_factory=dict)

    def register(self, candidate: ScientificFeatureCandidate) -> None:
        if candidate.feature_id in self._features:
            raise ValueError(f"duplicate scientific feature_id: {candidate.feature_id}")
        self.knowledge_registry.get(candidate.knowledge_pack_id)
        for constraint_id in candidate.source_constraint_ids:
            self.constraint_registry.get(constraint_id)
        for variable, unit_id in candidate.required_units.items():
            if variable not in candidate.required_variables:
                raise ValueError(f"required unit declared for unknown feature variable {variable}")
            self.unit_registry.get(unit_id)
        if candidate.output_unit:
            self.unit_registry.get(candidate.output_unit)
        self._features[candidate.feature_id] = candidate

    def get(self, feature_id: str) -> ScientificFeatureCandidate:
        try:
            return self._features[feature_id]
        except KeyError as exc:
            raise KeyError(f"unknown scientific feature_id: {feature_id}") from exc

    def list_features(
        self,
        *,
        domain: str | None = None,
        eligibility_status: str | None = None,
        validation_status: str | None = None,
    ) -> list[ScientificFeatureCandidate]:
        features = self._features.values()
        if domain is not None:
            features = [feature for feature in features if feature.domain == domain]
        if eligibility_status is not None:
            features = [feature for feature in features if feature.eligibility_status == eligibility_status]
        if validation_status is not None:
            features = [feature for feature in features if feature.validation_status == validation_status]
        return [self._features[key] for key in sorted(feature.feature_id for feature in features)]

    def snapshot(
        self,
        *,
        domain: str | None = None,
        eligibility_status: str | None = None,
        validation_status: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            feature.to_dict()
            for feature in self.list_features(
                domain=domain,
                eligibility_status=eligibility_status,
                validation_status=validation_status,
            )
        ]

    def validate(self) -> dict[str, object]:
        errors: list[str] = []
        for feature in self.list_features():
            try:
                for constraint_id in feature.source_constraint_ids:
                    self.constraint_registry.get(constraint_id)
                self.knowledge_registry.get(feature.knowledge_pack_id)
                for unit_id in feature.required_units.values():
                    self.unit_registry.get(unit_id)
                if feature.output_unit:
                    self.unit_registry.get(feature.output_unit)
            except (KeyError, ValueError) as exc:
                errors.append(f"{feature.feature_id}: {exc}")
        return {
            "valid": not errors,
            "errors": errors,
            "feature_count": len(self._features),
            "registry_version": "2.1.5",
        }


def build_default_scientific_feature_registry(
    constraint_registry: ScientificConstraintRegistry | None = None,
    knowledge_registry: DomainKnowledgeRegistry | None = None,
    unit_registry: UnitRegistry | None = None,
) -> ScientificFeatureRegistry:
    unit_registry = unit_registry or build_default_unit_registry()
    constraint_registry = constraint_registry or build_default_scientific_constraint_registry(unit_registry=unit_registry)
    knowledge_registry = knowledge_registry or build_default_domain_knowledge_registry()
    registry = ScientificFeatureRegistry(constraint_registry, knowledge_registry, unit_registry)
    for candidate in default_scientific_feature_candidates():
        registry.register(candidate)
    return registry
