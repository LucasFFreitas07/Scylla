"""Testes de caminhos de erro da interface CLI."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from scylla.cli import app
from scylla.errors import PermissionDeniedError, ProcessNotFoundError, ScyllaError
from scylla.processes import ProcessInfo

runner = CliRunner()


def _proc() -> ProcessInfo:
    return ProcessInfo(
        pid=42,
        name="sleep",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="sleeping",
        cmdline="sleep 300",
    )


def test_ps_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scylla.cli.list_processes",
        lambda: (_ for _ in ()).throw(ProcessNotFoundError("Processo não encontrado.")),
    )

    result = runner.invoke(app, ["ps"])

    assert result.exit_code == 2
    assert "Erro" in result.output


def test_kill_sem_permissao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scylla.cli.get_process_info",
        lambda pid: (_ for _ in ()).throw(
            PermissionDeniedError(f"Sem permissão para inspecionar o processo {pid}.")
        ),
    )

    result = runner.invoke(app, ["kill", "42"])

    assert result.exit_code == 2
    assert "permissão" in result.output.lower()


def test_kill_falha_ao_matar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scylla.cli.get_process_info", lambda pid: _proc())
    monkeypatch.setattr(
        "scylla.cli.kill_process",
        lambda pid, **kwargs: (_ for _ in ()).throw(
            PermissionDeniedError(f"Sem permissão para matar o processo {pid}.")
        ),
    )

    result = runner.invoke(app, ["kill", "42", "--yes"])

    assert result.exit_code == 2
    assert "permissão" in result.output.lower()


def test_scylla_error_exit_code_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scylla.cli.get_process_info",
        lambda pid: (_ for _ in ()).throw(ScyllaError("Erro customizado", exit_code=1)),
    )

    result = runner.invoke(app, ["kill", "42"])

    assert result.exit_code == 1
    assert "Erro customizado" in result.output


def test_no_color_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scylla.cli.list_processes", lambda: [_proc()])

    try:
        result = runner.invoke(app, ["--no-color", "ps"])
        assert result.exit_code == 0
        assert "NO_COLOR" in __import__("os").environ
    finally:
        __import__("os").environ.pop("NO_COLOR", None)
