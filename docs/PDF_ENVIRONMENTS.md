# Current PDF processing and historical replay

Develop on branch `fix/pypdf-security-replay-separation` in this worktree using
its own `.venv`. Check `git branch --show-current` and the imported package's
`__file__` when selecting an interpreter. An editable installation must point
to this same checkout, not another worktree. The original main checkout stays
unchanged and has no active development environment until separately prepared.

Current development and CLI environments install `pypdf==6.21.4` through both
`pyproject.toml` and `requirements.txt`. Use a Python 3.11 runtime and an editable
install for development:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' -c constraints-release.txt
.venv/bin/python -m pytest -q
```

All four external PDF parsing paths check the installed parser before giving it
input bytes. An old parser cannot be enabled with an environment variable or a
fallback. The two standalone acquisition workflows also pin the current version.
These checks do not replace download policy, provenance, or resource isolation.

## Immutable historical environment

The retained multisource contract still requires pypdf **6.18.1**, strict=False,
the original report fingerprints and all existing network/scientific boundaries.
The original round-9 verifier is unchanged. A current environment must reject a
claim that it executed that exact historical contract. A historical environment
must reject reports claiming a different parser. Do not rewrite old report
versions/hashes or install the historical requirements over current MDA.

Use the baseline MDA distribution at commit
`257dcfb3e51602119eeddb6f7da2226d66771ca2` in its own environment. Build it from
that commit or use a previously verified wheel from that commit. Do not install
the current checkout with `--no-deps` into the old environment: that would lie
about its dependency requirements. The historical environment is a baseline
wheel install; the current environment remains editable.

Example provisioning (separate scratch directories; never overwrite an existing
environment or evidence directory):

```bash
mkdir -p /path/to/new-baseline-source
git archive 257dcfb3e51602119eeddb6f7da2226d66771ca2 |
  tar -x -C /path/to/new-baseline-source
.venv/bin/python -m build --wheel /path/to/new-baseline-source \
  --outdir /path/to/new-baseline-wheel
python3.11 -m venv .venv-historical
.venv-historical/bin/python -m pip install \
  -r requirements-historical-replay.txt 'pytest>=8,<10' \
  /path/to/new-baseline-wheel/*.whl
.venv-historical/bin/python -m pip check
```

Provisioning can access the package index. **Execution must be offline** and use
only reviewed, checksum-bound retained inputs. Do not fetch or parse new external
PDFs using this vulnerable environment. A venv alone is not a security sandbox.
On Linux, the independent contract suite is run with existing bubblewrap and
prlimit tools. Missing isolation tools are a validation failure, not a reason to
skip these tests or run them without isolation:

```bash
RESULT=/absolute/path/to/new-replay-results
mkdir -p "$RESULT"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg \
prlimit --as=1610612736 --cpu=90 --nofile=256 \
  bwrap --die-with-parent --unshare-net --ro-bind / / --proc /proc --dev /dev \
  --tmpfs /tmp --bind "$RESULT" "$RESULT" \
  --setenv PYTHONDONTWRITEBYTECODE 1 \
  "$PWD/.venv-historical/bin/python" -m pytest -q -ra \
  -c /dev/null --confcutdir=validation validation/historical_pdf_replay.py \
  -o cache_dir="$RESULT/cache" --basetemp="$RESULT/tmp" \
  --junitxml="$RESULT/junit.xml"
```

`--confcutdir` prevents current tests/conftest.py from injecting current src into
the baseline process. The validation checks installed site-packages file hashes
for the five relevant baseline modules against historical_pdf_contract.json.
It tests the real historical parser and all four network-promotion rejections
without mocking its installed version. The normal unit suite independently
tests those conditions and verifies that current PDF paths reject old parsers.
The quality workflow has separate current and historical jobs.
The historical suite also checks the address-space, CPU and file-descriptor
limits in the executing process; omitting the limits is a validation failure.

The historical checks use synthetic text-only PDF bytes. They establish code
identity and software contracts, not a rerun of the retained research campaign,
equivalence of text extracted by two parser versions, or scientific validation.
Any real historical replay still requires its original authenticated inputs and
the unchanged full verifier, under the same offline/read-only/resource limits.
The sandbox permits host-file reads; it is not a confidentiality sandbox. Only
the specified result directory and ephemeral /tmp are writable. Never bind a
canonical dataset or existing research output directory as a writable result.

The old parser deliberately retains known vulnerabilities. Its audit result is
reported separately and never used to declare the current environment safe.
Store exact environment freezes, baseline artifact hashes and replay diagnostics
with the run. Current dependency audit failures remain release failures.
