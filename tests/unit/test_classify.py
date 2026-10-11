"""Unit tests: exit-code classification of execution results."""

from __future__ import annotations

from compreg.execution.runner import classify_execution
from compreg.models import ExecutionResult


def _result(returncode=None, error_kind=None, timed_out=False):
    return ExecutionResult(
        ok=returncode in (0, None and True) if returncode is not None else (error_kind is None),
        command=["bin"],
        stdout="",
        stderr="",
        returncode=returncode,
        elapsed_s=0.01,
        timed_out=timed_out,
        error_kind=error_kind,
    )


def test_zero_exit_is_pass_candidate():
    assert classify_execution(_result(returncode=0)) == "PASS"


def test_nonzero_exit_is_nonzero_exit():
    assert classify_execution(_result(returncode=3)) == "NONZERO_EXIT"


def test_timeout_flag_maps_to_timeout():
    assert classify_execution(_result(returncode=None, error_kind="timeout", timed_out=True)) == "TIMEOUT"


def test_spawn_failure_is_infrastructure():
    assert classify_execution(_result(returncode=None, error_kind="spawn_failed: ENOENT")) == "INFRASTRUCTURE_ERROR"


def test_missing_exit_code_is_execution_error():
    assert classify_execution(_result(returncode=None)) == "EXECUTION_ERROR"


def test_none_result_is_infrastructure():
    assert classify_execution(None) == "INFRASTRUCTURE_ERROR"
