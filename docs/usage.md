# CompReg usage

Global options (available on every subcommand):

| flag | meaning |
|---|---|
| `--config PATH` | TOML config layered over `config/default.toml` |
| `--compilers gcc,clang` | restrict compiler families |
| `--opts O0,O2` | restrict optimization levels |
| `--timeout S` | per-test execution timeout |
| `--artifacts DIR`, `--db PATH` | output overrides |

Exit codes: `0` success · `1` verification failures/regressions · `2`
configuration error · `3` infrastructure error.

## doctor

```bash
compreg doctor
```

Reports python/platform, each requested compiler (with install hints when
missing), sqlite, cmake/ctest, git and corpus integrity. Exit 0 unless the
corpus itself is broken.

## list-tests

```bash
compreg list-tests
compreg list-tests --category sorting
compreg list-tests --json
compreg list-tests --include-generated artifacts/generated/manifest.json
```

## generate — deterministic extra tests

```bash
compreg generate --count 6 --seed 42
compreg verify --include-generated artifacts/generated/manifest.json --opts O2
```

Generated programs carry precomputed oracles (computed by the generator, with
exact integer semantics, not by a compiler). Output is byte-identical for the
same seed on any platform.

## verify — correctness sweep

```bash
compreg verify                                   # all tests, all configured compiler/opts
compreg verify --opts O2                         # single option level sweep
compreg verify --tests sorting_bubble_sort --opts O0,O2
compreg verify --no-db                           # skip persistence
compreg verify --ad-hoc-source path/file.cpp --ad-hoc-expected path/file.expected
```

Classification values: `PASS`, `COMPILE_ERROR`, `OUTPUT_MISMATCH`,
`NONZERO_EXIT`, `TIMEOUT`, `EXECUTION_ERROR`, `INFRASTRUCTURE_ERROR`, and
`SKIPPED` for unavailable configurations. Failed compilation never proceeds to
execution.

## benchmark — measured timing after a correctness gate

```bash
compreg benchmark                                # all benchmark-eligible tests
compreg benchmark --tests bench_int_workload --reps 7 --warmup 2
```

Benchmarks only run after the correctness gate passes for the same test. Each
sample is the wall time of a full process run (startup included — see
docs/limitations.md). Results are stored as `benchmark_stat` +
`benchmark_sample` rows.

Custom/ad-hoc benchmarks (used by the demo scenarios):

```bash
compreg benchmark --ad-hoc-bench examples/slow_int_workload.cpp \
  --ad-hoc-id demo_workload --ad-hoc-expected test_corpus/benches/bench_int_workload.expected
```

## baselines and comparison

```bash
compreg benchmark --opts O2 --reps 7             # run A
compreg baseline create --run <A>                # store baselines (needs min samples)
compreg benchmark --opts O2 --reps 7             # run B (same machine)
compreg compare --run <B> --baseline <A>         # regression verdicts, persisted
```

`compare` refuses comparisons across different tests, compiler configurations
(optimization level/compiler version/flags), benchmark versions, and (by
config) different machines. Verdicts: `regression`, `no_regression`,
`insufficient_samples`, `incompatible`, plus `no_baseline` when none exists.

## history

```bash
compreg history            # run listing with pass/fail/skip counts
compreg history --test bench_int_workload   # regression timeline for one test
```

## minimize — delta debugging

```bash
compreg minimize --source examples/minimize_payload.cpp \
  --expected "$(printf '265\n86')" --opt O2
```

Behaviour: reduces the source LINE-wise while the candidate reproduces the
*identical failing behavior* (same failing stdout for runtime failures;
compile failure for a compile-failure original). Writes
`artifacts/minimize/<name>/minimized.cpp` and preserves the original
(`original-preserved.cpp`). Limitations are documented in docs/limitations.md.

## report / triage

```bash
compreg report --run latest --out prefix   # writes prefix.json + 2 CSVs + summary
compreg triage                              # failure-evidence JSON paths for a run
```

The report schema is documented in docs/reporting.md.

## ctest

```bash
compreg ctest   # cmake configure + build + ctest (native C++ tests, and pytest when importable)
```

## Configuration file

Any option can be layered in a user TOML:

```toml
[compilers]
families = ["gcc"]

[verification]
opt_levels = ["O0", "O2"]
timeout_s = 20

[benchmark]
reps = 11
warmup = 3
min_samples = 5

[regression]
rel_threshold = 0.15
abs_threshold_s = 0.01
noise_k_mad = 3.0

[paths]
db = "artifacts/compreg.db"
artifacts = "artifacts"

[comparisons]
require_same_host = true
```

Use with `compreg --config mysettings.toml verify`.
