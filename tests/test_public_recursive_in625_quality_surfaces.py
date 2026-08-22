from __future__ import annotations

from materials_data_analyzer.research_loop import public_recursive_api as api
from materials_data_analyzer.research_loop.in625_post_acquisition_rediagnosis_v2 import (
    build_in625_post_acquisition_rediagnosis_v2,
)
from materials_data_analyzer.research_loop.in625_tensile_quality_contract import (
    verify_in625_tensile_observed_quality,
)
from materials_data_analyzer.research_loop.in625_tensile_reviewed_intake import (
    build_reviewed_in625_tensile_intake as strict_intake,
)
from materials_data_analyzer.research_loop.in625_tensile_reviewed_intake_v2 import (
    build_reviewed_in625_tensile_intake_v2,
)


def test_public_in625_intake_defaults_to_row_preserving_v2() -> None:
    assert api.build_reviewed_in625_tensile_intake is build_reviewed_in625_tensile_intake_v2
    assert api.build_reviewed_in625_tensile_intake_v2 is build_reviewed_in625_tensile_intake_v2
    assert api.build_strict_in625_tensile_intake is strict_intake


def test_public_in625_quality_verifier_and_rediagnosis_are_exposed() -> None:
    assert api.verify_in625_tensile_observed_quality is verify_in625_tensile_observed_quality
    assert (
        api.build_in625_post_acquisition_rediagnosis_v2
        is build_in625_post_acquisition_rediagnosis_v2
    )
