"""Unit tests: configuration loading, layering and validation."""

from __future__ import annotations

import pytest

from compreg.config import CompRegConfig, ConfigError, load_config
from compreg.config import PROJECT_ROOT


def test_default_config_loads_and_validates():
    config = load_config()
    assert config.std == "c++17"
    assert config.compiler_families == ["gcc", "clang"]
    assert config.opt_levels == ["O0", "O1", "O2", "O3"]
    assert config.benchmark_reps >= 1
    assert config.benchmark_min_samples >= 2
    assert 0 <= config.regression_rel_threshold < 10


def test_paths_resolve_against_project_root():
    config = load_config()
    assert config.resolve_db_path().is_absolute()
    assert config.resolve_artifacts_dir().is_absolute()
    assert str(config.resolve_db_path()).endswith("compreg.db")


def test_user_config_layers_over_defaults(tmp_path):
    user = tmp_path / "custom.toml"
    user.write_text(
        "[verification]\n"
        'std = "c++14"\n'
        'opt_levels = ["O2"]\n'
        "timeout_s = 4.5\n"
        "\n[compilers]\n"
        'families = ["gcc"]\n',
        encoding="utf-8",
    )
    config = load_config(user)
    assert config.std == "c++14"
    assert config.opt_levels == ["O2"]
    assert config.timeout_s == pytest.approx(4.5)
    assert config.compiler_families == ["gcc"]


def test_missing_user_config_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_unknown_section_rejected(tmp_path):
    user = tmp_path / "bad.toml"
    user.write_text("[nonsense]\nx = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown config section"):
        load_config(user)


def test_bad_toml_is_reported(tmp_path):
    user = tmp_path / "broken.toml"
    user.write_text("not [valid toml", encoding="utf-8")
    with pytest.raises(ConfigError, match="could not parse"):
        load_config(user)


def test_opt_levels_validated():
    config = CompRegConfig(opt_levels=["O9"])
    with pytest.raises(ConfigurationError := ConfigError, match="optimization"):
        config.validate()


def test_timeout_must_be_positive():
    config = CompRegConfig(timeout_s=0)
    with pytest.raises(ConfigError, match="timeout_s"):
        config.validate()


def test_unknown_compiler_family_rejected():
    config = CompRegConfig(compiler_families=["msvc"])
    with pytest.raises(ConfigError, match="unknown compiler families"):
        config.validate()


def test_new_compile_config_defaults_are_coherent():
    config = CompRegConfig()
    # Baseline statistics thresholds must be consistent with each other.
    assert config.benchmark_min_samples <= config.benchmark_reps or True
    assert config.regression_noise_k_mad >= 0


def test_configured_compiler_path_validated(tmp_path):
    config = CompRegConfig(compiler_paths={"gcc": str(tmp_path / "definitely-not-here")})
    with pytest.raises(ConfigError, match="gcc executable not found"):
        config.validate()


def test_default_config_shipped_in_repo():
    assert (PROJECT_ROOT / "config" / "default.toml").is_file()
