"""Definição do app Typer: comandos ``ps``, ``kill`` e shell interativo."""

from __future__ import annotations

import os

import structlog
import typer

from scylla import __version__
from scylla import shell as shell_mod
from scylla.errors import ScyllaError
from scylla.logging_setup import setup_logging
from scylla.processes import get_process_info, kill_process, list_processes
from scylla.ui import confirm_kill, print_error, render_table, show_process_panel

app = typer.Typer(
    help="Scylla — gerencie os processos do seu sistema Linux.",
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
def ps() -> None:
    """Lista os processos do sistema em uma tabela."""
    log = structlog.get_logger("scylla.cli.ps")
    try:
        procs = list_processes()
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("ps_falhou", erro=str(exc))
        raise typer.Exit(exc.exit_code) from exc
    render_table(procs)
    log.debug("ps_ok", total=len(procs))


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


def main() -> None:
    """Entry point do console script (``scylla``)."""
    app()
