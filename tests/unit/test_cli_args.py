"""Unit tests: CLI argument handling and validation behavior."""

from __future__ import annotations

import pytest

from compreg.cli import EXIT_CONFIG, build_parser, main


def test_parser_requires_a_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_all_command_groups_parse():
    parser = build_parser()
    for argv in (
        ["doctor"],
        ["list-tests", "--category", "sorting", "--json"],
        ["verify", "--opts", "O0,O2", "--tests", "sorting_bubble_sort"],
        ["benchmark", "--reps", "3", "--ad-hoc-bench", "x.cpp", "--ad-hoc-id", "demo"],
        ["baseline", "create", "--run", "3", "--force"],
        ["compare", "--run", "3", "--baseline", "2"],
        ["history", "--limit", "3", "--test", "bench_x"],
        ["minimize", "--source", "x.cpp", "--expected", "y"],
        ["report", "--run", "latest", "--out", "prefix"],
        ["triage", "--run", "2"],
        ["generate", "--count", "3", "--seed", "7"],
        ["ctest", "--build-dir", "/tmp/build"],
    ):
        namespace = parser.parse_args(argv)
        assert hasattr(namespace, "func")


def test_main_reports_config_error_with_code_2(tmp_path):
    bad_config = tmp_path / "bad.toml"
    bad_config.write_text("[compilers]\nfamilies = ['msvc']\n", encoding="utf-8")
    rc = main(["verify", "--opts", "O2", "--config", str(bad_config)])
    assert rc == EXIT_CONFIG


def test_main_unknown_test_ids_exit_with_config_code():
    rc = main(["verify", "--tests", "definitely_not_a_test", "--no-db"])
    assert rc == EXIT_CONFIG


def test_generate_rejects_non_positive_count(tmp_path):
    rc = main(["generate", "--count", "0", "--seed", "1", "--out", str(tmp_path)])
    assert rc == EXIT_CONFIG
