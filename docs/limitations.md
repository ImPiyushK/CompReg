# CompReg limitations and honesty notes

This file documents what CompReg does NOT do. Every remaining limitation was
observed during development; none is a fabricated capability claim.

## Scope

- CompReg verifies **GCC/Clang for host CPUs**. It does not verify NVIDIA
  internal compilers, CUDA, PTX, GPU instruction semantics, or GPU
  performance. Transferability to compiler-verification work is the point,
  not equivalence with that environment.
- Clang is an optional capability. On environments without Clang all
  corresponding configurations are reported as SKIPPED with the reason; demos
  recorded in this repository ran GCC-only.

## Oracle coverage rules

- Curated tests use **independently derived** expectations (hand-verified
  values or Python reference models). Two compilers agreeing is collected as
  evidence but is never the pass criterion.
- Generated programs compute their expected outputs in the generator with
  exact integer semantics.
- Benchmark checksum oracles: `bench_matrix`'s checksum is
  IEEE-deterministic for its fixed operation order on default x86-64 codegen
  (verified identical at O0/O2/O3). It is validated with a *tolerant* oracle
  so FP-contraction differences under user flags like `-march=native` are not
  reported as compiler defects.
- Test sources are treated as **trusted or reviewed code**; there is no
  sandbox. Subprocess execution enforces timeouts and captures, but malicious
  source code could deliberately damage its environment. Do not run sources
  you do not trust.

## Benchmarking honesty

- Every measured sample includes process startup and filesystem overhead.
  The bundled benchmarks (hundreds of ms at -O0, tens of ms at -O2) make that
  overhead a small fraction of the measurement; if you benchmark tiny
  programs, startup noise will dominate and numbers become meaningless.
- The regression rule flags a regression only when the median grows beyond a
  relative threshold AND beyond `max(abs_threshold, k × MAD_baseline)` with
  enough samples on both sides. This avoids labeling ordinary jitter as a
  regression but cannot detect subtle or noisy-but-small regressions; the
  rule is deliberately conservative rather than trigger-happy.
- Wall-clock benchmarks are **machine-dependent**: during development, the
  same O2 binary measured 34 ms vs 47 ms medians across sessions (CPU state
  variance). The `incompatible` guard deliberately blocks cross-machine
  comparisons; run baseline/current back-to-back on the same machine, as the
  demo scripts do.
- Performance-regression *detection logic* is validated with injected
  measurement data (deterministic unit tests and `scripts/run_demo.sh 4`).
  Real wall-clock demonstration is scenario 5; numbers there are local
  machine results, not universal performance claims.

## Minimization and bisect

- The minimizer is **line-granular**: it cannot split lines, reorder code, or
  substitute tokens. It evaluates by compiling/executing candidates, so it
  reduces to the smallest text reproducing the identical failing behavior —
  its result is a starting point for a human, not an AST-level fault
  localizer.
- With extreme-parallelism machines, adversarial scheduling, or genuinely
  unreliable failures, minimization will correctly refuse to reduce and keep
  the original input (`reduced=False`).
- Git bisect is a best-effort helper: it requires a git repository, resolvable
  revisions, and a deterministic predicate command; otherwise it reports the
  precise limitation (it never fabricates a "first bad commit").

## Platform notes

- **Linux (GCC/Clang)** is the fully validated platform: all recorded runs in
  this repository were produced on Linux (GCC 13.3.0).
- Windows orchestration is platform-aware (executable suffixes, `list2cmdline`
  quoting, venv-aware tool discovery including pip-installed
  `cmake.exe`/`ninja.exe` under `%PREFIX%\Scripts`). The windows CI job
  installs a native GCC (MSYS2 UCRT64), runs the unit suite + doctor, then
  executes a real C++17 compile-and-verify subset and the CTest suite.
  Boundary (honest): the corpus' exact-string `.expected` artifacts were
  generated with Linux glibc. The Windows CI subset excludes tests that are
  sensitive to exotic float formatting; a full-corpus Windows run is possible
  but not gated in CI. Native MSVC (cl.exe) adapter behavior has NOT been
  validated anywhere and remains out of scope.
- WSL alternative (full-fidelity Windows path): run the complete Linux
  workflow inside WSL with no changes.
- Curated sources use `printf` formatting; the same glibc under GCC/Clang on
  Linux gives byte-identical output, verified in this repository. On Windows
  hosts, CRT formatting differences are absorbed by the tolerant numeric
  oracles where used.

## Known smaller gaps

- `compreg compare` matches baselines by stored benchmark contexts; if you
  benchmark an ad-hoc test without `--ad-hoc-id`, the auto id is
  content-hash-derived, so a later "same" run compares cleanly only when the
  source content is unchanged (deliberately: unchanged source = same
  benchmark).
- The framework's own SQLite schema is versioned (`schema_meta`) but there is
  no migration tooling beyond initialization; schema v1 is the only version.
- Cross-compilation, sanitizers, and coverage instrumentation are supported
  only via `extra_flags`; there are no dedicated sanitizier-orchestration
  commands.
- CTest registers the pytest suite only when the interpreter configured by
  CMake can import pytest; otherwise it prints a status line and runs only
  the native tests.
