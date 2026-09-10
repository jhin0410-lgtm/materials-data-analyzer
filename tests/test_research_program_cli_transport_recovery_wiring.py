from __future__ import annotations

from materials_data_analyzer import research_program_cli
from materials_data_analyzer.research_loop import autonomous_production_transport_recovery


def test_run_autonomous_cli_uses_fail_closed_transport_recovery_boundary() -> None:
    assert research_program_cli.run_autonomous_production is (
        autonomous_production_transport_recovery.run_autonomous_production
    )
