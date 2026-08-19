"""Integração com o Obsidian — criação de notas no vault."""

from __future__ import annotations

import os
import re
from pathlib import Path

import structlog

from scylla.errors import ScyllaError

# Caminho do vault — configuração via variável de ambiente ou padrão.
_VAULT_ENV = "SCYLLA_OBSIDIAN_VAULT"
_DEFAULT_VAULT = Path.home() / "Desktop" / "Obsidian"


def get_vault_path() -> Path:
    """Retorna o caminho absoluto do vault Obsidian.

    Resolução:
    1. ``SCYLLA_OBSIDIAN_VAULT`` (variável de ambiente)
    2. ``~/Desktop/Obsidian`` (padrão do usuário)
    """
    custom = os.environ.get(_VAULT_ENV)
    if custom:
        return Path(custom).expanduser().resolve()
    return _DEFAULT_VAULT.resolve()


def sanitize_name(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo no Obsidian.

    Preserva letras, números, espaços, hífens, underscores e pontos.
    """
    # Remove caracteres problemáticos no Windows/Linux
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    # Substitui múltiplos espaços/underscores por um único
    cleaned = re.sub(r"[\s_]+", " ", cleaned).strip()
    if not cleaned:
        raise ScyllaError("Nome da nota ficou vazio após sanitização.")
    return cleaned


def validate_folder(folder: str) -> str:
    """Valida uma subpasta do vault contra path traversal.

    Rejeita caminhos absolutos e segmentos ``..`` (que escapariam do vault).
    Retorna a pasta normalizada (sem barras no início/fim).
    """
    if not folder:
        raise ScyllaError("Pasta vazia.")
    folder = folder.replace("\\", "/").strip("/")
    if Path(folder).is_absolute():
        raise ScyllaError(f"Pasta não pode ser um caminho absoluto: {folder}")
    if ".." in folder.split("/"):
        raise ScyllaError(f"Pasta não pode conter '..' (path traversal): {folder}")
    return folder


def _sanitize_tag(tag: str) -> str:
    """Sanitiza uma tag para o frontmatter YAML.

    Remove quebras de linha e caracteres de controle (impede injeção YAML,
    ex.: uma tag ``ok\\nmalicious: true`` viraria uma chave extra).
    """
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", tag).strip()
    if not cleaned:
        raise ScyllaError("Tag ficou vazia após sanitização.")
    return cleaned


def build_frontmatter(tags: list[str] | None = None, **extra: str) -> str:
    """Gera o bloco YAML frontmatter para uma nota.

    Exemplo::

        ---
        tags:
          - DevOps
          - Docker
        ---
    """
    lines = ["---"]
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {_sanitize_tag(tag)}")
    for key, value in extra.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def create_note(
    name: str,
    *,
    folder: str | None = None,
    tags: list[str] | None = None,
    content: str | None = None,
) -> Path:
    """Cria uma nota no vault Obsidian.

    Retorna o caminho absoluto do arquivo criado.

    Parâmetros
    ----------
    name:
        Nome/título da nota (será sanitizado).
    folder:
        Subpasta dentro do vault (será criada se não existir).
    tags:
        Lista de tags para o frontmatter YAML.
    content:
        Corpo da nota (markdown). Se ``None``, cria nota só com frontmatter.
    """
    log = structlog.get_logger("scylla.obsidian")
    vault = get_vault_path()

    if not vault.exists():
        raise ScyllaError(f"Vault Obsidian não encontrado: {vault}")

    clean_name = sanitize_name(name)

    # Monta o caminho completo (folder validado contra path traversal)
    if folder:
        clean_folder = validate_folder(folder)
        note_dir = vault / clean_folder
    else:
        note_dir = vault

    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / f"{clean_name}.md"

    # Defesa em profundidade: garante que o arquivo final está dentro do vault
    try:
        dentro = note_path.resolve().is_relative_to(vault.resolve())
    except ValueError:
        dentro = False
    if not dentro:
        raise ScyllaError(
            f"Pasta escapa do vault: {folder}. Operação abortada."
        )

    if note_path.exists():
        raise ScyllaError(
            f"Nota já existe: {note_path.relative_to(vault)}. "
            "Use outro nome ou exclua a nota existente."
        )

    # Constrói o conteúdo
    parts: list[str] = []

    # Frontmatter
    fm = build_frontmatter(tags)
    parts.append(fm)

    # Título H1
    parts.append(f"\n# {clean_name}\n")

    # Corpo (se fornecido)
    if content:
        parts.append(f"{content}\n")

    note_content = "\n".join(parts)
    note_path.write_text(note_content, encoding="utf-8")

    log.info(
        "nota_criada",
        nota=clean_name,
        pasta=folder or "(raiz)",
        tags=tags or [],
        caminho=str(note_path),
    )
    return note_path