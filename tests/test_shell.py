"""Testes do shell interativo (REPL persistente) com entrada simulada."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from scylla import shell
from scylla.errors import ProcessNotFoundError
from scylla.processes import ProcessInfo


class FakeSession:
    """Substitui PromptSession: devolve entradas pré-programadas."""

    inputs: ClassVar[list[str]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._inputs = iter(self.inputs)

    def prompt(self, *args: object, **kwargs: object) -> str:
        return next(self._inputs)


def _fake_proc() -> ProcessInfo:
    return ProcessInfo(
        pid=7,
        name="bash",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="running",
        cmdline="bash",
    )


def _run_shell(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> None:
    monkeypatch.setattr(FakeSession, "inputs", inputs)
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    monkeypatch.setattr(shell, "list_processes", lambda: [_fake_proc()])
    shell.run_shell()


def test_shell_ps_e_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_shell(monkeypatch, ["ps", "exit"])
    out = capsys.readouterr().out

    assert "Scylla CLI" in out  # tela de apresentação
    assert "Xx$XxxXXX" in out  # arte ASCII do logo (imagem convertida, 50x32)
    assert "bash" in out  # resultado do ps dentro do shell
    assert "PID" in out


def test_shell_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _run_shell(monkeypatch, ["help", "exit"])
    out = capsys.readouterr().out

    assert "comandos disponíveis" in out
    assert "kill <PID>" in out


def test_shell_comando_desconhecido(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_shell(monkeypatch, ["foo", "exit"])
    err = capsys.readouterr().err

    assert "Comando desconhecido: foo" in err


def test_shell_entrada_vazia(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_shell(monkeypatch, ["", "exit"])
    capsys.readouterr()  # não deve levantar


def test_shell_kill_sucesso(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(FakeSession, "inputs", ["kill 7", "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    monkeypatch.setattr(shell, "get_process_info", lambda pid: _fake_proc())
    monkeypatch.setattr(shell, "confirm_kill", lambda info: True)
    monkeypatch.setattr(
        shell, "kill_process", lambda pid, **kwargs: "Processo bash (PID 7) encerrado com SIGTERM."
    )

    shell.run_shell()
    out = capsys.readouterr().out

    assert "SIGTERM" in out


def test_shell_kill_cancelado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(FakeSession, "inputs", ["kill 7", "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    monkeypatch.setattr(shell, "get_process_info", lambda pid: _fake_proc())
    monkeypatch.setattr(shell, "confirm_kill", lambda info: False)
    # kill_process não deve ser chamado quando o usuário recusa
    monkeypatch.setattr(
        shell, "kill_process", lambda pid, **kwargs: pytest.fail("não deveria matar")
    )

    shell.run_shell()
    out = capsys.readouterr().out

    assert "cancelada" in out.lower()


def test_shell_kill_uso_errado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_shell(monkeypatch, ["kill", "exit"])
    err = capsys.readouterr().err

    assert "Uso: kill <PID>" in err


def test_shell_kill_pid_nao_numerico(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_shell(monkeypatch, ["kill abc", "exit"])
    err = capsys.readouterr().err

    assert "PID inválido: abc" in err


def test_shell_kill_nao_encontrado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(FakeSession, "inputs", ["kill 999", "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)

    def nao_existe(pid: int) -> ProcessInfo:
        raise ProcessNotFoundError(f"Processo {pid} não encontrado (já foi encerrado?).")

    monkeypatch.setattr(shell, "get_process_info", nao_existe)

    shell.run_shell()
    err = capsys.readouterr().err

    assert "não encontrado" in err


def test_shell_kill_falha_ao_matar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(FakeSession, "inputs", ["kill 7", "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    monkeypatch.setattr(shell, "get_process_info", lambda pid: _fake_proc())
    monkeypatch.setattr(shell, "confirm_kill", lambda info: True)

    from scylla.errors import PermissionDeniedError

    def sem_permissao(pid: int, **kwargs: object) -> str:
        raise PermissionDeniedError(f"Sem permissão para matar o processo {pid}.")

    monkeypatch.setattr(shell, "kill_process", sem_permissao)

    shell.run_shell()
    err = capsys.readouterr().err

    assert "permissão" in err.lower()


def test_shell_ps_erro(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(FakeSession, "inputs", ["ps", "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)

    def erro() -> list[ProcessInfo]:
        raise ProcessNotFoundError("Falha ao listar processos.")

    monkeypatch.setattr(shell, "list_processes", erro)

    shell.run_shell()
    err = capsys.readouterr().err

    assert "Falha ao listar processos" in err


def test_history_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))

    path = shell._history_file()

    assert path == cache / "scylla" / "history"
    assert path.parent.is_dir()


# ---------------------------------------------------------------------------
# Comandos docker no shell
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("dps", ["ps"]),
        ("dpsa", ["ps", "-a"]),
        ("di", ["images"]),
        ("dcps", ["compose", "ps"]),
        ("dcup", ["compose", "up", "-d"]),
        ("dcdown", ["compose", "down"]),
        ("dclog", ["compose", "logs"]),
        ("dcrestart", ["compose", "restart"]),
    ],
)
def test_shell_docker_sem_argumento(
    monkeypatch: pytest.MonkeyPatch, entrada: str, esperado: list[str]
) -> None:
    chamadas: list[list[str]] = []
    monkeypatch.setattr(FakeSession, "inputs", [entrada, "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    monkeypatch.setattr(shell, "run_docker", lambda a: chamadas.append(a))

    shell.run_shell()

    assert chamadas == [esperado]


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("dlog nginx", ["logs", "nginx"]),
        ("dstop web", ["stop", "web"]),
        ("dstart web", ["start", "web"]),
        ("drm web", ["rm", "web"]),
        ("drmi alpine", ["rmi", "alpine"]),
    ],
)
def test_shell_docker_com_argumento(
    monkeypatch: pytest.MonkeyPatch, entrada: str, esperado: list[str]
) -> None:
    chamadas: list[list[str]] = []
    monkeypatch.setattr(FakeSession, "inputs", [entrada, "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    monkeypatch.setattr(shell, "run_docker", lambda a: chamadas.append(a))

    shell.run_shell()

    assert chamadas == [esperado]


@pytest.mark.parametrize("entrada", ["dlog", "dstop", "drmi"])
def test_shell_docker_falta_argumento(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], entrada: str
) -> None:
    monkeypatch.setattr(FakeSession, "inputs", [entrada, "exit"])
    monkeypatch.setattr(shell, "PromptSession", FakeSession)
    # run_docker não deve ser chamado quando falta o argumento
    monkeypatch.setattr(
        shell, "run_docker", lambda a: pytest.fail("não deveria executar docker")
    )

    shell.run_shell()
    err = capsys.readouterr().err

    assert f"Uso: {entrada} <nome>" in err
