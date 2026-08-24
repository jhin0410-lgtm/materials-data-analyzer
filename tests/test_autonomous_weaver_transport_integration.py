from __future__ import annotations

from materials_data_analyzer.research_loop import autonomous_production_transport_recovery as recovery
from materials_data_analyzer.research_loop import autonomous_production_weaver_extension as weaver


def test_transport_recovery_defaults_to_weaver_capable_production() -> None:
    assert recovery.run_reference_chain_production is weaver.run_autonomous_production


def test_weaver_extension_preserves_twelve_cycle_reference_chain_delegate() -> None:
    # The integration layer extends the audited production frontier rather than replacing the
    # existing <=12-cycle scientific path. The Weaver module itself owns the exact delegation.
    assert weaver.run_reference_chain_production is not recovery.run_autonomous_production
