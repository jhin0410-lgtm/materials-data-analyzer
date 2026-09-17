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

from . import autonomous_production_fresh_review_round10 as _round10
from . import autonomous_production_live_verifier_base as _base
from . import autonomous_production_merge_gate_hardening as _merge_gate
from .autonomous_production_authority_binding_hardening import (
    AutonomousProductionAuthorityBindingError,
    verify_exact_authority_bindings,
)
from .autonomous_production_cycle6_reacquisition_binding import (
    verify_cycle6_reacquisition_boundaries,
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
from .autonomous_production_exact_head_p2_round4 import (
    verify_exact_head_round4_boundaries,
)
from .autonomous_production_exact_head_p2_round5 import (
    verify_exact_head_round5_boundaries,
)
from .autonomous_production_exact_head_p2_round6 import (
    verify_exact_head_round6_boundaries,
)
from .autonomous_production_exact_head_p2_round7 import (
    verify_exact_head_round7_boundaries,
)
from .autonomous_production_exact_head_p2_round8 import (
    verify_exact_head_round8_boundaries,
)
from .autonomous_production_fresh_review_round9 import (
    verify_fresh_review_round9_boundaries,
)
from .autonomous_production_fresh_review_round11 import (
    verify_fresh_review_round11_boundaries,
)
from .autonomous_production_fresh_review_round12 import (
    verify_fresh_review_round12_boundaries,
)
from .autonomous_production_fresh_review_round13 import (
    verify_fresh_review_round13_boundaries,
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
from .autonomous_production_transport_recovery import (
    NIST_ACTION_CLASS,
    TRANSPORT_STOP_REASON_CODE,
)
from .autonomous_production_trusted_replay_artifact_binding import (
    verify_trusted_replay_artifact_bindings,
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


def _is_exact_nist_transport_stop_lifecycle(manifest: dict[str, Any]) -> bool:
    """Recognize only the dedicated three-cycle typed NIST transport-stop contract.

    This does not authenticate that stop by itself. The retained base verifier performs the
    complete transport report/policy/authorization/scientific-boundary verification after the
    additive gates return. The narrow predicate exists only so Round 12 does not demand current
    cycle-1 typed-execution artifacts from the older dedicated transport-stop lifecycle.
    """
    cycles = manifest.get("cycles")
    stop = manifest.get("stop")
    if not isinstance(cycles, list) or len(cycles) != 3 or not isinstance(stop, dict):
        return False
    cycle3 = cycles[2]
    if not isinstance(cycle3, dict):
        return False
    return (
        stop.get("status") == "stopped"
        and stop.get("reason_code") == TRANSPORT_STOP_REASON_CODE
        and stop.get("requested_action_class") == NIST_ACTION_CLASS
        and stop.get("scientific_status_changed") is False
        and type(cycle3.get("cycle_index")) is int
        and cycle3.get("cycle_index") == 3
        and cycle3.get("selected_action_class") == NIST_ACTION_CLASS
        and cycle3.get("scientific_status_changed") is False
        and manifest.get("scientific_status_changed") is False
    )


def _verify_with_semantic_hardening(output_root: str | Path) -> str:
    try:
        # Reject duplicate keys before legacy parsing, while allowing lifecycle-specific
        # handling of bounded partial source metadata that is not yet a complete JSON object.
        verify_round3_duplicate_key_preflight(output_root)
        verify_exact_authority_bindings(output_root)
        # Python equality aliases JSON ints/floats and bools/ints. Re-check the retained NIST
        # authority/control-plane identities through canonical JSON before any legacy equality
        # can accept an equal-valued type substitution.
        verify_fresh_review_round13_boundaries(output_root)
        verify_persisted_semantic_boundaries(output_root)
        verify_exact_head_round2_boundaries(output_root)
        verify_final_merge_gate_boundaries(output_root)
        verify_source_replay_boundaries(output_root)
        # These checks rely on the source replay above, so they run after canonical replay.
        verify_exact_head_round3_boundaries(output_root)
        verify_exact_head_round4_boundaries(output_root)
        # Fresh-review closure authenticates mutable-fingerprint presence, parser identity,
        # cycle-4 network history, and persisted late policy qualifications before capability replay.
        verify_fresh_review_round9_boundaries(output_root)
        # Cycle 6 performs a second eight-source network acquisition. Replay those exact retained
        # responses and rebuild its source-version and bridge conclusions before later promotion gates.
        verify_cycle6_reacquisition_boundaries(output_root)
        # Authenticate candidate/verifier producers before replaying registry successors.
        verify_exact_head_round7_boundaries(output_root)
        # Bind mutable retained smoke responses to independently reviewed source versions.
        verify_exact_head_round8_boundaries(output_root)
        # Bind persisted downstream authority artifacts to the canonical trusted producer replay.
        verify_trusted_replay_artifact_bindings(output_root)

        # Round 10 was written for the complete 12-cycle lineage. Its promotion loop must not
        # demand verification/promoted-registry artifacts from legitimate 5/7/9/11-cycle bounded
        # stops. Preserve geometry replay on partial lifecycles and run the full legacy Round-10
        # replay only when all 12 cycles exist. Round 12 below independently supplies the missing
        # stage-aware derived-artifact replay for legitimate 10/11-cycle outputs.
        root = Path(output_root).expanduser().resolve(strict=True)
        manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
        cycles = manifest.get("cycles")
        if not isinstance(cycles, list):
            raise AutonomousProductionMergeGateHardeningError(
                "autonomous production cycles must be a list"
            )
        if len(cycles) == 12:
            _round10.verify_fresh_review_round10_boundaries(root)
        else:
            _round10._verify_geometry_mapping(root, manifest)

        # Round 11 provides stage-aware promotion replay, canonical JSON type fidelity,
        # complete predecessor reconstruction, cycle-6 execution boundaries, and the first
        # independent cycle-1 authority/execution closure.
        verify_fresh_review_round11_boundaries(root)
        # Round 12 closes the remaining fresh-review surfaces on the current production lineage.
        # The dedicated three-cycle NIST transport-stop lifecycle predates those retained cycle-1
        # typed-execution artifacts and is already authenticated by the base transport verifier.
        # Skip only that exact lifecycle shape; a current/full output cannot delete Round-12 fields
        # and downgrade into this path without also satisfying the base verifier's transport proof.
        if not _is_exact_nist_transport_stop_lifecycle(manifest):
            verify_fresh_review_round12_boundaries(root)
        verify_exact_head_round6_boundaries(output_root)
        verify_exact_head_round5_boundaries(output_root)
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
