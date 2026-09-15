from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_authority_binding_hardening as authority_hardening,
)
from materials_data_analyzer.research_loop.nist_mds2_2923_network_policy import (
    ACTION_CLASS,
    POLICY_ID,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rehash(value: dict[str, Any], field: str) -> None:
    value.pop(field, None)
    value[field] = authority_hardening._canonical_sha(value)


def _fixture(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    qualification: dict[str, Any] = {
        "mission_sha256": authority_hardening.EXPECTED_MISSION_SHA256,
        "policy_id": POLICY_ID,
        "policy_sha256": authority_hardening.EXPECTED_NIST_POLICY_SHA256,
    }
    _rehash(qualification, "qualification_sha256")

    authorization: dict[str, Any] = {
        "mission_sha256": authority_hardening.EXPECTED_MISSION_SHA256,
        "policy_id": POLICY_ID,
        "policy_sha256": authority_hardening.EXPECTED_NIST_POLICY_SHA256,
    }
    _rehash(authorization, "authorization_sha256")

    manifest: dict[str, Any] = {
        "mission_sha256": authority_hardening.EXPECTED_MISSION_SHA256,
        "nist_mds2_2923_policy_sha256": (
            authority_hardening.EXPECTED_NIST_POLICY_SHA256
        ),
        "nist_mds2_2923_network_authorization_sha256": authorization[
            "authorization_sha256"
        ],
        "cycles": [
            {"cycle_index": 1},
            {"cycle_index": 2},
            {
                "cycle_index": 3,
                "selected_action_class": ACTION_CLASS,
                "network_policy_id": POLICY_ID,
                "network_policy_sha256": (
                    authority_hardening.EXPECTED_NIST_POLICY_SHA256
                ),
                "network_authorization_sha256": authorization[
                    "authorization_sha256"
                ],
            },
        ],
    }
    _write(root / "nist-network-policy-qualification.json", qualification)
    _write(root / "nist-network-authorization.json", authorization)
    _write(root / "autonomous-production-manifest.json", manifest)
    return qualification, authorization, manifest


def test_exact_authority_binding_accepts_only_pinned_roots(tmp_path: Path) -> None:
    _fixture(tmp_path)
    authority_hardening.verify_exact_authority_bindings(tmp_path)


@pytest.mark.parametrize("field", ["mission_sha256", "policy_sha256"])
def test_consistently_rehashed_authority_root_substitution_is_rejected(
    tmp_path: Path,
    field: str,
) -> None:
    qualification, authorization, manifest = _fixture(tmp_path)
    forged = "0" * 64

    qualification[field] = forged
    _rehash(qualification, "qualification_sha256")
    authorization[field] = forged
    _rehash(authorization, "authorization_sha256")

    if field == "mission_sha256":
        manifest["mission_sha256"] = forged
    else:
        manifest["nist_mds2_2923_policy_sha256"] = forged
        manifest["cycles"][2]["network_policy_sha256"] = forged
    manifest["nist_mds2_2923_network_authorization_sha256"] = authorization[
        "authorization_sha256"
    ]
    manifest["cycles"][2]["network_authorization_sha256"] = authorization[
        "authorization_sha256"
    ]

    _write(tmp_path / "nist-network-policy-qualification.json", qualification)
    _write(tmp_path / "nist-network-authorization.json", authorization)
    _write(tmp_path / "autonomous-production-manifest.json", manifest)

    with pytest.raises(
        authority_hardening.AutonomousProductionAuthorityBindingError,
        match="exact mission/policy binding drifted",
    ):
        authority_hardening.verify_exact_authority_bindings(tmp_path)
