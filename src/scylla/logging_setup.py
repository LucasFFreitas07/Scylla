"""Configuração do structlog: JSON em pipes, texto colorido no TTY."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


class _CurrentStderrLogger(structlog.PrintLogger):
    """PrintLogger que sempre escreve no ``sys.stderr`` atual.

    Resolver o stderr no momento da escrita (em vez de capturá-lo na criação)
    evita escrever em arquivos fechados depois de isolamentos de teste/CLI.
    """

    def msg(self, message: str) -> None:
        with self._lock:
            print(message, file=sys.stderr, flush=True)


class _CurrentStderrFactory:
    """LoggerFactory do structlog que usa o stderr atual a cada escrita."""

    def __call__(self, *args: Any, **kwargs: Any) -> structlog.PrintLogger:
        return _CurrentStderrLogger()


def setup_logging(*, json_logs: bool = False) -> None:
    """Configura o structlog.

    Logs vão para **stderr** (stdout fica reservado para dados/tabela).
    JSON quando ``--json-logs`` ou quando stderr não é um TTY (pipes/CI).
    """
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if json_logs or not sys.stderr.isatty():
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=_CurrentStderrFactory(),
        cache_logger_on_first_use=True,
    )
