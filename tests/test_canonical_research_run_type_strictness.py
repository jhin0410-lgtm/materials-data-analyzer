from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop import canonical_research_run_impl
from materials_data_analyzer.research_loop.canonical_research_run import (
    CanonicalResearchRunError,
    build_canonical_research_run_contract,
    validate_canonical_research_run_contract,
)


def test_research_run_validation_rejects_boolean_integer_type_aliasing() -> None:
    contract = copy.deepcopy(build_canonical_research_run_contract())
    contract["authority_invariants"][
        "science_plane_may_initialize_non_empirical_scientific_scaffolding"
    ] = 1
    with pytest.raises(CanonicalResearchRunError, match="drifted"):
        validate_canonical_research_run_contract(contract)


def test_research_run_validation_rejects_integral_float_type_aliasing() -> None:
    contract = copy.deepcopy(build_canonical_research_run_contract())
    contract["authority_invariants"][
        "science_plane_may_initialize_non_empirical_scientific_scaffolding"
    ] = 1.0
    with pytest.raises(CanonicalResearchRunError, match="drifted"):
        validate_canonical_research_run_contract(contract)


def test_internal_research_run_validator_is_not_a_weaker_type_boundary() -> None:
    contract = copy.deepcopy(
        canonical_research_run_impl.build_canonical_research_run_contract()
    )
    contract["authority_invariants"][
        "science_plane_may_initialize_non_empirical_scientific_scaffolding"
    ] = 1
    with pytest.raises(
        canonical_research_run_impl.CanonicalResearchRunError,
        match="drifted",
    ):
        canonical_research_run_impl.validate_canonical_research_run_contract(contract)
