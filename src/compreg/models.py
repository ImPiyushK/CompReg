"""Core data models shared across CompReg modules.

All records are intentionally plain dataclasses so they serialize to
JSON/reports and into SQLite without adapter layers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ResultCategory(str, Enum):
    """Classification of a single test/configuration outcome."""

    PASS = "PASS"
    COMPILE_ERROR = "COMPILE_ERROR"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    NONZERO_EXIT = "NONZERO_EXIT"
    TIMEOUT = "TIMEOUT"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    # Reporting-only status for configurations that could not run at all
    # (e.g. requested compiler family not installed). Never used for a test
    # that was executed.
    SKIPPED = "SKIPPED"


#: Categories that count as verification failures for exit-code purposes.
FAILURE_CATEGORIES = frozenset(
    {
        ResultCategory.COMPILE_ERROR,
        ResultCategory.OUTPUT_MISMATCH,
        ResultCategory.NONZERO_EXIT,
        ResultCategory.TIMEOUT,
        ResultCategory.EXECUTION_ERROR,
        ResultCategory.INFRASTRUCTURE_ERROR,
    }
)


class OracleKind(str, Enum):
    EXACT = "exact"            # normalized exact stdout match
    FLOAT_LIST = "float-list"  # compare numbers in output with tolerance
    EXIT_CODE = "exit-code"    # only require a specific exit code


@dataclass(frozen=True)
class OracleSpec:
    """How the output of a test case is judged.

    For floating-point programs values are rounded by different platforms and
    libms; `float-list` compares parsed numbers with a relative tolerance so
    formatting differences are not reported as compiler defects.
    """

    kind: OracleKind = OracleKind.EXACT
    expected_stdout: str = ""
    expected_exit_code: int = 0
    tolerance: float = 1e-9
    normalize_whitespace: bool = True

    @property
    def has_expected_output(self) -> bool:
        return self.kind != OracleKind.EXIT_CODE

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "OracleSpec":
        return OracleSpec(
            kind=OracleKind(data.get("kind", OracleKind.EXACT.value)),
            expected_stdout=data.get("expected_stdout", ""),
            expected_exit_code=int(data.get("expected_exit_code", 0)),
            tolerance=float(data.get("tolerance", 1e-9)),
            normalize_whitespace=bool(data.get("normalize_whitespace", True)),
        )

    @staticmethod
    def from_json(text: str) -> "OracleSpec":
        return OracleSpec.from_dict(json.loads(text))


@dataclass(frozen=True)
class TestCase:
    """A deterministic, trusted test program with a known validation oracle.

    `source_path` is stored relative to the project root so results remain
    reproducible on other machines/checkout directories.
    """

    test_id: str
    source_path: str
    category: str
    description: str
    oracle: OracleSpec
    timeout_s: float = 10.0
    benchmark_eligible: bool = False
    benchmark_version: Optional[str] = None

    @property
    def is_benchmark(self) -> bool:
        return self.benchmark_eligible

    def reference_key(self) -> Tuple[str, ...]:
        return (self.test_id, self.category)


@dataclass
class CompilerIdentity:
    """Everything needed to identify and reproduce a compiler/configuration."""

    family: str                      # "gcc" | "clang"
    executable: str                  # path as discovered/configured
    version_text: str
    version_major: Optional[int] = None
    version_minor: Optional[int] = None
    version_patch: Optional[int] = None
    target: Optional[str] = None     # -dumpmachine result when available
    std: str = "c++17"
    extra_flags: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ("-Wall", "-Wextra")

    @property
    def display_name(self) -> str:
        version = ".".join(
            str(part)
            for part in (self.version_major, self.version_minor, self.version_patch)
            if part is not None
        )
        base = f"{self.family} {version}" if version else self.family
        if self.target:
            return f"{base} ({self.target})"
        return base

    def version_tuple(self) -> Tuple[int, ...]:
        return tuple(  # type: ignore[return-value]
            part
            for part in (
                self.version_major,
                self.version_minor,
                self.version_patch,
            )
            if part is not None
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompileResult:
    """Structured outcome of compiling one source file."""

    ok: bool
    command: List[str]
    stdout: str
    stderr: str
    returncode: Optional[int]
    elapsed_s: float
    binary_path: Optional[str] = None
    error_kind: Optional[str] = None  # "spawn_failed" | "compile_failed" | ...


@dataclass
class ExecutionResult:
    """Structured outcome of executing one compiled binary."""

    ok: bool
    command: List[str]
    stdout: str
    stderr: str
    returncode: Optional[int]
    elapsed_s: float
    timed_out: bool = False
    error_kind: Optional[str] = None  # "spawn_failed" | "timeout" | ...


@dataclass
class TestOutcome:
    """One test case run under one compiler/configuration."""

    test_case: TestCase
    identity: CompilerIdentity
    opt_level: str
    config_hash: str
    category: ResultCategory
    message: str = ""
    compile_result: Optional[CompileResult] = None
    execution_result: Optional[ExecutionResult] = None
    source_sha256: str = ""
    artifacts_dir: str = ""
    reproduction_compile: List[str] = field(default_factory=list)
    reproduction_run: List[str] = field(default_factory=list)
    skip_reason: Optional[str] = None  # set only for SKIPPED outcomes

    @property
    def is_failure(self) -> bool:
        return self.category in FAILURE_CATEGORIES

    @property
    def is_benchmarkable(self) -> bool:
        return self.category == ResultCategory.PASS and self.test_case.benchmark_eligible


@dataclass
class BenchmarkStats:
    """Summary statistics over repeated measurements of one configuration."""

    samples: int
    median_s: float
    min_s: float
    max_s: float
    mad_s: float  # median absolute deviation

    def noise_floor_s(self, k: float) -> float:
        """k * MAD; the minimum difference treated as signal, not noise."""
        return k * self.mad_s

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegressionVerdict:
    """Result of comparing one benchmark result against one baseline."""

    test_id: str
    config_hash: str
    compatible: bool
    incompatibility_reason: Optional[str]
    baseline_median_s: Optional[float]
    current_median_s: Optional[float]
    baseline_samples: Optional[int]
    current_samples: Optional[int]
    slowdown_pct: Optional[float]
    verdict: str  # regression|no_regression|insufficient_samples|incompatible|statistics_error
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunMeta:
    """Metadata for one verification/benchmark session."""

    run_id: Optional[int]
    started_at: str
    status: str
    host: str
    platform: str
    python_version: str
    tool_versions: Dict[str, str] = field(default_factory=dict)
    notes: str = ""

    @staticmethod
    def start(tool_versions: Dict[str, str]) -> "RunMeta":
        from .util import machine_profile, now_iso, platform_string, python_version_string

        return RunMeta(
            run_id=None,
            started_at=now_iso(),
            status="running",
            host=machine_profile(),
            platform=platform_string(),
            python_version=python_version_string(),
            tool_versions=tool_versions,
        )
