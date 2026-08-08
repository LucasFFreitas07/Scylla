"""Lógica de listagem e kill de processos via psutil."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import psutil

from scylla.errors import (
    InvalidPidError,
    PermissionDeniedError,
    ProcessNotFoundError,
)

CMD_MAX_LEN = 60


@dataclass(frozen=True)
class ProcessInfo:
    """Dados de um processo usados na tabela e no painel de confirmação."""

    pid: int
    name: str
    username: str
    cpu_percent: float
    memory_percent: float
    status: str
    cmdline: str


def _clean(value: object, fallback: str = "?") -> str:
    return str(value).strip() if value else fallback


def _cpu_percent(proc: psutil.Process) -> float:
    """CPU% médio desde o início do processo (via /proc/<pid>/stat).

    O ``psutil`` só calcula CPU instantânea com duas amostras; numa única
    varredura ele retorna 0.0. Aqui usamos o tempo de CPU acumulado dividido
    pelo tempo de vida do processo, o que dá um valor real e barato.
    """
    try:
        with proc.oneshot():
            cpu_times = proc.cpu_times()
            create_time = proc.create_time()
        elapsed = time.time() - create_time
        if elapsed <= 0:
            return 0.0
        total = cpu_times.user + cpu_times.system
        return total / elapsed * 100.0
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return 0.0


def list_processes() -> list[ProcessInfo]:
    """Lista todos os processos visíveis (sem ordenação)."""
    procs: list[ProcessInfo] = []
    for proc in psutil.process_iter(
        attrs=[
            "pid",
            "name",
            "username",
            "memory_percent",
            "status",
            "cmdline",
        ]
    ):
        try:
            info = proc.info
            procs.append(
                ProcessInfo(
                    pid=int(info["pid"]),
                    name=_clean(info["name"]),
                    username=_clean(info["username"]),
                    cpu_percent=_cpu_percent(proc),
                    memory_percent=float(info["memory_percent"] or 0.0),
                    status=_clean(info["status"]),
                    cmdline=" ".join(info["cmdline"] or [])[:CMD_MAX_LEN],
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            # Processo morreu no meio da iteração ou sem permissão: ignora.
            continue
    return procs


SORT_KEYS = {
    "pid": lambda p: p.pid,
    "cpu": lambda p: p.cpu_percent,
    "mem": lambda p: p.memory_percent,
    "resources": lambda p: p.cpu_percent + p.memory_percent,
}


def sort_processes(procs: list[ProcessInfo], by: str = "resources") -> list[ProcessInfo]:
    """Ordena processos.

    ``by``: ``pid`` (crescente) ou ``cpu``/``mem``/``resources`` (decrescente).
    O padrão ``resources`` coloca primeiro os que mais consomem CPU+memória.
    """
    if by == "pid":
        return sorted(procs, key=lambda p: p.pid)
    key = SORT_KEYS.get(by, SORT_KEYS["resources"])
    return sorted(procs, key=key, reverse=True)


def get_process_info(pid: int) -> ProcessInfo:
    """Retorna os dados de um PID específico (para o painel de confirmação)."""
    if pid <= 0:
        raise InvalidPidError(f"PID inválido: {pid}. Use um inteiro positivo.")
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            return ProcessInfo(
                pid=pid,
                name=_clean(proc.name()),
                username=_clean(proc.username()),
                cpu_percent=proc.cpu_percent(interval=None),
                memory_percent=proc.memory_percent(),
                status=_clean(proc.status()),
                cmdline=" ".join(proc.cmdline() or [])[:CMD_MAX_LEN],
            )
    except psutil.NoSuchProcess:
        raise ProcessNotFoundError(
            f"Processo {pid} não encontrado (já foi encerrado?)."
        ) from None
    except psutil.AccessDenied:
        raise PermissionDeniedError(
            f"Sem permissão para inspecionar o processo {pid}."
        ) from None


def kill_process(pid: int, *, force: bool = False) -> str:
    """Mata o processo ``pid`` e retorna mensagem de sucesso.

    force=False: envia SIGTERM e aguarda até 3s; se continuar vivo, aplica SIGKILL.
    force=True: envia SIGKILL direto.
    """
    if pid <= 0:
        raise InvalidPidError(f"PID inválido: {pid}. Use um inteiro positivo.")
    if pid == os.getpid():
        raise InvalidPidError("Não é possível matar o próprio processo scylla.")

    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
    except psutil.NoSuchProcess:
        raise ProcessNotFoundError(
            f"Processo {pid} não encontrado (já foi encerrado?)."
        ) from None

    try:
        if force:
            proc.kill()  # SIGKILL
            _wait_quiet(proc, timeout=5)
            return f"Processo {proc_name} (PID {pid}) morto com SIGKILL."
        proc.terminate()  # SIGTERM
        try:
            proc.wait(timeout=3)
        except psutil.TimeoutExpired:
            proc.kill()
            _wait_quiet(proc, timeout=5)
            return (
                f"Processo {proc_name} (PID {pid}) não respondeu ao SIGTERM; "
                "SIGKILL aplicado."
            )
        return f"Processo {proc_name} (PID {pid}) encerrado com SIGTERM."
    except psutil.AccessDenied:
        raise PermissionDeniedError(
            f"Sem permissão para matar o processo {proc_name} (PID {pid}). "
            "Tente com sudo ou como o dono do processo."
        ) from None
    except psutil.NoSuchProcess:
        raise ProcessNotFoundError(
            f"Processo {pid} não encontrado (já foi encerrado?)."
        ) from None


def _wait_quiet(proc: psutil.Process, *, timeout: float) -> None:
    try:
        proc.wait(timeout=timeout)
    except (psutil.TimeoutExpired, psutil.NoSuchProcess):
        pass
