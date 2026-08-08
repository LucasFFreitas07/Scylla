"""Exceções customizadas e códigos de saída padronizados."""

from __future__ import annotations

# Códigos de saída
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUNTIME = 2


class ScyllaError(Exception):
    """Erro base da ferramenta, com mensagem amigável e código de saída."""

    exit_code = EXIT_RUNTIME

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class InvalidPidError(ScyllaError):
    """PID inválido (não é um inteiro positivo)."""

    exit_code = EXIT_USAGE


class ProcessNotFoundError(ScyllaError):
    """Processo não existe (ou já foi encerrado)."""


class PermissionDeniedError(ScyllaError):
    """Sem permissão para agir sobre o processo."""
