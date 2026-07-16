# Unit Backend Decision

Status: `optional_pint_backend`

The platform keeps the existing builtin unit registry as the default backend.
It supports the current case studies, preserves backward compatibility, and
keeps CI dependency size stable.

## Decision

`optional_pint_backend`

Pint is not added as a required dependency in v2.2.2. The new backend interface
can use Pint only when it is already installed and explicitly requested by code.
The platform remains functional without Pint.

## Rationale

- Current case studies use a small controlled unit vocabulary.
- Existing tests cover linear conversions and the Celsius/Kelvin offset.
- Compound symbolic unit parsing is useful future work but not required for the
  v2.2.2 entity foundation.
- Existing JSON outputs must preserve original and canonical unit metadata.

## Guardrails

Arbitrary unit definition files are not loaded. All conversion metadata records
the backend identifier and version. Domain display units are preserved; canonical
storage does not force all user-facing values into SI display.
