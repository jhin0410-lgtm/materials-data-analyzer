"""Battery Degradation Intelligence public API."""
from .common import (
    BatteryIntelligenceConfig,
    validate_cycle_summary,
    validate_raw_signal,
)
from .degradation import analyze_trajectories, detect_knee_point
from .signals import extract_signal_features
from .forecast_table import build_forecast_table
from .forecast_validation import evaluate_grouped_forecast
from .closeout import scientific_closeout
from .workflow import run_battery_intelligence

__all__ = [
    "BatteryIntelligenceConfig",
    "validate_cycle_summary",
    "validate_raw_signal",
    "extract_signal_features",
    "detect_knee_point",
    "analyze_trajectories",
    "build_forecast_table",
    "evaluate_grouped_forecast",
    "scientific_closeout",
    "run_battery_intelligence",
]
