"""Testes da interface CLI (Typer) com CliRunner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from scylla import __version__
from scylla.cli import app
from scylla.processes import ProcessInfo

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"scylla {__version__}" in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Scylla" in result.output
    assert "ps" in result.output
    assert "kill" in result.output


def test_ps_mostra_tabela(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = ProcessInfo(
        pid=42,
        name="sleep",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="sleeping",
        cmdline="sleep 300",
    )
    monkeypatch.setattr("scylla.cli.list_processes", lambda: [proc])

    result = runner.invoke(app, ["ps"])

    assert result.exit_code == 0
    assert "PID" in result.output
    assert "NOME" in result.output
    assert "sleep" in result.output
    assert "42" in result.output


def test_ps_sort_option(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = ProcessInfo(
        pid=42,
        name="sleep",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="sleeping",
        cmdline="sleep 300",
    )
    monkeypatch.setattr("scylla.cli.list_processes", lambda: [proc])

    result = runner.invoke(app, ["ps", "--sort", "mem"])

    assert result.exit_code == 0
    assert "sleep" in result.output


def test_ps_sort_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scylla.cli.list_processes", list)

    result = runner.invoke(app, ["ps", "--sort", "xyz"])

    assert result.exit_code == 1
    assert "Ordenação inválida" in result.output


def test_kill_com_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = ProcessInfo(
        pid=42,
        name="sleep",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="sleeping",
        cmdline="sleep 300",
    )
    monkeypatch.setattr("scylla.cli.get_process_info", lambda pid: proc)
    monkeypatch.setattr(
        "scylla.cli.kill_process",
        lambda pid, **kwargs: "Processo sleep (PID 42) encerrado com SIGTERM.",
    )

    result = runner.invoke(app, ["kill", "42", "--yes"])

    assert result.exit_code == 0
    assert "SIGTERM" in result.output


def test_kill_cancelado_pelo_usuario(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = ProcessInfo(
        pid=42,
        name="sleep",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="sleeping",
        cmdline="sleep 300",
    )
    monkeypatch.setattr("scylla.cli.get_process_info", lambda pid: proc)
    monkeypatch.setattr("scylla.cli.confirm_kill", lambda info: False)
    # kill_process nunca deve ser chamado quando o usuário recusa
    monkeypatch.setattr("scylla.cli.kill_process", lambda pid, **kwargs: pytest.fail("não deveria matar"))

    result = runner.invoke(app, ["kill", "42"])

    assert result.exit_code == 0
    assert "cancelada" in result.output.lower()


def test_kill_processo_inexistente() -> None:
    result = runner.invoke(app, ["kill", "999999999"])
    assert result.exit_code == 2
    assert "não encontrado" in result.output.lower()


def test_kill_pid_nao_numerico() -> None:
    result = runner.invoke(app, ["kill", "abc"])
    assert result.exit_code == 2  # erro de uso do typer
