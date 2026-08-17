from __future__ import annotations

import hashlib
import json

from materials_data_analyzer.research_loop.nist_pdr_acquisition import (
    discover_nist_pdr_candidates,
)


def test_datafile_inheritance_and_decimal_string_size_are_accepted() -> None:
    artifact = b"exact-nist-bytes"
    metadata = {
        "@id": "ark:/88434/mds2-2923",
        "@type": ["nrdp:DataPublication", "nrdp:PublicDataResource"],
        "version": "1.0",
        "components": [
            {
                "@type": ["nrdp:DataFile", "dcat:Distribution"],
                "filepath": "Master_TrackList_Measurements.xlsx",
                "downloadURL": (
                    "https://data.nist.gov/od/id/mds2-2923/"
                    "Master_TrackList_Measurements.xlsx"
                ),
                "size": str(len(artifact)),
                "checksum": {
                    "hash": hashlib.sha256(artifact).hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            }
        ],
    }
    metadata_bytes = (json.dumps(metadata) + "\n").encode("utf-8")

    candidate = discover_nist_pdr_candidates(
        metadata_bytes=metadata_bytes,
        product_id="mds2-2923",
    )[0]

    assert candidate["expected_size_bytes"] == len(artifact)
    assert candidate["retrieval_endpoint"].endswith(
        "/Master_TrackList_Measurements.xlsx"
    )
