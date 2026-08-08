"""Testes da configuração de logging."""

from __future__ import annotations

import pytest

from scylla.logging_setup import setup_logging


def test_setup_logging_json() -> None:
    setup_logging(json_logs=True)  # não deve levantar


def test_setup_logging_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStderr:
        def isatty(self) -> bool:
            return True

        def write(self, s: str) -> None:
            pass

        def flush(self) -> None:
            pass

    monkeypatch.setattr("scylla.logging_setup.sys.stderr", FakeStderr())
    setup_logging()  # ramo ConsoleRenderer (TTY) — não deve levantar
