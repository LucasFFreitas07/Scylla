"""Renderização rich: tabela de processos, tela de apresentação e confirmação."""

from __future__ import annotations

import questionary
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from scylla import __version__
from scylla.processes import ProcessInfo
from scylla.websearch import SearchResult


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


def render_table(procs: list[ProcessInfo], *, top: int | None = None) -> None:
    """Renderiza a tabela de processos.

    Campos vindos do sistema (nome, usuário, cmdline) são escapados com
    ``rich.markup.escape`` para impedir injeção de markup/ANSI por um processo
    malicioso (spoofing de UI ou crash por MarkupError).
    """
    title = f"Processos — {len(procs)}"
    if top is not None:
        title += f" (top {top})"
    table = Table(title=title, box=box.ROUNDED, expand=False)
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
            escape(p.name),
            escape(p.username),
            f"{p.cpu_percent:.1f}",
            f"{p.memory_percent:.1f}",
            Text(p.status, style=STATUS_COLORS.get(p.status, "white")),
            escape(p.cmdline),
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


DARK_BLUE = "#003B73"


def welcome_screen() -> None:
    """Tela de apresentação estilo Hermes Agent."""
    info = Text.from_markup(
        f"[bold {DARK_BLUE}]Gerenciador de processos e Docker para Linux[/]\n\n"
        "[yellow]Comandos:[/] [bold]ps[/] | [bold]kill <PID>[/] | [bold]dps[/] "
        "| [bold]help[/] | [bold]exit[/]\n"
        "[dim]Dica: d* = docker (dps, dlog...), dc* = compose (dcup, dcdown...). "
        "Tab autocompleta, ↑/↓, Ctrl+D encerra.[/]"
    )
    panel = Panel(
        info,
        title=f"[bold {DARK_BLUE}]Scylla CLI[/]  [dim]v{__version__}[/]",
        subtitle=f"digite [bold {DARK_BLUE}]help[/] para ajuda completa",
        border_style=DARK_BLUE,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console = get_console()
    console.print(LOGO, style=f"bold {DARK_BLUE}", highlight=False)
    console.print(panel)


def show_process_panel(proc: ProcessInfo) -> None:
    """Painel com os dados do processo antes da confirmação do kill.

    Campos vindos do sistema (nome, usuário, status, cmdline) são escapados
    com ``rich.markup.escape`` para impedir injeção de markup/ANSI por um
    processo malicioso (spoofing de UI ou crash por MarkupError).
    """
    panel = Panel(
        Text.from_markup(
            f"[bold]Nome:[/] {escape(proc.name)}\n"
            f"[bold]PID:[/] {proc.pid}\n"
            f"[bold]Usuário:[/] {escape(proc.username)}\n"
            f"[bold]Status:[/] {escape(proc.status)}\n"
            f"[bold]CMD:[/] {escape(proc.cmdline)}"
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


def render_search_results(query: str, results: list[SearchResult]) -> None:
    """Renderiza os resultados de busca no terminal (lista numerada).

    Título, URL e snippet vêm da web (conteúdo de terceiros) — são escapados
    com ``rich.markup.escape`` para impedir injeção de markup/ANSI (spoofing
    de UI ou crash por MarkupError).
    """
    console = get_console()
    console.print(f"[bold cyan]Busca:[/] {escape(query)} [dim]({len(results)} resultados)[/]")
    console.print()
    for i, r in enumerate(results, start=1):
        console.print(f"[bold]{i}.[/] {escape(r.title)}")
        console.print(f"  [dim]{escape(r.url)}[/]")
        if r.snippet:
            console.print(f"  {escape(r.snippet)}")
        console.print()
    if not results:
        console.print("[yellow]Nenhum resultado encontrado.[/]")