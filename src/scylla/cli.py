"""Definição do app Typer: comandos ``ps``, ``kill`` e shell interativo."""

from __future__ import annotations

import os

import structlog
import typer

from scylla import __version__
from scylla import shell as shell_mod
from scylla.dockertools import ARGS_COMMANDS, DOCKER_COMMANDS, run_docker
from scylla.errors import ScyllaError
from scylla.logging_setup import setup_logging
from scylla.processes import (
    SORT_KEYS,
    get_process_info,
    kill_process,
    list_processes,
    sort_processes,
)
from scylla.ui import confirm_kill, print_error, render_table, show_process_panel

app = typer.Typer(
    help="Scylla — gerencie processos e Docker do seu sistema Linux.",
    add_completion=True,
)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Mostra a versão e sai."),
    json_logs: bool = typer.Option(False, "--json-logs", help="Emite logs em JSON (útil em pipes)."),
    no_color: bool = typer.Option(False, "--no-color", help="Desativa cores na saída."),
) -> None:
    """Scylla — gerencie os processos do seu sistema Linux."""
    if no_color:
        os.environ["NO_COLOR"] = "1"
    setup_logging(json_logs=json_logs)
    if version:
        typer.echo(f"scylla {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        # Modo persistente: `scylla` sem argumentos abre a sessão interativa.
        shell_mod.run_shell()


@app.command()
def ps(
    sort_by: str = typer.Option(
        "resources",
        "--sort",
        "-s",
        help="Ordena por: pid, cpu, mem ou resources (padrão: resources).",
    ),
    top: int | None = typer.Option(
        None,
        "--top",
        "-n",
        help="Mostra apenas os N processos de maior consumo.",
    ),
) -> None:
    """Lista os processos do sistema em uma tabela."""
    log = structlog.get_logger("scylla.cli.ps")
    if sort_by not in SORT_KEYS:
        print_error(f"Ordenação inválida: {sort_by}. Use: pid, cpu, mem ou resources.")
        raise typer.Exit(1)
    if top is not None and top <= 0:
        print_error("--top deve ser um inteiro positivo.")
        raise typer.Exit(1)
    try:
        procs = list_processes()
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("ps_falhou", erro=str(exc))
        raise typer.Exit(exc.exit_code) from exc
    procs = sort_processes(procs, by=sort_by)
    if top is not None:
        procs = procs[:top]
    render_table(procs, top=top)
    log.debug("ps_ok", total=len(procs), sort=sort_by, top=top)


@app.command()
def kill(
    pid: int = typer.Argument(..., help="PID do processo a matar."),
    force: bool = typer.Option(False, "--force", "-f", help="Envia SIGKILL direto, sem SIGTERM."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (útil em scripts)."),
) -> None:
    """Mata um processo pelo PID, com confirmação."""
    log = structlog.get_logger("scylla.cli.kill")

    try:
        info = get_process_info(pid)
    except ScyllaError as exc:
        print_error(str(exc))
        raise typer.Exit(exc.exit_code) from exc

    show_process_panel(info)
    if not yes and not confirm_kill(info):
        typer.echo("Operação cancelada.")
        log.info("kill_cancelado", pid=pid)
        raise typer.Exit(0)

    try:
        message = kill_process(pid, force=force)
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("kill_falhou", pid=pid, erro=str(exc))
        raise typer.Exit(exc.exit_code) from exc
    typer.echo(message)
    log.info("kill_ok", pid=pid, force=force)


def _exit_docker(args: list[str]) -> None:
    """Executa um comando docker e propaga o exit code."""
    log = structlog.get_logger("scylla.cli.docker")
    code = run_docker(args)
    log.debug("docker_ok", args=args, exit_code=code)
    if code:
        raise typer.Exit(code)


# ---------------------------------------------------------------------------
# Docker (comandos mínimos: d* = docker, dc* = docker compose)
# ---------------------------------------------------------------------------


@app.command()
def dps() -> None:
    """Lista containers em execução (docker ps)."""
    _exit_docker(DOCKER_COMMANDS["dps"])


@app.command()
def dpsa() -> None:
    """Lista todos os containers, incluindo parados (docker ps -a)."""
    _exit_docker(DOCKER_COMMANDS["dpsa"])


@app.command()
def di() -> None:
    """Lista as imagens locais (docker images)."""
    _exit_docker(DOCKER_COMMANDS["di"])


@app.command()
def dlog(container: str = typer.Argument(..., help="Nome ou ID do container.")) -> None:
    """Mostra os logs de um container (docker logs <container>)."""
    _exit_docker([*ARGS_COMMANDS["dlog"], container])


@app.command()
def dstop(container: str = typer.Argument(..., help="Nome ou ID do container.")) -> None:
    """Para um container (docker stop <container>)."""
    _exit_docker([*ARGS_COMMANDS["dstop"], container])


@app.command()
def dstart(container: str = typer.Argument(..., help="Nome ou ID do container.")) -> None:
    """Inicia um container parado (docker start <container>)."""
    _exit_docker([*ARGS_COMMANDS["dstart"], container])


@app.command()
def drm(container: str = typer.Argument(..., help="Nome ou ID do container.")) -> None:
    """Remove um container (docker rm <container>)."""
    _exit_docker([*ARGS_COMMANDS["drm"], container])


@app.command()
def drmi(image: str = typer.Argument(..., help="Nome ou ID da imagem.")) -> None:
    """Remove uma imagem (docker rmi <imagem>)."""
    _exit_docker([*ARGS_COMMANDS["drmi"], image])


@app.command()
def dcps() -> None:
    """Lista os serviços do compose (docker compose ps)."""
    _exit_docker(DOCKER_COMMANDS["dcps"])


@app.command()
def dcup() -> None:
    """Sobe os serviços do compose em segundo plano (docker compose up -d)."""
    _exit_docker(DOCKER_COMMANDS["dcup"])


@app.command()
def dcdown() -> None:
    """Derruba os serviços do compose (docker compose down)."""
    _exit_docker(DOCKER_COMMANDS["dcdown"])


@app.command()
def dclog() -> None:
    """Mostra os logs dos serviços do compose (docker compose logs)."""
    _exit_docker(DOCKER_COMMANDS["dclog"])


@app.command()
def dcrestart() -> None:
    """Reinicia os serviços do compose (docker compose restart)."""
    _exit_docker(DOCKER_COMMANDS["dcrestart"])


def main() -> None:
    """Entry point do console script (``scylla``)."""
    app()
