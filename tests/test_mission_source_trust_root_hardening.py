from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.mission_source_trust_root import (
    MissionSourceTrustRootError,
    authenticate_mission_source_trust_policy_pin,
)


def test_non_bytes_mission_fails_with_domain_error() -> None:
    with pytest.raises(MissionSourceTrustRootError, match="mission_bytes must be exact bytes"):
        authenticate_mission_source_trust_policy_pin(
            mission_bytes="not-bytes",  # type: ignore[arg-type]
            expected_mission_sha256="0" * 64,
            program_state={},
            policy_id="policy",
            source_trust_policy_bytes=b"{}",
        )


def test_non_bytes_policy_fails_with_domain_error() -> None:
    with pytest.raises(
        MissionSourceTrustRootError,
        match="source_trust_policy_bytes must be exact bytes",
    ):
        authenticate_mission_source_trust_policy_pin(
            mission_bytes=b"{}",
            expected_mission_sha256="0" * 64,
            program_state={},
            policy_id="policy",
            source_trust_policy_bytes="not-bytes",  # type: ignore[arg-type]
        )
