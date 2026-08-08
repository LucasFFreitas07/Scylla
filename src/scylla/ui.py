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


def render_table(procs: list[ProcessInfo], *, top: int | None = None) -> None:
    """Renderiza a tabela de processos."""
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
            p.name,
            p.username,
            f"{p.cpu_percent:.1f}",
            f"{p.memory_percent:.1f}",
            Text(p.status, style=STATUS_COLORS.get(p.status, "white")),
            p.cmdline,
        )
    get_console().print(table)


LOGO = r"""
Xx$XxXX$X++xx++&&x+;xXXX&X+X&XXx++&+&:+$
;&;x&xxxx&&&&&x+&&&X;&xx&+x&$xXx+xxXx&xx
Xx+&&&xX+&xx&x;;+x&x&+&+&xxx&&&xX$&&xxx+
&+&xxxx&&x&+.:;+;;;+x+::;;x&xxxXxx+x&xxx
xx&++;;;++x;;;:&+;;;;:;;;;;:;;;+&x&xX&Xx
XXX:;+::+:x+;&+;x$x;+;;;;+:;+xx+. +XXXXX
$xX;.&+;.:;;; :.;;;;.::;&x+:.+xX:;:XX$$$
$xXx: .+;;+;. +;:.;:.;.;:;&+ &;x+;+X$XxX
&+xx&x&.;+;;::;:::;:;x.+;:+;+.+&x+&&XXXX
+&&&&&++&+;:;&.+&&:+:&;xX+:+++&&+;+x&&XX
;x&+&&x+;::;++;+;;:+;+;;xx+:;;;:+&xx+xXX
:;::::.;+++;;.:..:+;::+;x&&+:;;++;&$xXxx
 +;;;;;:+;;:::;;++;;;;;+:;+;;:;&+x&&xxxx
+:..+:+;.:+:;+::+;.;;:;;+::::&;+:;:.++::
+.:; .:+;+.;& :;;;;+.+++;;;:++:+;+;;:+.;
++;++  :+:;+&+;x++ +;;:;:;::&;++.;&::;+;
&;;:++:.:++x;+&+&+:.:;;&+;&+;+&;: ;+++;+
x&+::+x;..::+:;;...&+:;&xxx++&+++;.;;+++
+;&+:.:&&&x;. :;+&&&x;;;+:.:.;;;:; &&;;;
.:+++.:.   ;+++;;;;.+:;+;:;;;+&++ .;+&;+
;+;++;;&x;:;+;&;+++&&:+;x+;++&&;+:;+.;&&
+++;+;++++;;.++&++&;:;.;::++;.;:+++++++;
+::&;&+:  ;+:+&&&;.;:.:;+;+:;&+::+  ....
&;&;+;:;;;:+&x&+;&:::+&;+:;x;::.:::;+;&&
&;++:++&;;&+;+;++:;+:;;:&&++:. ::.+x;x+;
:;;;++;:;;++;;;;;;;;;++;+;::.:;++++;+;;:
"""


DARK_BLUE = "#003B73"


def welcome_screen() -> None:
    """Tela de apresentação estilo Hermes Agent (comandos ao lado da arte)."""
    right_col: list[str] = [
        f"[bold {DARK_BLUE}]Gerenciador de processos[/]",
        f"[bold {DARK_BLUE}]e Docker para Linux[/]",
        "",
        "[yellow]Comandos:[/] ps | kill <PID>",
        "| dps | help | exit",
        "",
        "[dim]Dica: d* = docker, dc* = compose[/]",
        "[dim]Tab autocompleta, ↑/↓, Ctrl+D[/]",
    ]
    art_lines = LOGO.strip("\n").split("\n")
    art_width = max(len(line) for line in art_lines)
    info_start = max(0, (len(art_lines) - len(right_col)) // 2)

    content = Text()
    for i, art_line in enumerate(art_lines):
        row = Text(art_line.ljust(art_width), style=f"bold {DARK_BLUE}")
        row.append("  ")
        idx = i - info_start
        if 0 <= idx < len(right_col) and right_col[idx]:
            row.append(Text.from_markup(right_col[idx]))
        content.append(row)
        if i < len(art_lines) - 1:
            content.append("\n")

    panel = Panel(
        content,
        title=f"[bold {DARK_BLUE}]Scylla CLI[/]  [dim]v{__version__}[/]",
        subtitle=f"digite [bold {DARK_BLUE}]help[/] para ajuda completa",
        border_style=DARK_BLUE,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    get_console().print(panel)


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
