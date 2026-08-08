"""Integração com o Docker CLI e Docker Compose.

Os comandos docker são executados como subprocessos herdando stdout/stderr,
preservando a formatação nativa do docker.
"""

from __future__ import annotations

import shutil
import subprocess

import structlog

from scylla.ui import print_error

DOCKER_BIN = "docker"
RUN_TIMEOUT = 120  # segundos

# Comandos sem argumento: nome do comando -> args do docker.
DOCKER_COMMANDS: dict[str, list[str]] = {
    "dps": ["ps"],
    "dpsa": ["ps", "-a"],
    "di": ["images"],
    "dcps": ["compose", "ps"],
    "dcup": ["compose", "up", "-d"],
    "dcdown": ["compose", "down"],
    "dclog": ["compose", "logs"],
    "dcrestart": ["compose", "restart"],
}

# Comandos que exigem um argumento (container/imagem): nome -> prefixo dos args.
ARGS_COMMANDS: dict[str, list[str]] = {
    "dlog": ["logs"],
    "dstop": ["stop"],
    "dstart": ["start"],
    "drm": ["rm"],
    "drmi": ["rmi"],
}


def docker_available() -> bool:
    """True se o binário docker existir no PATH."""
    return shutil.which(DOCKER_BIN) is not None


def run_docker(args: list[str]) -> int:
    """Executa ``docker <args>`` herdando stdout/stderr; retorna o exit code."""
    log = structlog.get_logger("scylla.docker")
    if not docker_available():
        print_error("Docker não encontrado no PATH.")
        log.error("docker_ausente")
        return 1
    log.debug("executando", comando=DOCKER_BIN, args=args)
    try:
        result = subprocess.run([DOCKER_BIN, *args], check=False, timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        print_error(f"Comando docker demorou demais (> {RUN_TIMEOUT}s) e foi abortado.")
        log.error("docker_timeout", args=args)
        return 1
    except OSError as exc:
        print_error(f"Falha ao executar docker: {exc}")
        log.error("docker_falhou", erro=str(exc))
        return 1
    log.debug("docker_ok", args=args, exit_code=result.returncode)
    return result.returncode
