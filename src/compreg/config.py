"""Configuration loading, validation and CLI-override helpers.

Configuration precedence (highest wins):
  1. explicit CLI flags
  2. user config file (--config PATH)
  3. bundled config/default.toml
Values are validated eagerly: invalid values raise ConfigError with an
actionable message instead of failing later at runtime.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .util import ensure_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.toml"

KNOWN_COMPILER_FAMILIES = ("gcc", "clang")
KNOWN_OPT_LEVELS = ("O0", "O1", "O2", "O3")


class ConfigError(ValueError):
    """Raised when configuration values are missing or invalid."""


@dataclass
class CompRegConfig:
    project_root: Path = PROJECT_ROOT
    compiler_families: List[str] = field(default_factory=lambda: list(KNOWN_COMPILER_FAMILIES))
    compiler_paths: Dict[str, str] = field(default_factory=dict)  # family -> explicit exe
    std: str = "c++17"
    opt_levels: List[str] = field(default_factory=lambda: ["O0", "O1", "O2", "O3"])
    timeout_s: float = 10.0
    warnings: List[str] = field(default_factory=lambda: ["-Wall", "-Wextra"])
    extra_flags: List[str] = field(default_factory=list)
    float_tolerance: float = 1e-9

    benchmark_reps: int = 7
    benchmark_warmup: int = 2
    benchmark_timeout_multiplier: float = 10.0
    benchmark_min_samples: int = 5
    benchmark_version: str = "v1"

    regression_rel_threshold: float = 0.20
    regression_abs_threshold_s: float = 0.010
    regression_noise_k_mad: float = 3.0

    db_path: Path = PROJECT_ROOT / "artifacts" / "compreg.db"
    artifacts_dir: Path = PROJECT_ROOT / "artifacts"

    require_same_host: bool = True
    keep_failure_binaries: bool = True
    log_level: str = "INFO"

    # ------------------------------------------------------------------ #
    # path resolution
    # ------------------------------------------------------------------ #
    def resolve(self, relative: str | Path) -> Path:
        """Resolve a config-relative path against the project root."""
        path = Path(relative)
        if path.is_absolute():
            return path
        return self.project_root / path

    def resolve_db_path(self) -> Path:
        path = self.resolve(self.db_path)
        ensure_dir(path.parent)
        return path

    def resolve_artifacts_dir(self) -> Path:
        return ensure_dir(self.resolve(self.artifacts_dir))

    def compiler_executable(self, family: str) -> Optional[str]:
        """Explicitly configured executable for a family, if any and present."""
        raw = self.compiler_paths.get(family, "")
        if not raw:
            return None
        path = Path(self.resolve(raw) if not Path(raw).is_absolute() else raw)
        return str(path) if path.exists() else None

    def runtime_env(self) -> Dict[str, str]:
        """Environment passed to subprocesses: a copy of the current process
        environment. Returning None-equivalent empty behavior would be wrong:
        subprocess.run(env={}) *replaces* the entire environment, which
        breaks PATH-based tool invocations (e.g. gcc's collect2/ld)."""
        env: Dict[str, str] = dict(os.environ)
        # Deterministic library behavior for benchmark stability:
        env.setdefault("OMP_NUM_THREADS", "1")
        return env

    # ------------------------------------------------------------------ #
    # validation
    # ------------------------------------------------------------------ #
    def validate(self) -> None:
        problems: List[str] = []

        unknown_families = [f for f in self.compiler_families if f not in KNOWN_COMPILER_FAMILIES]
        if unknown_families:
            problems.append(
                f"unknown compiler families {unknown_families}; supported: {list(KNOWN_COMPILER_FAMILIES)}"
            )
        if not self.compiler_families:
            problems.append("compiler families list must not be empty")

        bad_opts = [o for o in self.opt_levels if o not in KNOWN_OPT_LEVELS]
        if bad_opts:
            problems.append(f"unknown optimization levels {bad_opts}; supported: {list(KNOWN_OPT_LEVELS)}")
        if not self.opt_levels:
            problems.append("opt_levels list must not be empty")

        if self.std not in {"c++98", "c++03", "c++11", "c++14", "c++17", "c++20", "c++23"}:
            problems.append(f"unsupported language standard '{self.std}'")

        if self.timeout_s <= 0:
            problems.append(f"timeout_s must be > 0 (got {self.timeout_s})")
        if self.benchmark_timeout_multiplier <= 0:
            problems.append(
                f"benchmark.timeout_multiplier must be > 0 (got {self.benchmark_timeout_multiplier})"
            )
        if self.benchmark_reps < 1:
            problems.append(f"benchmark.reps must be >= 1 (got {self.benchmark_reps})")
        if self.benchmark_warmup < 0:
            problems.append(f"benchmark.warmup must be >= 0 (got {self.benchmark_warmup})")
        if self.benchmark_min_samples < 2:
            problems.append(f"benchmark.min_samples must be >= 2 (got {self.benchmark_min_samples})")
        if not self.benchmark_version:
            problems.append("benchmark.benchmark_version must not be empty")

        if self.regression_rel_threshold < 0:
            problems.append(
                f"regression.rel_threshold must be >= 0 (got {self.regression_rel_threshold})"
            )
        if self.regression_abs_threshold_s < 0:
            problems.append(
                f"regression.abs_threshold_s must be >= 0 (got {self.regression_abs_threshold_s})"
            )
        if self.regression_noise_k_mad < 0:
            problems.append(
                f"regression.noise_k_mad must be >= 0 (got {self.regression_noise_k_mad})"
            )
        if self.float_tolerance < 0:
            problems.append(f"verification.float_tolerance must be >= 0 (got {self.float_tolerance})")

        for family in KNOWN_COMPILER_FAMILIES:
            raw = self.compiler_paths.get(family, "")
            if raw and shutil.which(raw) is None and not self.resolve(raw).exists():
                problems.append(
                    f"configured {family} executable not found: '{raw}' "
                    f"(tried as command on PATH and as project-relative path)"
                )

        if problems:
            raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(problems))


def load_config(path: str | Path | None = None) -> CompRegConfig:
    """Load the default config, optionally layered with a user TOML file."""
    config = CompRegConfig()
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        if path is not None:  # explicit user config must exist
            raise ConfigError(f"config file not found: {config_path}")
    else:
        try:
            with open(config_path, "rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"could not parse config '{config_path}': {exc}") from exc

        _apply_setting(config, data)
    config.validate()
    return config


def _apply_setting(config: CompRegConfig, data: Dict) -> None:
    """Apply a parsed TOML dict onto a config object (validating keys)."""
    known_sections = {
        "compilers",
        "compiler_paths",
        "verification",
        "benchmark",
        "regression",
        "paths",
        "comparisons",
        "storage",
    }
    for section, values in data.items():
        if section not in known_sections:
            raise ConfigError(f"unknown config section '{section}' in [section] table")
        if not isinstance(values, dict):
            raise ConfigError(f"config section '{section}' must be a table")

    compilers = data.get("compilers", {})
    if "families" in compilers:
        config.compiler_families = list(compilers["families"])

    for family in KNOWN_COMPILER_FAMILIES:
        raw = data.get("compiler_paths", {}).get(family, "")
        if raw:
            config.compiler_paths[family] = str(raw)

    ver = data.get("verification", {})
    if "std" in ver:
        config.std = str(ver["std"])
    if "opt_levels" in ver:
        config.opt_levels = [str(o) for o in ver["opt_levels"]]
    if "timeout_s" in ver:
        config.timeout_s = float(ver["timeout_s"])
    if "warnings" in ver:
        config.warnings = [str(w) for w in ver["warnings"]]
    if "extra_flags" in ver:
        config.extra_flags = [str(f) for f in ver["extra_flags"]]
    if "float_tolerance" in ver:
        config.float_tolerance = float(ver["float_tolerance"])

    bench = data.get("benchmark", {})
    if "reps" in bench:
        config.benchmark_reps = int(bench["reps"])
    if "warmup" in bench:
        config.benchmark_warmup = int(bench["warmup"])
    if "timeout_multiplier" in bench:
        config.benchmark_timeout_multiplier = float(bench["timeout_multiplier"])
    if "min_samples" in bench:
        config.benchmark_min_samples = int(bench["min_samples"])
    if "benchmark_version" in bench:
        config.benchmark_version = str(bench["benchmark_version"])

    reg = data.get("regression", {})
    if "rel_threshold" in reg:
        config.regression_rel_threshold = float(reg["rel_threshold"])
    if "abs_threshold_s" in reg:
        config.regression_abs_threshold_s = float(reg["abs_threshold_s"])
    if "noise_k_mad" in reg:
        config.regression_noise_k_mad = float(reg["noise_k_mad"])

    paths = data.get("paths", {})
    if "db" in paths:
        config.db_path = Path(paths["db"])
    if "artifacts" in paths:
        config.artifacts_dir = Path(paths["artifacts"])

    comparisons = data.get("comparisons", {})
    if "require_same_host" in comparisons:
        config.require_same_host = bool(comparisons["require_same_host"])

    storage = data.get("storage", {})
    if "keep_failure_binaries" in storage:
        config.keep_failure_binaries = bool(storage["keep_failure_binaries"])
    if "log_level" in storage:
        config.log_level = str(storage["log_level"])
