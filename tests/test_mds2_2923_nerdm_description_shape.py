from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop import mds2_2923_experiment_identity_reference_chain as graph


_DESCRIPTION = (
    "Some of the data is associated with publications (1) "
    "https://doi.org/10.1016/j.jmapro.2021.10.053 and (2) "
    "https://doi.org/10.1007/s40192-022-00289-w."
)


def _metadata(description: object) -> bytes:
    return json.dumps(
        {
            "@id": "ark:/88434/mds2-2923",
            "ediid": "ark:/88434/mds2-2923",
            "doi": "doi:10.18434/mds2-2923",
            "description": description,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def test_exact_nerdm_one_item_description_list_preserves_publication_associations() -> None:
    raw = _metadata([_DESCRIPTION])

    metadata_sha, associations = graph._metadata_associations(raw)

    assert metadata_sha == hashlib.sha256(raw).hexdigest()
    assert associations == [graph.WEAVER_DOI, graph.NADERI_DOI]


def test_historical_string_fixture_remains_supported_without_authority_change() -> None:
    raw = _metadata(_DESCRIPTION)

    _, associations = graph._metadata_associations(raw)

    assert associations == [graph.WEAVER_DOI, graph.NADERI_DOI]


@pytest.mark.parametrize(
    "description",
    [
        [],
        [_DESCRIPTION, "second description"],
        [_DESCRIPTION, 7],
        {"text": _DESCRIPTION},
    ],
)
def test_unexpected_nerdm_description_shapes_fail_closed(description: object) -> None:
    with pytest.raises(
        graph.Mds22923ExperimentIdentityReferenceChainError,
        match="description must be text or one non-empty text item",
    ):
        graph._metadata_associations(_metadata(description))
