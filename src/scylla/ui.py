"""Renderização rich: tabela de processos, tela de apresentação e confirmação."""

from __future__ import annotations

import questionary
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from scylla import __version__
from scylla.processes import ProcessInfo


def get_console() -> Console:
    """Console para stdout, criado no momento do uso.

    Criar por chamada (em vez de cachear) garante que, em testes com
    CliRunner/capsys, o console capture o stdout/stderr isolado no momento
    da impressão e não segure arquivos fechados de testes anteriores.
    """
    return Console()


def get_err_console() -> Console:
    return Console(stderr=True)


STATUS_COLORS = {
    "running": "green",
    "sleeping": "yellow",
    "idle": "cyan",
    "zombie": "red",
    "stopped": "magenta",
    "disk-sleep": "blue",
    "tracing-stop": "magenta",
    "parked": "cyan",
}


def render_table(procs: list[ProcessInfo]) -> None:
    """Renderiza a tabela de processos."""
    table = Table(title=f"Processos — {len(procs)}", box=box.ROUNDED, expand=False)
    table.add_column("PID", justify="right", style="cyan", no_wrap=True)
    table.add_column("NOME", style="bold")
    table.add_column("USUÁRIO")
    table.add_column("CPU %", justify="right")
    table.add_column("MEM %", justify="right")
    table.add_column("STATUS", justify="center")
    table.add_column("CMD", overflow="ellipsis")

    for p in procs:
        table.add_row(
            str(p.pid),
            p.name,
            p.username,
            f"{p.cpu_percent:.1f}",
            f"{p.memory_percent:.1f}",
            Text(p.status, style=STATUS_COLORS.get(p.status, "white")),
            p.cmdline,
        )
    get_console().print(table)


LOGO = r"""
███████╗ ██████╗██╗   ██╗██╗     ██╗      █████╗
██╔════╝██╔════╝╚██╗ ██╔╝██║     ██║     ██╔══██╗
███████╗██║      ╚████╔╝ ██║     ██║     ███████║
╚════██║██║       ╚██╔╝  ██║     ██║     ██╔══██║
███████║╚██████╗   ██║   ███████╗███████╗██║  ██║
╚══════╝ ╚═════╝   ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝
"""


def welcome_screen() -> None:
    """Tela de apresentação estilo Hermes Agent."""
    content = Text.from_markup(
        "[bold cyan]Gerenciador de processos e Docker para Linux[/]\n\n"
        "[yellow]Comandos:[/] [bold]ps[/] | [bold]kill <PID>[/] | [bold]dps[/] "
        "| [bold]help[/] | [bold]exit[/]\n"
        "[dim]Dica: d* = docker (dps, dlog...), dc* = compose (dcup, dcdown...). "
        "Tab autocompleta, ↑/↓ navega o histórico, Ctrl+D encerra.[/]"
    )
    panel = Panel(
        content,
        title=f"[bold cyan]Scylla CLI[/]  [dim]v{__version__}[/]",
        subtitle="digite [bold]help[/] para ajuda completa",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console = get_console()
    console.print(LOGO, style="bold cyan", highlight=False)
    console.print(panel)


def show_process_panel(proc: ProcessInfo) -> None:
    """Painel com os dados do processo antes da confirmação do kill."""
    panel = Panel(
        Text.from_markup(
            f"[bold]Nome:[/] {proc.name}\n"
            f"[bold]PID:[/] {proc.pid}\n"
            f"[bold]Usuário:[/] {proc.username}\n"
            f"[bold]Status:[/] {proc.status}\n"
            f"[bold]CMD:[/] {proc.cmdline}"
        ),
        title="Processo alvo",
        border_style="yellow",
        box=box.ROUNDED,
    )
    get_console().print(panel)


def confirm_kill(proc: ProcessInfo) -> bool:
    """Pede confirmação antes de matar (questionary)."""
    return (
        questionary.confirm(
            f"Deseja matar o processo {proc.name} (PID {proc.pid})?",
            default=False,
        ).ask()
        is True
    )


def print_error(message: str) -> None:
    """Imprime erro em vermelho no stderr."""
    get_err_console().print(f"[bold red]Erro:[/] {message}")
