# CompReg reporting formats

## JSON report — schema `compreg.report.v1`

```jsonc
{
  "schema": "compreg.report.v1",
  "metadata": {
    "run_id": 4, "started_at": "...", "host": "Linux/x86_64",
    "platform": "Linux-...-x86_64", "python_version": "3.12.3",
    "tool_versions": {"compreg": "1.0.0", "gcc": "gcc 13.3.0 (...)"},
    "notes": "verify: passed=26 failed=1 skipped=27",
    "artifacts": [{"results_dir": ".../artifacts/runs"}]
  },
  "summary": {
    "total": 54, "passed": 26, "failed": 1, "regressions": 0, "skipped": 27,
    "compile_errors": 0, "output_mismatches": 1, "nonzero_exits": 0,
    "timeouts": 0, "execution_errors": 0, "infrastructure_errors": 0
  },
  "tests": [
    {
      "test_id": "adhoc_broken_bubble_sort_9bccf35eb0", "category": "ad-hoc",
      "source_path": "...", "compiler": {"family": "gcc", "name": "gcc 13.3.0 (...)"},
      "opt_level": "O2", "std": "c++17", "config_hash": "b78080ce8f6d7df5",
      "source_sha256": "...", "status": "OUTPUT_MISMATCH", "message": "first differing line #1: ...",
      "timeout_s": 10.0,
      "detail": {"exit_code": 0, "elapsed_s": 0.0123, "timed_out": false},
      "reproduction": "g++ ... && ./broken_bubble_sort",
      "artifacts_dir": ".../results/..."
    }
    // PASS/SKIPPED entries omit "reproduction"
  ],
  "regressions": [
    {
      "test_id": "demo_workload", "config_hash": "...",
      "verdict": "regression", "baseline_median_s": 0.1056,
      "current_median_s": 0.2759, "slowdown_pct": 161.3, "explanation": "...",
      "baseline_samples": 5, "current_samples": 5
    }
  ]
}
```

Produced by `compreg report` (also written to `<prefix>.json` with `--out`).

## CSV exports

`<prefix>_correctness.csv` — one row per stored outcome:

```
test_id, category, compiler_family, compiler_version, opt_level, status,
message, exit_code, elapsed_s, config_hash, source_sha256, artifacts_dir,
reproduction
```

`<prefix>_benchmarks.csv` — one row per stored benchmark statistic:

```
test_id, category, compiler_family, compiler_version, opt_level, samples,
median_s, min_s, max_s, mad_s, row_kind
```

## Terminal summary

`reporting/summary.py` renders the same counts in ASCII tables for CLI
commands (verify/benchmark/report/history), plus explicit "skipped
configurations" and "regression verdicts" sections.

## Triage JSON (`compreg triage` / automatic per-run artifacts)

```jsonc
{
  "generated_at": "...",
  "test_id": "...", "category": "NONZERO_EXIT", "triage_class": "runtime_exit_failure",
  "compiler": { "family": "gcc", "version_text": "...", "target": "...", "std": "c++17",
                 "version_major": 13, "warnings": ["-Wall", "-Wextra"] },
  "configuration": { "opt_level": "O2", "config_hash": "...", "host": "..." },
  "reproduction": {
    "compile_command": "g++ -std=c++17 -O2 -Wall ...",
    "run_command": ".../binary",
    "source_sha256": "...", "opt_level": "O2", "std": "c++17"
  },
  "observations": ["execution exit code: 3, elapsed 0.005s, timed_out=False"],
  "hypotheses": ["hypothesis (unverified): ..."],
  "artifacts": { "artifacts_dir": "...</results/...>",
                 "actual_stdout": "partial result: 1 4 9 16 25",
                 "expected_exit_code": 3, "timeout_s": 10.0 },
  "baseline": null   // or { verdict, medians, slowdown_pct, explanation } for benchmarks
}
```

Hypotheses always carry the prefix "hypothesis (unverified)" — observations
are factual captures only; the framework never invents a root cause.
