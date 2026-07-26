from __future__ import annotations

import copy

import pytest

from src.platform_core import battery_michigan_formation_deepblue_metadata_access_closeout as closeout
from src.platform_core import battery_michigan_formation_deepblue_metadata_retrieval_gate as gate


def test_access_denial_closeout_is_deterministic_and_bounded():
    result = closeout.execute(write_outputs=False)
    closeout.validate_result(result)
    assert result["deterministic_result_checksum"] == closeout.EXPECTED_FAILURE_CHECKSUM
    assert result["retrieval_status"] == "failed"
    assert result["error_category"] == "http_status_403"
    assert result["access_observation"]["observation_scope"] == "user_reported_local_execution_context"
    assert result["dataset_response"] is None
    assert result["file_set_records"] == []
    assert result["scientific_closeout"]["status"] == "inconclusive"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["access_observation"].__setitem__("observation_scope", "provider_api_globally_inaccessible"),
        lambda value: value["decision"].__setitem__("provider_dataset_identity", "api_verified"),
        lambda value: value["decision"].__setitem__("internal_provider_manifest", "established"),
        lambda value: value["decision"].__setitem__("cross_cohort_comparability", "admitted"),
        lambda value: value.__setitem__("candidate_admitted", True),
        lambda value: value.__setitem__("provider_file_payload_read", True),
    ],
)
def test_access_denial_closeout_rejects_claim_promotion(mutation):
    result = closeout.execute(write_outputs=False)
    promoted = copy.deepcopy(result)
    mutation(promoted)
    promoted["deterministic_result_checksum"] = gate.canonical_checksum(promoted)
    with pytest.raises(ValueError):
        closeout.validate_result(promoted)


def test_access_denial_does_not_claim_response_metadata():
    result = closeout.execute(write_outputs=False)
    assert result["metadata_completeness"] == {
        "file_set_ids_recovered": False,
        "labels_recovered": False,
        "sizes_recovered": False,
        "mime_types_recovered": False,
        "repository_checksums_recovered": False,
        "original_checksums_recovered": False,
    }
    assert result["decision"]["top_level_file_set_metadata"] == "access_denied_for_observed_execution_context"
    assert result["decision"]["local_archive_binding"] == "not_established"
    assert result["decision"]["predictive_validation"] == "blocked"
