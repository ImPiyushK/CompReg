# CompReg testing

Two layers: `pytest` for the Python framework and `CTest/pytest-through-CTest`
for the native C++ project. Timing-sensitive logic is validated with
**injected measurement data**, so no ordinary test depends on wall-clock
threshold timing.

## Unit tests (mandatory; run without any compiler)

| file | covers |
|---|---|
| `test_config.py` | config layering, validation failures, path resolution |
| `test_compiler.py` | argv construction, opt-level validation, version parsing (incl. distro banner fallback), config-hash sensitivity, discovery incl. fake compilers on a temp PATH and broken-executable handling |
| `test_oracle.py` | normalization rules, exact + first-difference, tolerance semantics, count mismatch, non-finite handling |
| `test_classify.py` | execution-result → category mapping |
| `test_statistics.py` | median/MAD hand-computed values, outlier robustness, invalid input rejection |
| `test_regression_synthetic.py` | the noise-aware rule: jitter not flagged, +60% flagged, 3-sample refused, incompatible metadata refused, threshold composition (40 deterministic seeded trials) |
| `test_database.py` | schema/tables, upsert idempotence, sample batches, baseline round trips, regression history |
| `test_minimizer.py` | predicates: reduction, rejection, budget, duplicates, passthrough |
| `test_reports.py` | stable JSON schema, counts, CSV columns/values |
| `test_cli_args.py` | parser coverage, config-error exit code, unknown ids |
| `test_corpus.py` | registry/expected integrity, banned API scan, generator determinism & oracles |

Fake compiler ("discovery uses a configured path / broken executable") tests
use throwaway shell scripts in temporary directories — no fake version is ever
recorded as a real outcome.

## Integration tests (require the installed compiler; skip transparently)

| file | covers |
|---|---|
| `test_verify_e2e.py` | compile+run PASS; deliberate OUTPUT_MISMATCH; COMPILE_ERROR with no execution; TIMEOUT; NONZERO_EXIT; multi-style consistency; deterministic SKIPPED rows for unavailable compilers (injected missing path, no environment dependence); **oracle decides even when all configurations agree** on a wrong expected output |
| `test_bisect_real_repo.py` | real `git bisect run` over a temp repository with an injected regression: first-bad-commit identification, bisect-state cleanup on success and failure, missing-revision handling (git-bisect(1) exit-code contract) |
| `test_baseline_flow.py` | persistence round trip; injected-sample regression flow through SQLite; compatibility guard |
| `test_report_triage_e2e.py` | complete JSON+CSV export; triage evidence with commands/hashes |
| `test_tooling_e2e.py` | CTest suite executed end-to-end; generated tests compiled and passing; minimization preserves the failure |

## Recorded run on the development machine

```
$ pytest                     → 117 passed  (97 unit + 20 integration)
$ pytest -m "not slow"       → 111 passed, 6 deselected (slow: CTest e2e, generated, minimize, bisect)
$ compreg ctest              → "100% tests passed" 3/3 (2 native C++ + python_unit_tests)
$ compreg doctor             → all checks OK (clang reported UNAVAILABLE with hint; GCC 13.3.0 found)
```

## Adding tests

- Anything touching compilers belongs in `tests/integration` with the
  `requires_compiler` markers supplied by `tests/conftest.py`.
- Anything timing-ranked belongs behind injected measurements (see
  `compreg.benchmarking.runner.measure_samples` injection points).
- The CI workflow (`.github/workflows/ci.yml`) runs unit, integration, and
  CTest jobs; the Windows job installs MSYS2 UCRT64 GCC and executes a real
  compile-verify subset plus `compreg ctest`.
