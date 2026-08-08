"""REPL persistente estilo Hermes Agent: tela de apresentação + prompt contínuo."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from scylla.errors import ScyllaError
from scylla.processes import get_process_info, kill_process, list_processes
from scylla.ui import (
    confirm_kill,
    get_console,
    print_error,
    render_table,
    show_process_panel,
    welcome_screen,
)

COMMANDS = ["ps", "kill", "help", "clear", "exit", "quit"]

PROMPT_STYLE = Style.from_dict({"prompt": "bold cyan"})

HELP_TEXT = """\
[bold cyan]Scylla CLI[/] — comandos disponíveis:

  [bold]ps[/]               Lista os processos em uma tabela
  [bold]kill <PID>[/]      Mata um processo (com confirmação)
  [bold]help[/]            Mostra esta ajuda
  [bold]clear[/]           Limpa a tela
  [bold]exit[/]            Sai do scylla (ou Ctrl+D)

Dicas: Tab autocompleta, ↑/↓ navega o histórico.
"""


def _history_file() -> Path:
    cache_base = os.environ.get("XDG_CACHE_HOME")
    cache_dir = Path(cache_base) if cache_base else Path.home() / ".cache"
    history_dir = cache_dir / "scylla"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / "history"


def _run_ps() -> None:
    log = structlog.get_logger("scylla.shell.ps")
    try:
        procs = list_processes()
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("ps_falhou", erro=str(exc))
        return
    render_table(procs)
    log.debug("ps_ok", total=len(procs))


def _run_kill(args: list[str]) -> None:
    log = structlog.get_logger("scylla.shell.kill")
    if len(args) != 1:
        print_error("Uso: kill <PID>")
        return
    raw_pid = args[0]
    try:
        pid = int(raw_pid)
    except ValueError:
        print_error(f"PID inválido: {raw_pid}")
        return

    try:
        info = get_process_info(pid)
    except ScyllaError as exc:
        print_error(str(exc))
        return

    show_process_panel(info)
    if not confirm_kill(info):
        get_console().print("[yellow]Operação cancelada.[/]")
        log.info("kill_cancelado", pid=pid)
        return

    try:
        message = kill_process(pid)
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("kill_falhou", pid=pid, erro=str(exc))
        return
    get_console().print(f"[green]{message}[/]")
    log.info("kill_ok", pid=pid)


def run_shell() -> None:
    """Loop principal: tela de apresentação + prompt persistente."""
    log = structlog.get_logger("scylla.shell")
    welcome_screen()

    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(_history_file())),
        completer=WordCompleter(COMMANDS, ignore_case=True),
        style=PROMPT_STYLE,
    )
    log.info("sessao_iniciada")

    while True:
        try:
            raw = session.prompt("scylla> ")
        except (KeyboardInterrupt, EOFError):
            get_console().print()
            break
        text = raw.strip()
        if not text:
            continue
        parts = text.split()
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("exit", "quit"):
            break
        if cmd == "ps":
            _run_ps()
        elif cmd == "kill":
            _run_kill(args)
        elif cmd == "help":
            get_console().print(HELP_TEXT)
        elif cmd == "clear":
            get_console().clear()
        else:
            print_error(f"Comando desconhecido: {cmd}. Digite 'help' para ver os comandos.")

    log.info("sessao_encerrada")
