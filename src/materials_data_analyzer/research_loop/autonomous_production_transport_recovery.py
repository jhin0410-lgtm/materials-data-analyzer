"""Weaver-aware facade over the reviewed autonomous transport-recovery implementation.

The recovery implementation remains byte-for-byte identical to the reviewed #233 implementation.
This facade changes only the scientific production function invoked beneath that recovery boundary:
`autonomous_production_weaver_extension.run_autonomous_production` delegates <=12 cycles to the
existing reference-chain implementation and extends cycles 13-14 only under the separately
authenticated Weaver authority. The narrow NIST transport exception remains the only recovered
failure class.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import autonomous_production_transport_recovery_impl as _impl
from .autonomous_production_weaver_extension import (
    run_autonomous_production as run_weaver_production,
)

# Historical tests and callers monkeypatch this module-level seam. Keep that surface while
# changing its production default from the 12-cycle reference-chain implementation to the
# Weaver-capable implementation. Each invocation copies the current seam into the reviewed
# implementation so monkeypatches remain effective and deterministic.
run_reference_chain_production = run_weaver_production

AutonomousProductionTransportRecoveryError = _impl.AutonomousProductionTransportRecoveryError
TRANSPORT_STOP_CONTRACT_VERSION = _impl.TRANSPORT_STOP_CONTRACT_VERSION
TRANSPORT_STOP_REASON_CODE = _impl.TRANSPORT_STOP_REASON_CODE
NIST_ACTION_CLASS = _impl.NIST_ACTION_CLASS
NIST_CANDIDATE_ID = _impl.NIST_CANDIDATE_ID
NIST_POLICY_ID = _impl.NIST_POLICY_ID
NIST_PRODUCT_ID = _impl.NIST_PRODUCT_ID
_canonical_sha = _impl._canonical_sha
_finalize_transport_stop = _impl._finalize_transport_stop


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 12,
) -> dict[str, Any]:
    """Run Weaver-capable production behind the reviewed narrow transport recovery boundary."""

    _impl.run_reference_chain_production = run_reference_chain_production
    return _impl.run_autonomous_production(
        repository_root=repository_root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=max_cycles,
    )


__all__ = [
    "AutonomousProductionTransportRecoveryError",
    "TRANSPORT_STOP_CONTRACT_VERSION",
    "TRANSPORT_STOP_REASON_CODE",
    "run_autonomous_production",
]
