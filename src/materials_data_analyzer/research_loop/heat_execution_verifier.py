"""Independent pre-execution byte verifier for the reference heat-solver adapter."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .action_registry import describe_action, load_action_registry
from .heat_conduction_action import ACTION_TYPE, ACTION_VERSION, COST_UNITS
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state

ADAPTER_ID = "reference-heat-conduction"
REGISTRY_DOMAIN = "reference_heat_conduction_physics"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "action_version",
    "research_run",
    "solver_request",
    "expected_solver_request_sha256",
    "expected_solver_implementation_sha256",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}


class HeatExecutionVerifierError(ResearchLoopError):
    """Raised when independent execution pins cannot be established exactly."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HeatExecutionVerifierError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_request(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HeatExecutionVerifierError("execution request must be valid UTF-8 JSON") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise HeatExecutionVerifierError("execution request must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise HeatExecutionVerifierError("execution request root must be an object")
    if set(value) != _REQUEST_KEYS:
        raise HeatExecutionVerifierError("typed heat execution request field set drifted")
    if value.get("schema_version") != "1.0":
        raise HeatExecutionVerifierError("unsupported typed heat execution request schema")
    for field in (
        "expected_solver_request_sha256",
        "expected_solver_implementation_sha256",
        "expected_registry_sha256",
    ):
        digest = value.get(field)
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise HeatExecutionVerifierError(f"{field} must be canonical lowercase SHA-256")
    return value


def _resolve(raw: object, *, base: Path, field: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise HeatExecutionVerifierError(f"{field} must be a path string")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=True)


def _current_solver_implementation_sha256() -> str:
    from .scientific_simulation_registry import repository_heat_conduction_contract

    digest = repository_heat_conduction_contract().implementation_module_sha256
    if _SHA256.fullmatch(digest) is None:
        raise HeatExecutionVerifierError("solver implementation SHA-256 is malformed")
    return digest


def verify_heat_execution_handoff(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    registry_path = Path(action_registry_path).expanduser().resolve(strict=True)
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request = _load_request(request_file)
    if request.get("action_type") != ACTION_TYPE or request.get("action_version") != ACTION_VERSION:
        raise HeatExecutionVerifierError("execution request action type/version drifted")
    if _resolve(request.get("repository_root"), base=request_file.parent, field="repository_root") != root:
        raise HeatExecutionVerifierError("request repository_root differs from verifier context")
    if _resolve(request.get("research_run"), base=request_file.parent, field="research_run") != run:
        raise HeatExecutionVerifierError("request research_run differs from verifier context")
    if _resolve(request.get("registry"), base=request_file.parent, field="registry") != registry_path:
        raise HeatExecutionVerifierError("request registry differs from verifier context")
    registry = load_action_registry(registry_path, repository_root=root)
    if registry.get("domain") != REGISTRY_DOMAIN:
        raise HeatExecutionVerifierError("reference heat registry domain drifted")
    contract = describe_action(registry, ACTION_TYPE)
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("cost_units") != COST_UNITS
    ):
        raise HeatExecutionVerifierError("reference heat registry action contract drifted")
    registry_sha = str(registry["registry_sha256"])
    if request.get("expected_registry_sha256") != registry_sha:
        raise HeatExecutionVerifierError("request expected_registry_sha256 differs from verified registry")
    solver_request = _resolve(request.get("solver_request"), base=request_file.parent, field="solver_request")
    solver_sha = _sha256_file(solver_request)
    if request.get("expected_solver_request_sha256") != solver_sha:
        raise HeatExecutionVerifierError("solver request differs from request-pinned SHA-256")
    implementation_sha = _current_solver_implementation_sha256()
    if request.get("expected_solver_implementation_sha256") != implementation_sha:
        raise HeatExecutionVerifierError(
            "solver implementation differs from request-pinned SHA-256"
        )
    state = load_research_state(run)
    if state.get("status") != "active":
        raise HeatExecutionVerifierError("research run is not active")
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    ledger_sha = _sha256_file(ledger)
    if state.get("ledger_sha256") != ledger_sha:
        raise HeatExecutionVerifierError("research state ledger SHA differs from current ledger bytes")
    request_sha = _sha256_file(request_file)
    if _SHA256.fullmatch(request_sha) is None or _SHA256.fullmatch(ledger_sha) is None:
        raise HeatExecutionVerifierError("internal SHA-256 normalization failed")
    return {
        "schema_version": "1.0",
        "adapter_id": ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": request_sha,
        "research_ledger_sha256": ledger_sha,
        "registry_sha256": registry_sha,
        "solver_request_sha256": solver_sha,
        "solver_implementation_sha256": implementation_sha,
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = ["ADAPTER_ID", "HeatExecutionVerifierError", "verify_heat_execution_handoff"]
