"""Configuração do structlog: JSON em pipes, texto colorido no TTY."""

from __future__ import annotations

import logging
import sys

import structlog


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
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
