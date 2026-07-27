## Summary

Describe the focused change and why it is needed.

## Scope and compatibility

- Public CLI/API behavior changed: yes / no
- Output schema or filename changed: yes / no
- New dependency added: yes / no
- Raw data or generated artifacts added: yes / no

Explain any intentional compatibility impact.

## Validation

List the exact commands and results.

```text
python -m pytest -q
```

Separate software validation from scientific validation. Passing tests does not by itself establish physical validity, causal interpretation, model generalization, or production readiness.

## Scientific and data review

- [ ] Units, identifiers, grouping, time order, and target definitions were checked where relevant.
- [ ] Preprocessing, filtering, exclusions, and missing metadata are explicit.
- [ ] Leakage and extrapolation risks were considered where relevant.
- [ ] Claims remain within the available evidence.
- [ ] External data source, license/access terms, and provenance are documented.

## Repository hygiene

- [ ] No credentials, private data, local registries, caches, or large regenerable outputs are included.
- [ ] Tests and relevant documentation were updated.
- [ ] Unrelated files were not modified.
