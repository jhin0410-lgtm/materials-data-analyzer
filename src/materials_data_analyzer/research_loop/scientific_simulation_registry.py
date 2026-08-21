"""Simulation contracts, structural sensitivity, and bounded physics registration.

The registry never executes a solver. Execution remains behind the repository's independent
authorization, pinned-request, and typed-executor chain. A contract may declare
``physics_solver=True`` only when its governing equation, numerical method, unit contract,
stability rule, and numerical-validation contract are all explicit and attestable.
"""
from __future__ import annotations

import hashlib
import inspect
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .design_simulation import simulate_design_structure
from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.1"


class ScientificSimulationRegistryError(ResearchLoopError):
    """Raised when a simulation planning contract is scientifically unsafe."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def callable_module_sha256(callable_object: object) -> str:
    source = inspect.getsourcefile(callable_object)
    if source is None:
        raise ScientificSimulationRegistryError(
            "simulation implementation has no attestable Python source file"
        )
    return _sha256_file(Path(source).resolve(strict=True))


@dataclass(frozen=True)
class SolverContract:
    solver_id: str
    version: str
    implementation_qualname: str
    implementation_module_sha256: str
    action_type: str
    action_version: str
    assumptions: tuple[str, ...]
    execution_route: str = "existing_independent_authorization_and_typed_executor_chain"
    physics_solver: bool = False
    governing_equation: str | None = None
    numerical_method: str | None = None
    unit_contract: str | None = None
    stability_contract: str | None = None
    numerical_validation_contract: str | None = None
    empirical_validation_status: str = "not_established"

    def __post_init__(self) -> None:
        for field in (
            "solver_id",
            "version",
            "implementation_qualname",
            "action_type",
            "action_version",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ScientificSimulationRegistryError(f"{field} must be non-empty")
        digest = self.implementation_module_sha256
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ScientificSimulationRegistryError(
                "implementation_module_sha256 must be lowercase SHA-256"
            )
        if not self.assumptions or any(not item.strip() for item in self.assumptions):
            raise ScientificSimulationRegistryError("solver assumptions must be explicit")
        if self.execution_route != "existing_independent_authorization_and_typed_executor_chain":
            raise ScientificSimulationRegistryError("a second simulation executor is not allowed")
        audit_fields = (
            self.governing_equation,
            self.numerical_method,
            self.unit_contract,
            self.stability_contract,
            self.numerical_validation_contract,
        )
        if self.physics_solver:
            if any(not isinstance(item, str) or not item.strip() for item in audit_fields):
                raise ScientificSimulationRegistryError(
                    "physics_solver=true requires governing equation, numerical method, units, stability, and numerical validation contracts"
                )
            if self.empirical_validation_status not in {"not_established", "established"}:
                raise ScientificSimulationRegistryError("unsupported empirical_validation_status")
        else:
            if any(item is not None for item in audit_fields):
                raise ScientificSimulationRegistryError(
                    "non-physics structural contracts must not carry physics audit fields"
                )
            if self.empirical_validation_status != "not_established":
                raise ScientificSimulationRegistryError(
                    "non-physics solver cannot claim empirical validation status"
                )


class SolverContractRegistry:
    """Registry of exact solver contracts; it intentionally has no execute method."""

    def __init__(self) -> None:
        self._contracts: dict[str, SolverContract] = {}

    def register_attested(
        self,
        contract: SolverContract,
        *,
        implementation: object,
    ) -> None:
        qualname = getattr(implementation, "__qualname__", None)
        if qualname != contract.implementation_qualname:
            raise ScientificSimulationRegistryError(
                "implementation qualname differs from solver contract"
            )
        if callable_module_sha256(implementation) != contract.implementation_module_sha256:
            raise ScientificSimulationRegistryError(
                "implementation module checksum differs from solver contract"
            )
        existing = self._contracts.get(contract.solver_id)
        if existing is not None and existing != contract:
            raise ScientificSimulationRegistryError(
                "solver_id is already registered with a different contract"
            )
        self._contracts[contract.solver_id] = contract

    def get(self, solver_id: str) -> SolverContract:
        try:
            return self._contracts[solver_id]
        except KeyError as exc:
            raise ScientificSimulationRegistryError(
                f"solver contract is not registered: {solver_id}"
            ) from exc


def repository_design_simulation_contract() -> SolverContract:
    """Return the attested contract for the response-free structural simulator."""
    return SolverContract(
        solver_id="response_free_structural_design",
        version="1.0",
        implementation_qualname=simulate_design_structure.__qualname__,
        implementation_module_sha256=callable_module_sha256(simulate_design_structure),
        action_type="nist_structural_design_simulation",
        action_version="1.0",
        assumptions=(
            "Only design-matrix structure is evaluated.",
            "No response values, effect sizes, predictions, or physical observations are synthesized.",
            "Expected information gain is not probabilistically quantified.",
        ),
        physics_solver=False,
    )


def repository_heat_conduction_contract() -> SolverContract:
    """Return the attested contract for the first audited continuum-physics solver."""
    from .heat_conduction_solver import (
        HEAT_SOLVER_ACTION_TYPE,
        HEAT_SOLVER_ACTION_VERSION,
        HEAT_SOLVER_ID,
        HEAT_SOLVER_VERSION,
        run_reference_heat_conduction_request,
    )

    return SolverContract(
        solver_id=HEAT_SOLVER_ID,
        version=HEAT_SOLVER_VERSION,
        implementation_qualname=run_reference_heat_conduction_request.__qualname__,
        implementation_module_sha256=callable_module_sha256(run_reference_heat_conduction_request),
        action_type=HEAT_SOLVER_ACTION_TYPE,
        action_version=HEAT_SOLVER_ACTION_VERSION,
        assumptions=(
            "One-dimensional transient heat conduction only.",
            "Thermal properties are constant over space, temperature, and time.",
            "Boundary conditions are fixed-temperature Dirichlet boundaries.",
            "No phase change, latent heat, convection, radiation, heat source, melt flow, or process physics is represented.",
            "Material properties are explicit request inputs and are never inferred or imputed.",
            "Analytical sine-mode comparison establishes numerical reference behavior, not empirical material validity.",
        ),
        physics_solver=True,
        governing_equation="dT/dt = alpha * d2T/dx2",
        numerical_method="explicit FTCS finite difference in 1D",
        unit_contract="strict SI: m, s, K and either m^2/s or W/(m*K), kg/m^3, J/(kg*K)",
        stability_contract="Fourier number alpha*dt/dx^2 <= 0.5; unstable requests are rejected before time marching",
        numerical_validation_contract="single sine eigenmode analytical solution with explicit max-absolute-error tolerance",
        empirical_validation_status="not_established",
    )


def _validate_graph_dependencies(
    graph: Mapping[str, object],
    *,
    upstream_evidence_node_ids: tuple[str, ...],
    target_node_id: str,
) -> None:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise ScientificSimulationRegistryError("epistemic graph nodes are missing")
    node_types = {
        str(item.get("node_id")): str(item.get("node_type"))
        for item in nodes
        if isinstance(item, Mapping)
    }
    if node_types.get(target_node_id) not in {"hypothesis", "claim", "conclusion"}:
        raise ScientificSimulationRegistryError(
            "simulation target must be an existing hypothesis, claim, or conclusion"
        )
    if not upstream_evidence_node_ids:
        raise ScientificSimulationRegistryError("simulation planning requires upstream evidence")
    if len(set(upstream_evidence_node_ids)) != len(upstream_evidence_node_ids):
        raise ScientificSimulationRegistryError("upstream evidence ids must be unique")
    for node_id in upstream_evidence_node_ids:
        if node_types.get(node_id) not in {"evidence", "analysis", "simulation", "experiment"}:
            raise ScientificSimulationRegistryError(
                "upstream dependency is absent or not evidence-producing"
            )


@dataclass(frozen=True)
class SimulationPlanningRequest:
    request_id: str
    solver_id: str
    upstream_evidence_node_ids: tuple[str, ...]
    target_node_id: str


def compile_simulation_action_candidate(
    registry: SolverContractRegistry,
    request: SimulationPlanningRequest,
    graph: Mapping[str, object],
) -> dict[str, Any]:
    """Compile planner-visible simulation work without granting execution authority."""
    if not request.request_id.strip():
        raise ScientificSimulationRegistryError("request_id must be non-empty")
    contract = registry.get(request.solver_id)
    _validate_graph_dependencies(
        graph,
        upstream_evidence_node_ids=request.upstream_evidence_node_ids,
        target_node_id=request.target_node_id,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "action_id": request.request_id,
        "action_class": "simulation",
        "description": f"Run registered solver contract {contract.solver_id} through the existing typed executor.",
        "rationale": (
            "Solver identity and implementation bytes are attested, but execution authority "
            "remains in the existing independent authorization chain."
        ),
        "required_evidence_node_ids": list(request.upstream_evidence_node_ids),
        "target_node_id": request.target_node_id,
        "expected_action_type": contract.action_type,
        "expected_action_version": contract.action_version,
        "execution_mode": "explicit_authorization_required",
        "execution_route": contract.execution_route,
        "execution_performed": False,
        "second_executor_introduced": False,
        "scientific_status_upgrade_authorized": False,
        "physics_solver": contract.physics_solver,
        "physics_audit": {
            "governing_equation": contract.governing_equation,
            "numerical_method": contract.numerical_method,
            "unit_contract": contract.unit_contract,
            "stability_contract": contract.stability_contract,
            "numerical_validation_contract": contract.numerical_validation_contract,
            "empirical_validation_status": contract.empirical_validation_status,
        },
        "assumptions": list(contract.assumptions),
    }


@dataclass(frozen=True)
class StructuralDesignCandidate:
    candidate_id: str
    config: Mapping[str, Any]
    cost_units: float

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ScientificSimulationRegistryError("candidate_id must be non-empty")
        if not math.isfinite(self.cost_units) or self.cost_units < 0:
            raise ScientificSimulationRegistryError("cost_units must be finite and non-negative")


@dataclass(frozen=True)
class StructuralDesignAssessment:
    candidate_id: str
    rank_gain: int
    residual_df_gain: int
    new_unique_cell_count: int
    structural_utility: float
    cost_units: float
    expected_information_gain_status: str = "not_quantified"


def assess_structural_design_candidate(
    candidate: StructuralDesignCandidate,
) -> StructuralDesignAssessment:
    """Reuse the existing response-free simulator and expose only structural proxies."""
    result = simulate_design_structure(candidate.config)
    changes = result["comparison"]["model_changes"]
    rank_gain = sum(max(0, int(item["rank_gain"])) for item in changes)
    residual_df_gain = sum(max(0, int(item["residual_df_gain"])) for item in changes)
    new_cells = int(result["comparison"]["new_unique_cell_count"])
    structural_utility = float(rank_gain * 2 + residual_df_gain + new_cells)
    return StructuralDesignAssessment(
        candidate_id=candidate.candidate_id,
        rank_gain=rank_gain,
        residual_df_gain=residual_df_gain,
        new_unique_cell_count=new_cells,
        structural_utility=structural_utility,
        cost_units=candidate.cost_units,
    )


def structural_design_sensitivity(
    candidates: tuple[StructuralDesignCandidate, ...],
) -> tuple[StructuralDesignAssessment, ...]:
    """Evaluate predeclared design variants; no response/physics sensitivity is implied."""
    if not candidates:
        raise ScientificSimulationRegistryError("at least one design candidate is required")
    ids = [item.candidate_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ScientificSimulationRegistryError("design candidate ids must be unique")
    return tuple(assess_structural_design_candidate(item) for item in candidates)


def select_structural_design_candidate(
    candidates: tuple[StructuralDesignCandidate, ...],
    *,
    remaining_budget: float,
) -> dict[str, Any]:
    """Choose the strongest structural augmentation per cost without calling it EIG."""
    if not math.isfinite(remaining_budget) or remaining_budget < 0:
        raise ScientificSimulationRegistryError("remaining_budget must be finite and non-negative")
    assessments = structural_design_sensitivity(candidates)
    feasible = [item for item in assessments if item.cost_units <= remaining_budget]
    if not feasible:
        return {
            "selected_candidate_id": None,
            "status": "budget_blocked",
            "expected_information_gain": {"status": "not_quantified", "value": None},
            "physical_experiment_execution_authorized": False,
        }
    selected = max(
        feasible,
        key=lambda item: (
            item.structural_utility / (1.0 + item.cost_units),
            item.candidate_id,
        ),
    )
    return {
        "selected_candidate_id": selected.candidate_id,
        "status": "structural_design_priority_only",
        "structural_utility": selected.structural_utility,
        "rank_gain": selected.rank_gain,
        "residual_df_gain": selected.residual_df_gain,
        "new_unique_cell_count": selected.new_unique_cell_count,
        "expected_information_gain": {"status": "not_quantified", "value": None},
        "execution_mode": "explicit_authorization_required",
        "execution_route": "existing_independent_authorization_and_typed_executor_chain",
        "physical_experiment_execution_authorized": False,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = [
    "SCHEMA_VERSION",
    "ScientificSimulationRegistryError",
    "SimulationPlanningRequest",
    "SolverContract",
    "SolverContractRegistry",
    "StructuralDesignAssessment",
    "StructuralDesignCandidate",
    "assess_structural_design_candidate",
    "callable_module_sha256",
    "compile_simulation_action_candidate",
    "repository_design_simulation_contract",
    "repository_heat_conduction_contract",
    "select_structural_design_candidate",
    "structural_design_sensitivity",
]
