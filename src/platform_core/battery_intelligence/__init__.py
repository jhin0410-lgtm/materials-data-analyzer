"""Battery Degradation Intelligence public API."""
from .common import (
    BatteryIntelligenceConfig,
    validate_cycle_summary,
    validate_raw_signal,
)
from .degradation import analyze_trajectories, detect_knee_point
from .signals import extract_signal_features
from .forecast_table import build_forecast_table
from .forecast_baselines import build_baseline_predictions
from .forecast_validation import evaluate_grouped_forecast
from .error_diagnostics import build_error_diagnostics
from .raw_signal_admission import audit_raw_signal_admission
from .target_comparability import (
    audit_battery_intelligence_run,
    build_target_comparability_audit,
)
from .influence_triage import (
    audit_battery_influence_run,
    build_battery_influence_triage,
)
from .closeout import scientific_closeout
from .workflow import run_battery_intelligence
from .nasa_pcoe_resilient import import_nasa_pcoe_battery

__all__ = [
    "BatteryIntelligenceConfig",
    "validate_cycle_summary",
    "validate_raw_signal",
    "extract_signal_features",
    "detect_knee_point",
    "analyze_trajectories",
    "build_forecast_table",
    "build_baseline_predictions",
    "evaluate_grouped_forecast",
    "build_error_diagnostics",
    "audit_raw_signal_admission",
    "build_target_comparability_audit",
    "audit_battery_intelligence_run",
    "build_battery_influence_triage",
    "audit_battery_influence_run",
    "scientific_closeout",
    "run_battery_intelligence",
    "import_nasa_pcoe_battery",
]
