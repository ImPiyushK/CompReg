# CompReg — Automated Compiler Verification & Regression Analysis

CompReg is a CPU-only framework that automatically compiles and runs
deterministic C++17 test programs with multiple compiler configurations,
identifies correctness and performance regressions, stores historical results
in SQLite, and produces structured failure evidence for triage.

**Status:** 117 pytest tests passing (97 unit + 20 integration) · CTest 3/3
(native C++ + pytest-via-CTest) · all 7 demo scenarios executed end-to-end ·
CI configured for GitHub Actions (Linux full pipeline + Windows MSYS2
compile-verify + ctest-only job).

**Scope statement:** CompReg verifies *standard desktop toolchains*
(GCC/Clang building for a host CPU). It does **not** verify NVIDIA's internal
compilers, CUDA, PTX, or GPU instruction semantics — it is a transferable
compiler-verification portfolio built around the same engineering practices
(oracle-driven differential testing, DB-based regression tracking,
delta-debugging triage, CI automation). See
[Relevance to compiler-verification roles](#relevance-to-compiler-verification-roles)
for how this maps onto compiler-verification internship work, and
[Extending toward GPU toolchains](#extending-toward-gpu-toolchains-honest-roadmap--not-implemented)
for the honest boundary.

## Relevance to compiler-verification roles

This project was built to demonstrate the *verification-engineering* skills a
compiler verification team needs (e.g., NVIDIA's compiler verification team),
on hardware everyone has — a CPU — while being explicit about what it does
not cover:

| Typical compiler-verification responsibility | Where CompReg demonstrates it | Command to see it |
|---|---|---|
| Implement C/C++ programs that verify a compiler | 26-program C++17 differential corpus; every outcome is decided by an independently derived oracle (hand-verified arithmetic / Python reference models) — compiler agreement is never the pass criterion | `compreg verify` |
| Design tools, libraries and automation for the compiler verification process | The whole framework: compiler adapters, isolated build/execute engine, 7-way failure classification, SQLite history, noise-aware regression engine, triage + minimization, CLI, CI | `scripts/run_demo.sh all` |
| Scalable verification infrastructure across compiler releases | Compiler/version/config-hash identity, persisted baselines, release-over-release comparison with compatibility guards, transparent skip reporting | `compreg benchmark && compreg baseline create && compreg compare` |
| Debugging reproducible failures with compiler & hardware teams | Triage reports separating observations from hypotheses, exact reproduction commands, delta-debugging minimization, git bisect integration | `compreg triage`, `compreg minimize`, `pytest tests/integration/test_bisect_real_repo.py` |
| Strong C/C++ and Python skills | Typed, stdlib-only Python orchestration with injectable test seams; C++17 corpus plus a native CTest-tested kernel library | `pytest`, `compreg ctest` |
| Language-specification awareness | Corpus engineered against undefined behavior (guarded shifts, unsigned wrap semantics, no signed overflow), IEEE/FP-contraction-aware tolerances, `-std` handling | `tests/unit/test_corpus.py`, `docs/limitations.md` |

What this project deliberately does **not** claim: any GPU, CUDA, PTX, or
NVIDIA-internal-compiler verification; machine-learning-based triage;
parallel-programming content. The engineering transfer is the methodology —
oracle design, differential testing, regression gating, and evidence-based
failure investigation.

## Capabilities

| Capability | Status |
|---|---|
| GCC adapter (discovery, versions, flag construction) | implemented + tested |
| Clang adapter | implemented; used automatically when installed, otherwise reported as unavailable |
| Differential testing across compilers/optimization levels | implemented + tested (oracle-decided, never "compilers agree") |
| Oracle kinds | exact output, tolerant numeric list, exit code |
| Result classification | PASS, COMPILE_ERROR, OUTPUT_MISMATCH, NONZERO_EXIT, TIMEOUT, EXECUTION_ERROR, INFRASTRUCTURE_ERROR (+ reporting-only SKIPPED) |
| Deterministic test corpus | 26 curated UB-free programs with independently verified expected outputs |
| Deterministic generator (seeded) | implemented + tested; oracles computed by the generator, not by a compiler |
| Benchmarking | repeated wall-clock measurement, median/min/max/MAD, warmups, correctness gate |
| Regression statistics | relative threshold + absolute floor + k×MAD noise model; min sample counts; unit-tested |
| SQLite history | normalized schema v1, runs/results/samples/baselines/regressions/artifacts |
| Baseline compatibility | test id + config hash + benchmark version + (optional) host machine profile |
| Triage | structured failure evidence with observations/hypotheses split |
| Test-case minimization | line-level delta debugging, failure-preserving (documented limits) |
| Git revision bisection | implemented; git-bisect-run contract (0=good, 125=skip, nonzero=bad) verified by a real bisect integration test |
| Reports | stable JSON schema (`compreg.report.v1`), CSV exports, terminal summary |
| Build system | CMake + native C++ tests registered with CTest; pytest wired into CTest |
| CI | GitHub Actions (linux full pipeline, windows platform portability, ctest-only job) |

## Repository layout

```
CompReg/
├── README.md, LICENSE, .gitignore, pyproject.toml, CMakeLists.txt, CTestConfig.cmake
├── config/default.toml          # all thresholds/timeouts/paths
├── src/compreg/                 # Python framework (stdlib-only runtime)
│   ├── cli.py  config.py  models.py  util.py
│   ├── compiler/                # base adapter, gcc, clang, discovery
│   ├── corpus/                  # registry (26 curated tests) + generator
│   ├── execution/               # build engine + runner (subprocess, timeouts)
│   ├── verification/            # oracles + differential orchestration
│   ├── benchmarking/            # runner, statistics, regression rules
│   ├── storage/                 # sqlite schema + typed repository
│   ├── triage/                  # classifier, minimizer, revision bisect
│   └── reporting/               # json_report, csv_report, summary
├── cpp/                         # native C++17 library + CTest tests
├── test_corpus/                 # curated sources + *.expected artifacts
├── examples/                    # deliberately broken/slow demo fixtures
├── tests/                       # pytest unit + integration suites
├── scripts/run_demo.sh          # the 7 demonstration scenarios
└── docs/                        # architecture, installation, usage, ...
```

## How to run (fresh clone)

Full setup details (Windows/WSL/MSYS2, no-sudo machines): [docs/installation.md](docs/installation.md).

```bash
git clone https://github.com/<your-user>/CompReg.git && cd CompReg

# Linux/WSL — any Python >= 3.11; gcc (or clang) on PATH.
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # runtime is stdlib-only; dev brings pytest/cmake/ninja

compreg doctor                   # capability report: compilers, sqlite, cmake/ctest, git, corpus
compreg list-tests               # browse the 26-test corpus + 2 benchmarks

compreg verify                   # full differential sweep: tests x compilers x O0..O3
compreg benchmark --opts O2      # correctness gate -> repeated timing -> SQLite
compreg baseline create          # persist baselines (minimum sample count enforced)
compreg compare                  # noise-aware regression verdicts
compreg history                  # run listing / per-test regression timeline
compreg report                   # JSON (compreg.report.v1) + 2 CSVs + terminal summary
compreg triage                   # failure-evidence JSONs with reproduction commands
compreg minimize --source examples/minimize_payload.cpp \
    --expected "$(printf '265\n86')" --opt O2   # delta-debugging demo (59 -> 21 lines)

pytest                           # 117 tests (97 unit + 20 integration)
compreg ctest                    # cmake configure + C++ build + CTest (native + pytest)
bash scripts/run_demo.sh all     # all 7 demonstration scenarios end-to-end (~4 min)
```

Windows 10: WSL is the full-fidelity path (identical to the above). Native
Windows works via MSYS2 UCRT64 gcc — `pacman -S mingw-w64-ucrt-x86_64-gcc`
and put `C:\msys64\ucrt64\bin` on PATH; that is exactly what the windows CI
job does.

No-sudo machines: `python3 -m venv --without-pip .venv`, bootstrap pip with
`get-pip.py`, then `pip install -e ".[dev]"` — `pip install cmake ninja`
provides CMake/CTest without any system package manager.

Verification exit codes: `0` overall success · `1` verification failures or
detected regressions · `2` configuration/usage error · `3` infrastructure
error.

## Demonstrations (evidence in this repo)

`scripts/run_demo.sh <1..7|all>` reproduces the seven documented scenarios:

1. **Successful verification** — 26 tests × configs; passes shown; missing
   compilers listed as SKIPPED, never dropped.
2. **Correctness regression** — a deliberately inverted-comparison bubble
   sort is classified OUTPUT_MISMATCH (well-defined logic error, no UB).
3. **Compilation/runtime failures** — syntax-error fixture → COMPILE_ERROR
   with no execution attempted; infinite-loop fixture → TIMEOUT.
4. **Regression statistics** — deterministic synthetic measurements prove the
   noise-aware rule (jitter → no_regression; +60% → regression; 3 samples →
   insufficient_samples). No wall-clock claim is made here.
5. **Historical regression** — SQLite baseline from a fast benchmark run, then
   a real wall-clock run of a deliberately slowed variant (identical output,
   different source) shows `regression +~160%`.
6. **Reproducible triage** — full evidence JSON (compiler identity, config
   hash, both commands, source hash, captured output paths) plus line-level
   minimization (59 → 21 lines) that preserves the exact failing output.
7. **CI** — native CTest suite + pytest through automated entry points
   (`.github/workflows/ci.yml` runs the same workflows on GitHub).

Actual recorded runs are quoted in [docs/testing.md](docs/testing.md).

## Testing

```bash
pytest tests/unit              # 97 mandatory tests (no compiler needed)
pytest tests/integration       # 20 tests using the installed compiler(s) + real git bisect
pytest                         # everything (117)
pytest -m "not slow"           # quick subset
compreg ctest                  # cmake configure+build+ctest (native C++ tests)
```

Design detail: timing-sensitive checks use **injected measurements**, so
ordinary tests never depend on wall-clock thresholds; real wall-clock
benchmarking is demonstrated in scenario 5 and documented as machine-dependent.

## Extending toward GPU toolchains (honest roadmap — NOT implemented)

None of the following exists in this repository; this section describes where
the design would extend, so the boundary is explicit:

- `src/compreg/compiler/base.py` defines the `CompilerAdapter` ABC (discovery,
  version probing, argv construction, structured results). A `nvcc`/`ptxas`
  verification driver would be a new adapter class plus a discovery entry —
  the corpus, oracle, benchmark, storage, triage and reporting machinery are
  compiler-agnostic and would be reused unchanged.
- Differential oracles for GPU code would need GPU-specific references
  (e.g., PTX/SASS-level semantics or a simulator), which is exactly the
  NVIDIA-internal problem domain this project deliberately does not claim.
- The CPU-only constraint was a design choice to keep the portfolio runnable
  anywhere; nothing in the architecture assumes a CPU compiler beyond the
  two shipped adapters.

## Documentation

- [docs/architecture.md](docs/architecture.md) — module responsibilities
- [docs/installation.md](docs/installation.md) — Windows / Linux / WSL setup
- [docs/usage.md](docs/usage.md) — command reference + examples
- [docs/testing.md](docs/testing.md) — test map + observed results
- [docs/reporting.md](docs/reporting.md) — report schema + CSV columns
- [docs/limitations.md](docs/limitations.md) — honest boundaries

## Repository hygiene

CompReg creates machine-specific outputs while running verification, benchmarks,
triage, and demonstrations. These are runtime artifacts, not source files, and
should generally not be committed:

- `.venv/` or `venv/` — local Python environments; recreate them from the
  dependency files instead of sharing them.
- `artifacts/` — generated reports, logs, benchmark outputs, SQLite databases,
  and compiled test binaries. The demo scripts recreate their outputs.
- `dist/`, `build/`, `cmake-build*/`, `.pytest_cache/`, `__pycache__/`, and
  `*.pyc` — generated packaging, build, and cache files.
- `.git/` — local Git repository metadata. **Keep this directory in your
  working checkout**; it is not source content and should not be manually
  deleted to clean the project. Git does not push `.git/` as part of a commit.

The repository's `.gitignore` excludes the common generated paths. Before
committing, review the staged files:

```bash
git status --short
git diff --cached --stat
```

If generated files were accidentally tracked in an earlier commit, add the
appropriate paths to `.gitignore` and untrack them without deleting local copies:

```bash
git rm -r --cached --ignore-unmatch .venv venv artifacts dist .pytest_cache
```

Then review `git status` and commit the intended changes. Back up any reports or
databases you need before removing generated directories. Keep source code,
tests, fixtures, configuration, documentation, and CI workflows in Git.

## License

MIT — see [LICENSE](LICENSE).
