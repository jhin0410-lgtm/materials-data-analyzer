import pytest

from src.platform_core.uncertainty import UncertaintyInterval, UncertaintySpec


def test_uncertainty_kind_and_confidence_interval_validation():
    interval = UncertaintyInterval(lower=0.9, upper=1.1, unit="m", confidence_level=0.95)
    spec = UncertaintySpec(kind="confidence_interval", interval=interval, confidence_level=0.95)

    assert spec.to_dict()["interval"]["lower"] == 0.9
    with pytest.raises(ValueError, match="requires an interval"):
        UncertaintySpec(kind="confidence_interval")
    with pytest.raises(ValueError, match="confidence_level"):
        UncertaintySpec(kind="absolute", value=1.0, confidence_level=0.95)


def test_generic_confidence_score_is_not_uncertainty_kind():
    with pytest.raises(ValueError, match="unsupported uncertainty kind"):
        UncertaintySpec(kind="confidence_score", value=0.9)
