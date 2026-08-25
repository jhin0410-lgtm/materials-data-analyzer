"""Public autonomous-production live verifier with cross-artifact semantic hardening.

The previously reviewed verifier is retained byte-for-byte in
``autonomous_production_live_verifier_base``. This entrypoint adds semantic checks that a
self-consistently re-hashed artifact set cannot bypass, anchors execution authority to the
exact mission/policy pins and checkout-root evidence, independently replays source-derived
artifacts from exact retained bytes, then delegates to every pre-existing transport/full-
success provenance check.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import autonomous_production_live_verifier_base as _base
from .autonomous_production_authority_binding_hardening import (
    AutonomousProductionAuthorityBindingError,
    verify_exact_authority_bindings,
)
from .autonomous_production_exact_head_p2_closure import (
    install_exact_head_p2_closures,
)
from .autonomous_production_exact_head_p2_round2 import (
    install_exact_head_round2_closures,
    verify_exact_head_round2_boundaries,
)
from .autonomous_production_exact_head_p2_round3 import (
    install_exact_head_round3_closures,
    verify_exact_head_round3_boundaries,
)
from .autonomous_production_merge_gate_lifecycle import (
    AutonomousProductionMergeGateHardeningError,
    verify_final_merge_gate_boundaries,
)
from .autonomous_production_round3_preflight_scope import (
    verify_round3_duplicate_key_preflight,
)
from .autonomous_production_semantic_hardening import (
    AutonomousProductionSemanticHardeningError,
    verify_persisted_semantic_boundaries,
)
from .autonomous_production_source_replay_hardening import (
    AutonomousProductionSourceReplayHardeningError,
    verify_source_replay_boundaries,
)

AutonomousProductionLiveVerificationError = (
    _base.AutonomousProductionLiveVerificationError
)

_original_impl_verify_live_autonomous_output = (
    _base._impl.verify_live_autonomous_output
)

install_exact_head_p2_closures()
install_exact_head_round2_closures()
install_exact_head_round3_closures()


def _verify_with_semantic_hardening(output_root: str | Path) -> str:
    try:
        # Reject duplicate keys before legacy parsing, while allowing lifecycle-specific
        # handling of bounded partial source metadata that is not yet a complete JSON object.
        verify_round3_duplicate_key_preflight(output_root)
        verify_exact_authority_bindings(output_root)
        verify_persisted_semantic_boundaries(output_root)
        verify_exact_head_round2_boundaries(output_root)
        verify_final_merge_gate_boundaries(output_root)
        verify_source_replay_boundaries(output_root)
        # These checks rely on the source replay above, so they run after canonical replay.
        verify_exact_head_round3_boundaries(output_root)
    except (
        AutonomousProductionAuthorityBindingError,
        AutonomousProductionSemanticHardeningError,
        AutonomousProductionMergeGateHardeningError,
        AutonomousProductionSourceReplayHardeningError,
    ) as exc:
        raise AutonomousProductionLiveVerificationError(str(exc)) from exc
    return _original_impl_verify_live_autonomous_output(output_root)


# ``_base.main`` delegates through the implementation module, so patch the single dispatch
# point as well as the public function. The underlying reviewed verifier remains otherwise
# unchanged.
_base._impl.verify_live_autonomous_output = _verify_with_semantic_hardening


def verify_live_autonomous_output(output_root: str | Path) -> str:
    return _base.verify_live_autonomous_output(output_root)


def main(argv: list[str] | None = None) -> int:
    return _base.main(argv)


def __getattr__(name: str) -> Any:
    """Preserve compatibility for audited private helpers used by regression tests."""
    return getattr(_base, name)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AutonomousProductionLiveVerificationError",
    "main",
    "verify_live_autonomous_output",
]
