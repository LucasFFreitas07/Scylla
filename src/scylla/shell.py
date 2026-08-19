"""REPL persistente estilo Hermes Agent: tela de apresentação + prompt contínuo."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import structlog
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from scylla.dockertools import (
    ARGS_COMMANDS,
    DOCKER_COMMANDS,
    run_docker,
    validate_docker_arg,
)
from scylla.errors import ScyllaError
from scylla.obsidian import create_note
from scylla.processes import get_process_info, kill_process, list_processes, sort_processes
from scylla.ui import (
    confirm_kill,
    get_console,
    print_error,
    render_search_results,
    render_table,
    show_process_panel,
    welcome_screen,
)
from scylla.websearch import build_search_note_content, search_web

COMMANDS = [
    "ps",
    "kill",
    "exec",
    "obs_create",
    "search",
    "dps",
    "dpsa",
    "di",
    "dlog",
    "dstop",
    "dstart",
    "drm",
    "drmi",
    "dcps",
    "dcup",
    "dcdown",
    "dclog",
    "dcrestart",
    "help",
    "clear",
    "exit",
    "quit",
]

PROMPT_STYLE = Style.from_dict({"prompt": "bold blue"})

# Timeout para comandos do `exec`/`!` (evita travar o REPL indefinidamente).
EXEC_TIMEOUT = 300  # segundos

HELP_TEXT = """\
[bold cyan]Scylla CLI[/] — comandos disponíveis:

  [bold]ps[/]               Lista os processos em uma tabela
  [bold]kill <PID>[/]      Mata um processo (com confirmação)

[bold cyan]Docker:[/]
  [bold]dps[/]              docker ps (containers em execução)
  [bold]dpsa[/]             docker ps -a (todos os containers)
  [bold]di[/]               docker images (imagens locais)
  [bold]dlog <ctr>[/]       docker logs <container>
  [bold]dstop <ctr>[/]      docker stop <container>
  [bold]dstart <ctr>[/]     docker start <container>
  [bold]drm <ctr>[/]        docker rm <container>
  [bold]drmi <img>[/]       docker rmi <imagem>

[bold cyan]Docker Compose:[/]
  [bold]dcps[/]             docker compose ps
  [bold]dcup[/]             docker compose up -d
  [bold]dcdown[/]           docker compose down
  [bold]dclog[/]            docker compose logs
  [bold]dcrestart[/]        docker compose restart

[bold cyan]Terminal:[/]
  [bold]exec <cmd>[/]      Roda um comando de terminal (ex.: exec ls -la)
  [bold]!<cmd>[/]          Atalho do exec (!ls -la)

[bold cyan]Obsidian:[/]
  [bold]obs_create <nome>[/]              Cria uma nota no vault
  [bold]obs_create <nome> -t tags[/]      Cria com tags (separadas por vírgula)
  [bold]obs_create <nome> -f pasta[/]     Cria numa subpasta
  [bold]obs_create <nome> -c "texto"[/]   Cria com conteúdo markdown

[bold cyan]Busca:[/]
  [bold]search <consulta>[/]              Busca na web (DuckDuckGo)
  [bold]search <consulta> -n 10[/]        Limita a 10 resultados
  [bold]search <consulta> -s[/]           Salva os resultados como nota no Obsidian
  [bold]search <consulta> -s -f pasta[/]  Salva numa subpasta do vault

  [bold]help[/]            Mostra esta ajuda
  [bold]clear[/]           Limpa a tela
  [bold]exit[/]            Sai do scylla (ou Ctrl+D)

Dicas: Tab autocompleta, ↑/↓ navega o histórico.
"""


def _history_file() -> Path:
    cache_base = os.environ.get("XDG_CACHE_HOME")
    cache_dir = Path(cache_base) if cache_base else Path.home() / ".cache"
    history_dir = cache_dir / "scylla"
    history_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(history_dir, 0o700)
    history_path = history_dir / "history"
    if not history_path.exists():
        history_path.touch(mode=0o600)
    else:
        os.chmod(history_path, 0o600)
    return history_path


def _parse_ps_limit(args: list[str]) -> int | None:
    if not args:
        return None
    if len(args) == 1 and args[0].isdigit():
        n = int(args[0])
        if n > 0:
            return n
        print_error("O limite deve ser um inteiro positivo.")
        return None
    if len(args) == 2 and args[0] == "--top":
        try:
            n = int(args[1])
        except ValueError:
            print_error(f"Limite inválido: {args[1]}")
            return None
        if n <= 0:
            print_error("O limite deve ser um inteiro positivo.")
            return None
        return n
    print_error("Uso: ps [N] ou ps --top <N>")
    return None


def _run_ps(args: list[str]) -> None:
    log = structlog.get_logger("scylla.shell.ps")
    top: int | None = None
    if args:
        top = _parse_ps_limit(args)
        if top is None:
            return
    try:
        procs = list_processes()
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("ps_falhou", erro=str(exc))
        return
    procs = sort_processes(procs)
    if top is not None:
        procs = procs[:top]
    render_table(procs, top=top)
    log.debug("ps_ok", total=len(procs), top=top)


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
        message = kill_process(pid, expected_create_time=info.create_time)
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("kill_falhou", pid=pid, erro=str(exc))
        return
    get_console().print(f"[green]{message}[/]")
    log.info("kill_ok", pid=pid)


def _run_docker(docker_args: list[str]) -> None:
    log = structlog.get_logger("scylla.shell.docker")
    code = run_docker(docker_args)
    log.debug("docker_ok", args=docker_args, exit_code=code)


def _run_exec(args: list[str]) -> None:
    log = structlog.get_logger("scylla.shell.exec")
    command = " ".join(args).strip()
    if not command:
        print_error("Uso: exec <comando>")
        return
    binario = command.split(maxsplit=1)[0]
    log.info("executando", binario=binario)
    try:
        result = subprocess.run(
            command, shell=True, check=False, timeout=EXEC_TIMEOUT
        )
    except KeyboardInterrupt:
        get_console().print("[yellow]Comando interrompido.[/]")
        log.warning("exec_interrompido", binario=binario)
        return
    except subprocess.TimeoutExpired:
        print_error(f"Comando excedeu o limite de {EXEC_TIMEOUT}s e foi abortado.")
        log.warning("exec_timeout", binario=binario)
        return
    except OSError as exc:
        print_error(f"Falha ao executar: {exc}")
        log.error("exec_falhou", erro=str(exc))
        return
    if result.returncode != 0:
        get_console().print(f"[dim]exit code: {result.returncode}[/]")
        log.warning("exec_exit_nao_zero", binario=binario, exit_code=result.returncode)
    log.debug("exec_ok", binario=binario, exit_code=result.returncode)


def _parse_obs_create_args(args: list[str]) -> dict[str, Any]:
    """Parse dos argumentos de ``obs_create`` no shell interativo.

    Formato:
        obs_create <nome> [-t tag1,tag2] [-f pasta] [-c "conteúdo"]

    O ``<nome>`` pode conter espaços (todas as palavras antes do primeiro
    flag ``-t``/``-f``/``-c`` são tratadas como parte do nome).

    Retorna dict com ``name``, ``tags``, ``folder``, ``content``.
    """
    if not args:
        print_error("Uso: obs_create <nome> [-t tags] [-f pasta] [-c \"conteúdo\"]")
        return {}

    # Separa nome (tudo antes do primeiro flag) dos flags
    name_parts: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ("-t", "--tags", "-f", "--folder", "-c", "--content"):
            rest = args[i:]
            break
        name_parts.append(args[i])
        i += 1

    if not name_parts:
        print_error("Uso: obs_create <nome> [-t tags] [-f pasta] [-c \"conteúdo\"]")
        return {}

    result: dict[str, Any] = {
        "name": " ".join(name_parts),
        "tags": None,
        "folder": None,
        "content": None,
    }

    i = 0
    while i < len(rest):
        if rest[i] in ("-t", "--tags") and i + 1 < len(rest):
            result["tags"] = [t.strip() for t in rest[i + 1].split(",")]
            i += 2
        elif rest[i] in ("-f", "--folder") and i + 1 < len(rest):
            result["folder"] = rest[i + 1]
            i += 2
        elif rest[i] in ("-c", "--content") and i + 1 < len(rest):
            result["content"] = rest[i + 1]
            i += 2
        else:
            print_error(f"Argumento desconhecido: {rest[i]}")
            return {}
    return result


def _run_obs_create(args: list[str]) -> None:
    """Cria uma nota no vault Obsidian a partir do shell interativo."""
    log = structlog.get_logger("scylla.shell.obs_create")
    parsed = _parse_obs_create_args(args)
    if not parsed:
        return

    try:
        path = create_note(
            parsed["name"],
            folder=parsed["folder"],
            tags=parsed["tags"],
            content=parsed["content"],
        )
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("obs_create_falhou", erro=str(exc))
        return

    get_console().print(f"[green]Nota criada:[/] {path}")
    log.info("obs_create_ok", nota=parsed["name"])


def _parse_search_args(args: list[str]) -> dict[str, Any]:
    """Parse dos argumentos de ``search`` no shell interativo.

    Formato:
        search <consulta> [-n N] [-s] [-f pasta] [-t tags]

    A ``<consulta>`` pode conter espaços (tudo antes do primeiro flag).

    Retorna dict com ``query``, ``limit``, ``save``, ``folder``, ``tags``.
    """
    if not args:
        print_error("Uso: search <consulta> [-n N] [-s] [-f pasta] [-t tags]")
        return {}

    query_parts: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ("-n", "--limit", "-s", "--save", "-f", "--folder", "-t", "--tags"):
            rest = args[i:]
            break
        query_parts.append(args[i])
        i += 1

    if not query_parts:
        print_error("Uso: search <consulta> [-n N] [-s] [-f pasta] [-t tags]")
        return {}

    result: dict[str, Any] = {
        "query": " ".join(query_parts),
        "limit": 5,
        "save": False,
        "folder": None,
        "tags": None,
    }

    i = 0
    while i < len(rest):
        if rest[i] in ("-n", "--limit") and i + 1 < len(rest):
            try:
                result["limit"] = int(rest[i + 1])
            except ValueError:
                print_error(f"Limite inválido: {rest[i + 1]}")
                return {}
            if result["limit"] <= 0:
                print_error("O limite deve ser um inteiro positivo.")
                return {}
            i += 2
        elif rest[i] in ("-s", "--save"):
            result["save"] = True
            i += 1
        elif rest[i] in ("-f", "--folder") and i + 1 < len(rest):
            result["folder"] = rest[i + 1]
            i += 2
        elif rest[i] in ("-t", "--tags") and i + 1 < len(rest):
            result["tags"] = [t.strip() for t in rest[i + 1].split(",")]
            i += 2
        else:
            print_error(f"Argumento desconhecido: {rest[i]}")
            return {}
    return result


def _run_search(args: list[str]) -> None:
    """Busca na web e opcionalmente salva os resultados no Obsidian."""
    log = structlog.get_logger("scylla.shell.search")
    parsed = _parse_search_args(args)
    if not parsed:
        return

    try:
        results = search_web(parsed["query"], limit=parsed["limit"])
    except ScyllaError as exc:
        print_error(str(exc))
        log.warning("search_falhou", consulta=parsed["query"], erro=str(exc))
        return

    render_search_results(parsed["query"], results)

    if parsed["save"]:
        tag_list = parsed["tags"]
        if tag_list is None:
            tag_list = ["Busca"]
        elif "Busca" not in tag_list:
            tag_list.append("Busca")
        content = build_search_note_content(parsed["query"], results)
        note_name = f"Busca - {parsed['query']}"
        try:
            path = create_note(
                note_name, folder=parsed["folder"], tags=tag_list, content=content
            )
        except ScyllaError as exc:
            print_error(str(exc))
            log.warning("search_save_falhou", consulta=parsed["query"], erro=str(exc))
            return
        get_console().print(f"[green]Nota salva:[/] {path}")
        log.info("search_save_ok", consulta=parsed["query"], nota=note_name)


def run_shell() -> None:
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
        if text.startswith("!"):
            _run_exec([text[1:].strip()])
            continue
        parts = text.split()
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("exit", "quit"):
            break
        if cmd == "ps":
            _run_ps(args)
        elif cmd == "kill":
            _run_kill(args)
        elif cmd == "exec":
            _run_exec(args)
        elif cmd == "obs_create":
            _run_obs_create(args)
        elif cmd == "search":
            _run_search(args)
        elif cmd in DOCKER_COMMANDS:
            _run_docker(DOCKER_COMMANDS[cmd])
        elif cmd in ARGS_COMMANDS:
            if len(args) != 1:
                print_error(f"Uso: {cmd} <nome>")
            else:
                erro = validate_docker_arg(args[0])
                if erro:
                    print_error(erro)
                else:
                    _run_docker([*ARGS_COMMANDS[cmd], args[0]])
        elif cmd == "help":
            get_console().print(HELP_TEXT)
        elif cmd == "clear":
            get_console().clear()
        else:
            print_error(f"Comando desconhecido: {cmd}. Digite 'help' para ver os comandos.")

    log.info("sessao_encerrada")