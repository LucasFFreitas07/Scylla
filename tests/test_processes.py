"""Testes da lógica de processos (psutil mockado — sem tocar no SO real)."""

from __future__ import annotations

import os
import time
from contextlib import nullcontext

import psutil
import pytest

from scylla import processes
from scylla.errors import (
    InvalidPidError,
    PermissionDeniedError,
    ProcessNotFoundError,
)
from scylla.processes import (
    ProcessInfo,
    get_process_info,
    kill_process,
    list_processes,
    sort_processes,
)


class _FakeCpuTimes:
    def __init__(self, user: float = 0.0, system: float = 0.0) -> None:
        self.user = user
        self.system = system


class FakeProc:
    """Processo fake: .info consumido por process_iter + cpu_times/create_time."""

    def __init__(
        self,
        info: dict,
        cpu_times: _FakeCpuTimes | None = None,
        create_time: float | None = None,
    ) -> None:
        self.info = info
        self._cpu_times = cpu_times if cpu_times is not None else _FakeCpuTimes()
        self._create_time = create_time

    def cpu_times(self) -> _FakeCpuTimes:
        return self._cpu_times

    def create_time(self) -> float:
        if self._create_time is None:
            return time.time()  # elapsed ~0 → cpu 0.0
        return self._create_time

    def oneshot(self) -> object:
        return nullcontext()

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


def test_list_processes_preserva_ordem(monkeypatch: pytest.MonkeyPatch) -> None:
    procs = [
        FakeProc(_info(2, "b")),
        FakeProc(_info(1, "a")),
        FakeProc(_info(3, "c")),
    ]
    monkeypatch.setattr(processes.psutil, "process_iter", lambda **kwargs: procs)

    result = list_processes()

    assert [p.pid for p in result] == [2, 1, 3]  # ordem de iteração


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
    assert p.cpu_percent == 0.0  # elapsed ~0 → cpu 0.0
    assert p.memory_percent == 2.0
    assert p.status == "running"
    assert p.cmdline == "bash -c echo oi"


def test_list_processes_computa_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProc(
        _info(7, "bash"),
        cpu_times=_FakeCpuTimes(user=5.0, system=0.0),
        create_time=time.time() - 10,
    )
    monkeypatch.setattr(processes.psutil, "process_iter", lambda **kwargs: [fake])

    result = list_processes()

    assert result[0].cpu_percent == pytest.approx(50.0, abs=1.0)


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
# sort_processes
# ---------------------------------------------------------------------------


def _mk(pid: int, cpu: float, mem: float) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name="proc",
        username="lucas",
        cpu_percent=cpu,
        memory_percent=mem,
        status="running",
        cmdline="cmd",
    )


def test_sort_resources_desc() -> None:
    procs = [_mk(1, 10, 5), _mk(2, 1, 50), _mk(3, 20, 20)]
    # scores: p2=51, p3=40, p1=15
    result = sort_processes(procs)
    assert [p.pid for p in result] == [2, 3, 1]


def test_sort_cpu() -> None:
    procs = [_mk(1, 10, 5), _mk(2, 50, 1)]
    assert [p.pid for p in sort_processes(procs, by="cpu")] == [2, 1]


def test_sort_mem() -> None:
    procs = [_mk(1, 10, 5), _mk(2, 50, 1)]
    assert [p.pid for p in sort_processes(procs, by="mem")] == [1, 2]


def test_sort_pid_crescente() -> None:
    procs = [_mk(2, 0, 0), _mk(1, 0, 0)]
    assert [p.pid for p in sort_processes(procs, by="pid")] == [1, 2]


def test_sort_invalido_fallback_resources() -> None:
    procs = [_mk(1, 10, 5), _mk(2, 1, 50)]
    assert [p.pid for p in sort_processes(procs, by="xyz")] == [2, 1]


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
