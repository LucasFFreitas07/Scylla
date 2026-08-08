"""Testes dos comandos docker no Typer (one-shot)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from scylla.cli import app

runner = CliRunner()


def test_help_lista_docker() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("dps", "dpsa", "di", "dlog", "dstop", "dstart", "drm", "drmi",
                "dcps", "dcup", "dcdown", "dclog", "dcrestart"):
        assert cmd in result.output


@pytest.mark.parametrize(
    ("args", "esperado"),
    [
        (["dps"], ["ps"]),
        (["dpsa"], ["ps", "-a"]),
        (["di"], ["images"]),
        (["dcps"], ["compose", "ps"]),
        (["dcup"], ["compose", "up", "-d"]),
        (["dcdown"], ["compose", "down"]),
        (["dclog"], ["compose", "logs"]),
        (["dcrestart"], ["compose", "restart"]),
    ],
)
def test_comandos_sem_argumento(
    monkeypatch: pytest.MonkeyPatch, args: list[str], esperado: list[str]
) -> None:
    chamadas: list[list[str]] = []
    monkeypatch.setattr(
        "scylla.cli.run_docker", lambda a: (chamadas.append(a), 0)[1]
    )

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert chamadas == [esperado]


@pytest.mark.parametrize(
    ("args", "esperado"),
    [
        (["dlog", "nginx"], ["logs", "nginx"]),
        (["dstop", "web"], ["stop", "web"]),
        (["dstart", "web"], ["start", "web"]),
        (["drm", "web"], ["rm", "web"]),
        (["drmi", "alpine"], ["rmi", "alpine"]),
    ],
)
def test_comandos_com_argumento(
    monkeypatch: pytest.MonkeyPatch, args: list[str], esperado: list[str]
) -> None:
    chamadas: list[list[str]] = []
    monkeypatch.setattr(
        "scylla.cli.run_docker", lambda a: (chamadas.append(a), 0)[1]
    )

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert chamadas == [esperado]


def test_propaga_exit_code_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scylla.cli.run_docker", lambda a: 125)

    result = runner.invoke(app, ["dps"])

    assert result.exit_code == 125


def test_comando_requer_argumento() -> None:
    result = runner.invoke(app, ["dlog"])
    assert result.exit_code == 2  # erro de uso do typer (argumento ausente)
