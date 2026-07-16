# Schema Evolution

Status: `scaffold_stage`

v2.2.2 adds deterministic migration helpers for JSON-safe scientific records.
Migration functions are code-registered and are not loaded from user config.

## Policy

- Exact-version reads are preferred.
- Supported older records may be migrated through registered migration steps.
- Newer/future schema versions are rejected.
- Source artifacts are not mutated.
- Required field loss is treated as migration failure.
- Silent field drops are prohibited.

## Initial Fixtures

- `MaterialCompositionEntity` v1 to v2: rename `amounts` to
  `stoichiometric_amounts` and add normalization status.
- `ScientificQuantity` v1 to v2: preserve original unit and add validity and
  conversion metadata.

These fixtures are synthetic and only validate the migration mechanism.
