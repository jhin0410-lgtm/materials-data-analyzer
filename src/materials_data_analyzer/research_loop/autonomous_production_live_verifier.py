"""Live autonomous-production verifier with explicit transport-report provenance binding.

The full outcome verifier is retained byte-for-byte in the sibling implementation module.
This wrapper adds the missing cross-artifact SHA binding required for transport stops: the
self-authenticated transport report must be exactly the report bound by both cycle 3 and the
top-level autonomous-production manifest.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import autonomous_production_live_verifier_impl as _impl

AutonomousProductionLiveVerificationError = (
    _impl.AutonomousProductionLiveVerificationError
)

_original_verify_transport_stop = _impl._verify_transport_stop


def _verify_transport_stop(
    root: Path, manifest: dict[str, Any], stop: dict[str, Any]
) -> str:
    report = _impl._load(root, "nist-transport-unavailability.json")
    report_sha = _impl._verify_self_hash(
        report,
        "report_sha256_without_self_field",
        label="NIST transport report",
    )

    result = _original_verify_transport_stop(root, manifest, stop)

    cycles = manifest.get("cycles")
    _impl._require(
        isinstance(cycles, list) and len(cycles) == 3,
        "transport cycle history drifted",
    )
    cycle3 = cycles[-1]
    _impl._require(isinstance(cycle3, dict), "transport cycle 3 is invalid")
    _impl._require(
        cycle3.get("transport_unavailability_sha256") == report_sha,
        "transport report cycle binding mismatch",
    )
    _impl._require(
        manifest.get("nist_mds2_2923_transport_unavailability_sha256") == report_sha,
        "transport report manifest binding mismatch",
    )
    return result


# The delegated verifier resolves this global at runtime. Replace only the transport-stop
# branch so normal twelve-cycle success remains byte-for-byte delegated to the reviewed
# implementation.
_impl._verify_transport_stop = _verify_transport_stop


def verify_live_autonomous_output(output_root: str | Path) -> str:
    return _impl.verify_live_autonomous_output(output_root)


def main(argv: list[str] | None = None) -> int:
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
