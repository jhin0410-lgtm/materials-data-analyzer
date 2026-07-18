# Battery Mechanism Evidence Gaps

Status: `v2.3.3_completed`

The tracked evidence-gap registry records missing evidence and prohibited
workarounds. Key gaps include:

- Controlled comparable temperature groups for Arrhenius analysis
- Rate-like response definition
- Explicit protocol comparability metadata
- Electrode geometry or diffusion length scale
- Internal concentration field or observation model
- Initial and boundary conditions
- Transport-identifying protocol such as GITT, PITT, or EIS
- Physical transient time axis
- Resistance measurement definition
- Frequency axis for impedance claims
- Source uncertainty or calibration records

Prohibited workarounds include arbitrary geometry defaults, using cycle index
as physical time, treating capacity as a rate constant, using terminal voltage
as a concentration field, and assuming missing protocol metadata implies
protocol equality.

v2.3.5 recovers exact cycle timestamps, within-discharge duration, group-level
protocol documents, and impedance `Re`/`Rct` availability. Those fields close
lineage and descriptive-context gaps only. The evaluator remains cycle-index
based, impedance is not aligned to discharge cycles, cycle-specific command
logs remain incomplete, and source uncertainty/calibration records remain
unavailable. The v2.3.3 mechanism-identifiability decision is preserved.
