# CompReg architecture

## Component map

```
┌───────────────────────────────────────────────────────────────────────────┐
│                                   CLI (src/compreg/cli.py)                │
│  doctor / list-tests / generate / verify / benchmark / baseline / compare │
│  history / minimize / report / triage / ctest                             │
└──────────────┬──────────────────────────────┬───────────────────────┬─────┘
               │                              │                       │
        config (TOML)               storage (SQLite)            reporting
               │                              │                       │
┌──────────────▼───────────────┐  ┌───────────▼───────────────────────┐ │
│ corpus/                      │  │ execution/                        │ │
│  registry: 26 curated tests  │  │  build.py  (isolated dirs, logs)  │ │
│  each with *.expected oracle │  │  runner.py (timeout, capture)     │ │
│  generator.py (seeded)       │  └──────────────┬────────────────────┘ │
└──────────────┬───────────────┘                 │                      │
               │                          ┌──────▼───────────────────┐  │
┌──────────────▼───────────────┐         │ verification/            │  │
│ compiler/                    │         │  oracle.py (exact/float/ │  │
│  base: CompileSpec, adapters │◄────────│            exit-code)    │  │
│  gcc / clang adapters        │         │  differential.py         │  │
│  discovery (+ version probe) │         │   (classify, artifacts)  │  │
└──────────────────────────────┘         └──────┬───────────┬───────┘  │
                                               │           │          │
                                  ┌────────────▼───┐  ┌────▼──────────┐│
                                  │ benchmarking/  │  │ triage/       ││
                                  │ statistics     │  │ classifier    ││
                                  │ runner (reps)  │  │ minimizer     ││
                                  │ regression rule│  │ revision_bisect│
                                  └───────┬────────┘  └───────────────┘│
                                          │                            │
                                   storage/database.py + repository.py │
                                   (schema v1, transactions)           │
                                                                       │
                                        reporting/json_report.py       │
                                        reporting/csv_report.py        │
                                        reporting/summary.py ◄─────────┘
```

## Module responsibilities

### compiler/
- `base.py` — `CompilerAdapter` ABC: argv-only command construction (never a
  shell string), robust version parsing (`version X.Y.Z` first, GCC's
  `g++ (distro 13.3.0-6) 13.3.0` fallback), `-dumpmachine` target probing,
  `CompilerError` for every expected failure mode. `compile_config_hash()`
  builds the stable configuration identity used for baselines.
- `gcc.py` / `clang.py` — family-specific driver candidates and banner regex.
- `discovery.py` — explicit configured path ⇒ PATH candidates; never assumes a
  tool exists. Returns `DiscoveryEntry(family, found, reason[, identity])`
  including what was tried; `probe_std_support` compiles a tiny program for
  `doctor`.

### corpus/
- `registry.py` — the authoritative test table. Every test couples a trusted
  source with an **independently derived oracle** (hand-verified arithmetic or
  a Python reference model):
  26 tests across arithmetic / loops / arrays / branches / boundary / sorting /
  bitwise / structs / recursion / strings + 2 benchmarks. Expected outputs are
  reviewable `.expected` sidecar files. Floating-point tests use the tolerant
  `float-list` oracle; benchmark checksums are IEEE-deterministic for the
  fixed operation order (verified identical at O0/O2/O3) and use tolerance to
  absorb FP-contraction differences under user `-march` flags.
- `generator.py` — a seeded LCG produces bounded programs whose expected
  outputs are computed by *the generator itself* with exact integer semantics.
  Determinism across platforms is unit-tested.

### execution/
- `build.py` — per-(test×config) isolated build directory under
  `artifacts/runs/<run>/build/<test>/`; records the exact command to
  `command.txt` and compiler capture to `compile.log`. Spawn/timeout/output
  failures become structured `CompileResult(ok=False, error_kind=...)`.
- `runner.py` — `subprocess.run` with **argument arrays**, wall-clock timing
  via `perf_counter`, `TimeoutExpired` handling, spawn-failure detection, and
  artifact persistence (`run.log`, `run_command.txt`). Classification helper
  maps an `ExecutionResult` to a failure category.

### verification/
- `oracle.py` — explicit normalization (per-line trailing whitespace + trailing
  blank lines only; interior blanks preserved), exact comparison with useful
  first-difference messages, and tolerant float-list comparison (relative
  tolerance with absolute floor, non-finite handling).
- `differential.py` — iterates tests × discovered compilers × opt levels.
  Every configuration is judged **only by that test's oracle**; cross-config
  agreement is evidence, not the pass criterion. Missing compilers produce
  SKIPPED rows with the reason (never silent). Artifacts + reproduction
  commands are attached to failures.

### benchmarking/
- `statistics.py` — median/min/max/MAD with input validation; MAD chosen for
  small-sample robustness.
- `runner.py` — repeated process execution (warm-ups discarded, measured
  samples kept), injectable clock/executor for deterministic tests.
- `regression.py` — the noisy-rules machine:
  `is_regression` requires BOTH a relative median growth AND an excess above
  `max(abs_threshold, k×MAD_baseline)`; insufficient samples and
  incompatible contexts produce explicit, non-regression verdicts. Also the
  compatibility guard (test id, config hash, benchmark version, machine).

### storage/
- `database.py` — schema v1 (runs, compiler, compile_config, test_case,
  correctness_result, benchmark_stat, benchmark_sample, baseline, regression,
  artifact), WAL mode, FKs on, engine-checked unique indices.
- `repository.py` — parameterized SQL + transactions; get-or-create semantics
  for identity rows (avoiding stale `lastrowid` from upsert-updates), baseline
  compatibility queries that never mix optimization levels, benchmark
  versions, or hosts.

### triage/
- `classifier.py` — evidence assembly: compiler identity/config, source hash,
  commands, exit code/timeout data, expected vs actual, artifact paths, and a
  clear observations-vs-hypotheses split. For benchmarks, attaches the
  baseline/current statistics.
- `minimizer.py` — line-level delta debugging with an evaluation budget;
  reduction is accepted only when a predicate (the failure) still holds and
  unchanged input is returned otherwise.
- `revision_bisect.py` — wraps `git bisect run` with argument arrays, explicit
  preconditions (git repo, resolvable revisions), explicit failure reasons and
  a logic reset on all exits.

### reporting/
Stable JSON schema `compreg.report.v1` (counts, per-test records,
per-regression records, metadata), flat CSV rows for spreadsheets, and the
plain-text terminal summary used by CLI commands.

## Data flow of one verification run

1. `load_config` (layered user TOML over `config/default.toml`) → validated.
2. `discover_compilers` → available entries + explicit missing reasons.
3. For each (test × compiler × opt level): build in an isolated directory →
   run with configured timeout → classify → oracle-decide → persist artifacts
   and, unless `--no-db`, store rows tied to a run row (with reproducibility
   metadata: host, platform, python, tool versions).
4. Return outcomes + stats; prints the summary; exit code per contract.
5. Failures get triage JSONs under `artifacts/runs/<tag>/triage/`.
