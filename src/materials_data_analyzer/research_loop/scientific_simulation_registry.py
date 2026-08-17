"""Code-attested local scientific simulation, sensitivity, and active-learning contracts.

This registry is intentionally not a generic plugin loader. Callables are registered
in-process and attested to the SHA-256 of their defining Python module. Results are
immutable artifacts and enter the existing epistemic graph only as simulation nodes
with non-supporting relations. Physical experiment execution is never available here.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.0"
_TARGET_NODE_TYPES = {"hypothesis", "claim", "conclusion"}
_EVIDENCE_PRODUCING_TYPES = {"evidence", "analysis", "simulation", "experiment"}


class ScientificSimulationRegistryError(ResearchLoopError):
    """Raised when a solver or virtual experiment violates the pinned contract."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def callable_module_sha256(backend: Callable[..., object]) -> str:
    source = inspect.getsourcefile(backend)
    if source is None:
        raise ScientificSimulationRegistryError(
            "solver backend has no attestable Python source file"
        )
    return _sha256_file(Path(source).resolve(strict=True))


@dataclass(frozen=True)
class SolverSpec:
    solver_id: str
    version: str
    backend_qualname: str
    module_sha256: str
    input_units: Mapping[str, str]
    output_name: str
    output_unit: str
    validity_ranges: Mapping[str, tuple[float, float]]
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in (
            "solver_id",
            "version",
            "backend_qualname",
            "output_name",
            "output_unit",
        ):
            if not getattr(self, field).strip():
                raise ScientificSimulationRegistryError(f"{field} must be non-empty")
        if len(self.module_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.module_sha256
        ):
            raise ScientificSimulationRegistryError(
                "module_sha256 must be lowercase SHA-256"
            )
        if not self.input_units:
            raise ScientificSimulationRegistryError("solver inputs must be declared")
        for name, unit in self.input_units.items():
            if not name.strip() or not unit.strip():
                raise ScientificSimulationRegistryError(
                    "input names and units must be non-empty"
                )
        for name, bounds in self.validity_ranges.items():
            if name not in self.input_units:
                raise ScientificSimulationRegistryError(
                    "validity range references undeclared input"
                )
            low, high = bounds
            if not math.isfinite(low) or not math.isfinite(high) or low > high:
                raise ScientificSimulationRegistryError("invalid solver validity range")
        if not self.assumptions or any(not item.strip() for item in self.assumptions):
            raise ScientificSimulationRegistryError("solver assumptions must be explicit")


@dataclass(frozen=True)
class SimulationRequest:
    request_id: str
    solver_id: str
    inputs: Mapping[str, tuple[float, str]]
    upstream_evidence_node_ids: tuple[str, ...]
    target_node_id: str


Backend = Callable[[Mapping[str, float]], tuple[float, float, float]]


class ScientificSimulationRegistry:
    """Registry for source-attested, in-process solver callables only."""

    def __init__(self) -> None:
        self._solvers: dict[str, tuple[SolverSpec, Backend]] = {}

    def register(self, spec: SolverSpec, backend: Backend) -> None:
        if backend.__qualname__ != spec.backend_qualname:
            raise ScientificSimulationRegistryError(
                "backend qualname differs from solver specification"
            )
        if callable_module_sha256(backend) != spec.module_sha256:
            raise ScientificSimulationRegistryError(
                "backend module checksum differs from solver specification"
            )
        existing = self._solvers.get(spec.solver_id)
        if existing is not None and existing[0] != spec:
            raise ScientificSimulationRegistryError(
                "solver_id is already registered differently"
            )
        self._solvers[spec.solver_id] = (spec, backend)

    def _validate_request(
        self, request: SimulationRequest, graph: Mapping[str, object]
    ) -> tuple[SolverSpec, Backend, dict[str, float]]:
        if not request.request_id.strip() or not request.target_node_id.strip():
            raise ScientificSimulationRegistryError(
                "request_id and target_node_id must be non-empty"
            )
        if not request.upstream_evidence_node_ids:
            raise ScientificSimulationRegistryError(
                "simulation requires upstream evidence"
            )
        entry = self._solvers.get(request.solver_id)
        if entry is None:
            raise ScientificSimulationRegistryError("solver is not registered")
        spec, backend = entry
        raw_nodes = graph.get("nodes")
        if not isinstance(raw_nodes, list):
            raise ScientificSimulationRegistryError("epistemic graph nodes are missing")
        node_types = {
            str(item.get("node_id")): str(item.get("node_type"))
            for item in raw_nodes
            if isinstance(item, Mapping)
        }
        if node_types.get(request.target_node_id) not in _TARGET_NODE_TYPES:
            raise ScientificSimulationRegistryError(
                "simulation target must be an existing hypothesis, claim, or conclusion"
            )
        for node_id in request.upstream_evidence_node_ids:
            if node_types.get(node_id) not in _EVIDENCE_PRODUCING_TYPES:
                raise ScientificSimulationRegistryError(
                    "upstream evidence node is absent or not evidence-producing"
                )
        if len(set(request.upstream_evidence_node_ids)) != len(
            request.upstream_evidence_node_ids
        ):
            raise ScientificSimulationRegistryError(
                "upstream evidence node ids must not contain duplicates"
            )
        if set(request.inputs) != set(spec.input_units):
            raise ScientificSimulationRegistryError(
                "request input set differs from solver specification"
            )
        scalars: dict[str, float] = {}
        for name, expected_unit in spec.input_units.items():
            raw_value, unit = request.inputs[name]
            if unit != expected_unit:
                raise ScientificSimulationRegistryError(
                    f"unit mismatch for {name}; explicit conversion required"
                )
            value = float(raw_value)
            if not math.isfinite(value):
                raise ScientificSimulationRegistryError(f"input {name} must be finite")
            bounds = spec.validity_ranges.get(name)
            if bounds is not None and not bounds[0] <= value <= bounds[1]:
                raise ScientificSimulationRegistryError(
                    f"input {name} is outside solver validity range"
                )
            scalars[name] = value
        return spec, backend, scalars

    def evaluate(
        self, request: SimulationRequest, graph: Mapping[str, object]
    ) -> dict[str, object]:
        spec, backend, inputs = self._validate_request(request, graph)
        value, standard_uncertainty, uncertainty_score = backend(inputs)
        for field, number in (
            ("value", value),
            ("standard_uncertainty", standard_uncertainty),
            ("uncertainty_score", uncertainty_score),
        ):
            if not math.isfinite(float(number)):
                raise ScientificSimulationRegistryError(
                    f"solver output {field} must be finite"
                )
        if standard_uncertainty < 0 or not 0 <= uncertainty_score <= 1:
            raise ScientificSimulationRegistryError(
                "solver uncertainty outputs violate contract"
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": request.request_id,
            "solver_id": spec.solver_id,
            "solver_version": spec.version,
            "backend_qualname": spec.backend_qualname,
            "backend_module_sha256": spec.module_sha256,
            "inputs": {
                name: {"value": inputs[name], "unit": spec.input_units[name]}
                for name in sorted(inputs)
            },
            "output": {
                "name": spec.output_name,
                "value": float(value),
                "unit": spec.output_unit,
                "standard_uncertainty": float(standard_uncertainty),
                "uncertainty_score": float(uncertainty_score),
            },
            "upstream_evidence_node_ids": list(request.upstream_evidence_node_ids),
            "target_node_id": request.target_node_id,
            "assumptions": list(spec.assumptions),
            "scientific_boundary": {
                "physical_observation_synthesized": False,
                "physical_evidence_sufficiency_changed": False,
                "claim_support_granted_automatically": False,
            },
        }

    def execute_to_epistemic_artifact(
        self,
        request: SimulationRequest,
        graph: Mapping[str, object],
        *,
        output_path: str | Path,
    ) -> dict[str, object]:
        result = self.evaluate(request, graph)
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (
            json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")
        try:
            with path.open("xb") as handle:
                handle.write(raw)
        except FileExistsError as exc:
            raise ScientificSimulationRegistryError(
                "simulation output artifact already exists"
            ) from exc
        digest = hashlib.sha256(raw).hexdigest()
        node_id = "simulation:" + hashlib.sha256(
            f"{request.request_id}:{digest}".encode("utf-8")
        ).hexdigest()[:24]
        node = {
            "node_id": node_id,
            "node_type": "simulation",
            "statement": (
                f"Registered solver {result['solver_id']} evaluated declared inputs; "
                "the virtual result does not substitute for physical evidence."
            ),
            "execution_status": "completed",
            "artifact_bindings": [
                {"role": "simulation_result", "path": str(path), "sha256": digest}
            ],
            "metadata": result,
        }
        edges = [
            {
                "edge_id": f"edge:{node_id}:tests:{request.target_node_id}",
                "source_node_id": node_id,
                "target_node_id": request.target_node_id,
                "relation": "tests",
                "assessment_level": "proposal",
                "rationale": (
                    "Simulation tests model implications only; no physical support "
                    "is automatically granted."
                ),
                "active": True,
            }
        ]
        for upstream_id in request.upstream_evidence_node_ids:
            edges.append(
                {
                    "edge_id": f"edge:{node_id}:depends:{upstream_id}",
                    "source_node_id": node_id,
                    "target_node_id": upstream_id,
                    "relation": "depends_on",
                    "assessment_level": "proposal",
                    "rationale": (
                        "The simulation declares this exact upstream evidence dependency."
                    ),
                    "active": True,
                }
            )
        return {
            "result": result,
            "node": node,
            "edges": edges,
            "artifact_sha256": digest,
        }


@dataclass(frozen=True)
class SensitivityResult:
    variable: str
    derivative: float
    normalized_sensitivity: float
    step: float


def finite_difference_sensitivity(
    registry: ScientificSimulationRegistry,
    request: SimulationRequest,
    graph: Mapping[str, object],
    *,
    variable: str,
    relative_step: float = 0.01,
) -> SensitivityResult:
    if variable not in request.inputs or relative_step <= 0 or not math.isfinite(
        relative_step
    ):
        raise ScientificSimulationRegistryError(
            "invalid sensitivity variable or step"
        )
    base_value, base_unit = request.inputs[variable]
    step = max(abs(float(base_value)) * relative_step, 1e-12)

    def shifted(delta: float, suffix: str) -> SimulationRequest:
        values = dict(request.inputs)
        values[variable] = (float(base_value) + delta, base_unit)
        return SimulationRequest(
            request_id=request.request_id + suffix,
            solver_id=request.solver_id,
            inputs=values,
            upstream_evidence_node_ids=request.upstream_evidence_node_ids,
            target_node_id=request.target_node_id,
        )

    plus = registry.evaluate(shifted(step, ":sens:+"), graph)
    minus = registry.evaluate(shifted(-step, ":sens:-"), graph)
    base = registry.evaluate(request, graph)
    derivative = (
        float(plus["output"]["value"]) - float(minus["output"]["value"])
    ) / (2 * step)
    y_scale = max(abs(float(base["output"]["value"])), 1e-12)
    x_scale = max(abs(float(base_value)), step)
    return SensitivityResult(
        variable, derivative, derivative * x_scale / y_scale, step
    )


@dataclass(frozen=True)
class CandidateResearchAction:
    action_id: str
    action_type: str
    expected_information_gain: float
    expected_uncertainty_reduction: float
    cost_units: float


@dataclass(frozen=True)
class ResearchActionDecision:
    selected: CandidateResearchAction | None
    execution_mode: str
    rationale: tuple[str, ...]


def select_information_gain_action(
    candidates: tuple[CandidateResearchAction, ...], *, remaining_budget: float
) -> ResearchActionDecision:
    if not math.isfinite(remaining_budget) or remaining_budget < 0:
        raise ScientificSimulationRegistryError(
            "remaining_budget must be finite and non-negative"
        )
    feasible: list[CandidateResearchAction] = []
    for item in candidates:
        if item.action_type not in {
            "analysis",
            "simulation",
            "physical_experiment",
            "evidence_acquisition",
        }:
            raise ScientificSimulationRegistryError(
                "unsupported research action type"
            )
        values = (
            item.expected_information_gain,
            item.expected_uncertainty_reduction,
            item.cost_units,
        )
        if any(not math.isfinite(value) for value in values):
            raise ScientificSimulationRegistryError(
                "research action values must be finite"
            )
        if not (
            0 <= item.expected_information_gain <= 1
            and 0 <= item.expected_uncertainty_reduction <= 1
            and item.cost_units >= 0
        ):
            raise ScientificSimulationRegistryError(
                "research action values violate declared ranges"
            )
        if item.cost_units <= remaining_budget:
            feasible.append(item)
    if not feasible:
        return ResearchActionDecision(
            None, "blocked", ("no_action_within_remaining_budget",)
        )
    selected = max(
        feasible,
        key=lambda item: (
            (
                item.expected_information_gain
                + item.expected_uncertainty_reduction
            )
            / (1.0 + item.cost_units),
            item.action_id,
        ),
    )
    execution_mode = (
        "human_authorization_required"
        if selected.action_type == "physical_experiment"
        else "policy_bounded_software_action"
    )
    return ResearchActionDecision(
        selected,
        execution_mode,
        (
            "highest_expected_information_and_uncertainty_reduction_per_cost",
            "physical_instrument_execution_is_outside_this_registry"
            if selected.action_type == "physical_experiment"
            else "software_or_acquisition_action_only",
        ),
    )


__all__ = [
    "CandidateResearchAction",
    "ResearchActionDecision",
    "SCHEMA_VERSION",
    "ScientificSimulationRegistry",
    "ScientificSimulationRegistryError",
    "SensitivityResult",
    "SimulationRequest",
    "SolverSpec",
    "callable_module_sha256",
    "finite_difference_sensitivity",
    "select_information_gain_action",
]
