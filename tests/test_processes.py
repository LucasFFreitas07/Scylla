"""Testes da lógica de processos (psutil mockado — sem tocar no SO real)."""

from __future__ import annotations

import os
from contextlib import nullcontext

import psutil
import pytest

from scylla import processes
from scylla.errors import (
    InvalidPidError,
    PermissionDeniedError,
    ProcessNotFoundError,
)
from scylla.processes import get_process_info, kill_process, list_processes


class FakeProc:
    """Processo fake: apenas o atributo .info consumido por process_iter."""

    def __init__(self, info: dict) -> None:
        self.info = info

    def __repr__(self) -> str:  # pragma: no cover
        return f"FakeProc(pid={self.info.get('pid')})"


class BrokenProc:
    """Processo que falha ao ler .info (AccessDenied/NoSuchProcess)."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    @property
    def info(self) -> dict:
        raise self._error


def _info(
    pid: int,
    name: str = "proc",
    user: str = "lucas",
    cpu: float = 1.0,
    mem: float = 2.0,
    status: str = "running",
    cmdline: list[str] | None = None,
) -> dict:
    return {
        "pid": pid,
        "name": name,
        "username": user,
        "cpu_percent": cpu,
        "memory_percent": mem,
        "status": status,
        "cmdline": cmdline or [name],
    }


# ---------------------------------------------------------------------------
# list_processes
# ---------------------------------------------------------------------------


def test_list_processes_ordena_por_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    procs = [
        FakeProc(_info(2, "b")),
        FakeProc(_info(1, "a")),
        FakeProc(_info(3, "c")),
    ]
    monkeypatch.setattr(processes.psutil, "process_iter", lambda **kwargs: procs)

    result = list_processes()

    assert [p.pid for p in result] == [1, 2, 3]


def test_list_processes_preenche_campos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        processes.psutil,
        "process_iter",
        lambda **kwargs: [FakeProc(_info(7, "bash", cmdline=["bash", "-c", "echo oi"]))],
    )

    result = list_processes()

    assert len(result) == 1
    p = result[0]
    assert p.pid == 7
    assert p.name == "bash"
    assert p.username == "lucas"
    assert p.cpu_percent == 1.0
    assert p.memory_percent == 2.0
    assert p.status == "running"
    assert p.cmdline == "bash -c echo oi"


def test_list_processes_ignora_falhas(monkeypatch: pytest.MonkeyPatch) -> None:
    procs = [
        FakeProc(_info(1, "ok")),
        BrokenProc(psutil.AccessDenied()),
        BrokenProc(psutil.NoSuchProcess(999)),
    ]
    monkeypatch.setattr(processes.psutil, "process_iter", lambda **kwargs: procs)

    result = list_processes()

    assert [p.pid for p in result] == [1]


def test_list_processes_trunca_cmdline(monkeypatch: pytest.MonkeyPatch) -> None:
    longo = "x" * 200
    monkeypatch.setattr(
        processes.psutil,
        "process_iter",
        lambda **kwargs: [FakeProc(_info(1, "proc", cmdline=[longo]))],
    )

    result = list_processes()

    assert len(result[0].cmdline) == processes.CMD_MAX_LEN


# ---------------------------------------------------------------------------
# get_process_info
# ---------------------------------------------------------------------------


class FakeTargetProc:
    """Processo com a API usada por get_process_info."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def oneshot(self) -> object:
        return nullcontext()

    def name(self) -> str:
        return "sleep"

    def username(self) -> str:
        return "lucas"

    def cpu_percent(self, interval: float | None = None) -> float:
        return 0.0

    def memory_percent(self) -> float:
        return 0.5

    def status(self) -> str:
        return "sleeping"

    def cmdline(self) -> list[str]:
        return ["sleep", "300"]


def test_get_process_info_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(processes.psutil, "Process", FakeTargetProc)

    info = get_process_info(10)

    assert info.pid == 10
    assert info.name == "sleep"
    assert info.status == "sleeping"


def test_get_process_info_pid_invalido() -> None:
    with pytest.raises(InvalidPidError):
        get_process_info(0)
    with pytest.raises(InvalidPidError):
        get_process_info(-5)


def test_get_process_info_nao_encontrado(monkeypatch: pytest.MonkeyPatch) -> None:
    class NaoExiste(FakeTargetProc):
        def name(self) -> str:
            raise psutil.NoSuchProcess(self.pid)

    monkeypatch.setattr(processes.psutil, "Process", NaoExiste)

    with pytest.raises(ProcessNotFoundError):
        get_process_info(10)


def test_get_process_info_sem_permissao(monkeypatch: pytest.MonkeyPatch) -> None:
    class SemPermissao(FakeTargetProc):
        def name(self) -> str:
            raise psutil.AccessDenied()

    monkeypatch.setattr(processes.psutil, "Process", SemPermissao)

    with pytest.raises(PermissionDeniedError):
        get_process_info(10)


# ---------------------------------------------------------------------------
# kill_process
# ---------------------------------------------------------------------------


class FakeKillProc:
    """Processo que registra terminate/kill e controla o wait."""

    def __init__(self, pid: int, *, wait_timeout: bool = False) -> None:
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.wait_timeout = wait_timeout

    def name(self) -> str:
        return "sleep"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float) -> None:
        if self.wait_timeout and self.terminated and not self.killed:
            raise psutil.TimeoutExpired(timeout, self.pid)


def test_kill_process_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKillProc(10)
    monkeypatch.setattr(processes.psutil, "Process", lambda pid: fake)

    msg = kill_process(10)

    assert fake.terminated and not fake.killed
    assert "SIGTERM" in msg


def test_kill_process_escala_para_sigkill(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKillProc(10, wait_timeout=True)
    monkeypatch.setattr(processes.psutil, "Process", lambda pid: fake)

    msg = kill_process(10)

    assert fake.terminated and fake.killed
    assert "SIGKILL" in msg


def test_kill_process_force(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKillProc(10)
    monkeypatch.setattr(processes.psutil, "Process", lambda pid: fake)

    msg = kill_process(10, force=True)

    assert not fake.terminated and fake.killed
    assert "SIGKILL" in msg


def test_kill_process_nao_encontrado(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_process(pid: int) -> FakeKillProc:
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(processes.psutil, "Process", fake_process)

    with pytest.raises(ProcessNotFoundError):
        kill_process(10)


def test_kill_process_sem_permissao(monkeypatch: pytest.MonkeyPatch) -> None:
    class SemPermissao(FakeKillProc):
        def terminate(self) -> None:
            raise psutil.AccessDenied()

    monkeypatch.setattr(processes.psutil, "Process", lambda pid: SemPermissao(pid))

    with pytest.raises(PermissionDeniedError):
        kill_process(10)


def test_kill_process_pid_invalido() -> None:
    with pytest.raises(InvalidPidError):
        kill_process(0)
    with pytest.raises(InvalidPidError):
        kill_process(-1)


def test_kill_process_proprio_processo() -> None:
    with pytest.raises(InvalidPidError):
        kill_process(os.getpid())
