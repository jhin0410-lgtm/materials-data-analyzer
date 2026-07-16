"""Small Protocol interfaces for future scientific platform adapters."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .quantities import ScientificQuantity
from .scientific_entities import EntityRecord, EntityValidationResult, ScientificEntity
from .uncertainty import UncertaintyPropagationResult


class EntityReader(Protocol):
    def read(self, artifact_ref: str, metadata: Mapping[str, Any]) -> ScientificEntity: ...


class EntitySerializer(Protocol):
    def to_record(self, entity: ScientificEntity) -> EntityRecord: ...


class EntityValidator(Protocol):
    def validate(self, entity: ScientificEntity) -> EntityValidationResult: ...


class ScientificOperator(Protocol):
    operator_id: str

    def applicability(self, inputs: Mapping[str, ScientificEntity | ScientificQuantity]) -> Mapping[str, Any]: ...

    def execute(self, inputs: Mapping[str, ScientificEntity | ScientificQuantity]) -> Mapping[str, Any]: ...


class FeatureBuilder(Protocol):
    feature_builder_id: str

    def build_features(self, entities: tuple[ScientificEntity, ...], parameters: Mapping[str, Any]) -> Mapping[str, Any]: ...


class Predictor(Protocol):
    predictor_id: str

    def predict(self, approved_input: Mapping[str, Any]) -> Mapping[str, Any]: ...


class UncertaintyEstimator(Protocol):
    estimator_id: str

    def propagate(self, quantities: Mapping[str, ScientificQuantity], metadata: Mapping[str, Any]) -> UncertaintyPropagationResult: ...


class ResultRenderer(Protocol):
    renderer_id: str

    def render(self, result: Mapping[str, Any]) -> str: ...


class ArtifactAdapter(Protocol):
    adapter_id: str

    def to_entity(self, artifact: Mapping[str, Any]) -> ScientificEntity: ...

    def from_entity(self, entity: ScientificEntity) -> Mapping[str, Any]: ...


INTERFACE_BOUNDARY = {
    "config_import_paths_allowed": False,
    "explicit_registry_required": True,
    "single_god_base_class": False,
    "raw_dataset_read_in_core": False,
    "model_execution_in_core": False,
}
