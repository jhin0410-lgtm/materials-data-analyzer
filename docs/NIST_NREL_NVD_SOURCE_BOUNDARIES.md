# NIST, NREL, And NVD Source Boundaries

Status: `future_sources_declared_not_integrated`

v2.4.1 registers source-system routing metadata only. No API call, retrieval,
dataset snapshot, or successful integration evidence exists for these systems.

## NIST OAR

NIST Open Access to Research is a public research-data catalog and
distribution-discovery source. Catalog metadata can help locate a dataset or
documentation record; it does not independently validate the scientific
content, calibration, protocol, or suitability of a dataset.

## NVD

The National Vulnerability Database is routed to CVE/CPE and software-security
work. `NVD_API_KEY` is an environment-variable name only. NVD is not a source
for Battery protocol, measurement uncertainty, crystal structure, or computed
materials-property enrichment.

## NREL

NREL services can support future energy-system, weather, grid, renewable, or
operational context after a dataset-specific contract. `NREL_API_KEY` is an
environment-variable name only. NREL metadata is not a substitute for cell
cycling protocol, instrument calibration, measurement uncertainty, or an
official NASA Battery snapshot.

## Future Integration Gate

Each future source requires a named dataset, snapshot/version semantics,
distribution or endpoint, retrieval event, terms, provenance assessment,
domain comparability audit, and explicit claim boundary. Declaring a source
system does not make it integrated or scientifically eligible.
