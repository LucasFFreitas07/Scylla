"""Testes da integração com o Docker CLI (subprocess mockado)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from scylla import dockertools
from scylla.dockertools import docker_available, run_docker


class FakeResult:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


def test_docker_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker")
    assert docker_available() is True


def test_docker_indisponivel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert docker_available() is False


def test_run_docker_monta_comando(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker")

    def fake_run(cmd: list[str], **kwargs: object) -> FakeResult:
        chamadas.append(cmd)
        return FakeResult(0)

    monkeypatch.setattr(dockertools.subprocess, "run", fake_run)

    assert run_docker(["ps", "-a"]) == 0
    assert chamadas == [["docker", "ps", "-a"]]


def test_run_docker_propaga_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        dockertools.subprocess, "run", lambda cmd, **kwargs: FakeResult(125)
    )

    assert run_docker(["ps"]) == 125


def test_run_docker_ausente(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    code = run_docker(["ps"])

    assert code == 1
    assert "Docker não encontrado" in capsys.readouterr().err


def test_run_docker_oserror(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker")

    def falha(cmd: list[str], **kwargs: object) -> FakeResult:
        raise OSError("boom")

    monkeypatch.setattr(dockertools.subprocess, "run", falha)

    assert run_docker(["ps"]) == 1
    assert "Falha ao executar docker" in capsys.readouterr().err


def test_run_docker_timeout(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker")

    def demora(cmd: list[str], **kwargs: object) -> FakeResult:
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr(dockertools.subprocess, "run", demora)

    assert run_docker(["ps"]) == 1
    assert "demorou demais" in capsys.readouterr().err
