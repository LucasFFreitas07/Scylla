"""Busca na web via DuckDuckGo HTML (sem chave de API) + nota Obsidian."""

from __future__ import annotations

import html as html_mod
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import URLError

import structlog

from scylla.errors import ScyllaError

SEARCH_URL = "https://html.duckduckgo.com/html/"
TIMEOUT = 15  # segundos
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_TITLE_RE = re.compile(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
_URL_PARAM_RE = re.compile(r"uddg=([^&\"']+)")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class SearchResult:
    """Um resultado de busca: título, URL e descrição."""

    title: str
    url: str
    snippet: str


def _clean_html(text: str) -> str:
    """Remove tags HTML e decodifica entidades."""
    text = _TAG_RE.sub("", text)
    return html_mod.unescape(text).strip()


def _extract_url(href: str) -> str:
    """Extrai a URL real do redirect do DuckDuckGo (parâmetro ``uddg``)."""
    m = _URL_PARAM_RE.search(href)
    if m:
        return urllib.parse.unquote(m.group(1))
    return href


def search_web(query: str, *, limit: int = 5) -> list[SearchResult]:
    """Busca na web via DuckDuckGo HTML.

    Retorna até ``limit`` resultados (título, URL, snippet). Sem chave de API.
    """
    log = structlog.get_logger("scylla.websearch")
    if not query.strip():
        raise ScyllaError("Consulta de busca vazia.")
    if limit <= 0:
        raise ScyllaError("limit deve ser um inteiro positivo.")

    params = urllib.parse.urlencode({"q": query.strip()})
    url = f"{SEARCH_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except URLError as exc:
        raise ScyllaError(f"Falha na busca: {exc.reason}") from exc
    except TimeoutError:
        raise ScyllaError(f"Busca excedeu o limite de {TIMEOUT}s.") from None

    page = raw.decode("utf-8", errors="replace")
    titles = _TITLE_RE.findall(page)
    snippets = _SNIPPET_RE.findall(page)

    results: list[SearchResult] = []
    for i, (href, title) in enumerate(titles[:limit]):
        snippet = _clean_html(snippets[i]) if i < len(snippets) else ""
        results.append(
            SearchResult(
                title=_clean_html(title),
                url=_extract_url(href),
                snippet=snippet,
            )
        )
    log.info("busca_ok", consulta=query, resultados=len(results))
    return results


def _escape_markdown_link_text(text: str) -> str:
    """Escapa ``[`` e ``]`` no texto de um link markdown.

    Impede que um título vindo da web quebre o link (ex.: ``Evil](https://x)``).
    """
    return text.replace("[", "\\[").replace("]", "\\]")


def _escape_markdown_url(url: str) -> str:
    """Escapa ``(`` e ``)`` na URL de um link markdown.

    Impede que uma URL vinda da web quebre o link (ex.: ``https://x)``).
    """
    return url.replace("(", "%28").replace(")", "%29")


def build_search_note_content(query: str, results: list[SearchResult]) -> str:
    """Gera o markdown da nota Obsidian com os resultados da busca."""
    now = datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")
    lines = [
        f"> Resultados de busca para **\"{query}\"** — {now}.",
        "",
        "## Resultados",
        "",
    ]
    for i, r in enumerate(results, start=1):
        title = _escape_markdown_link_text(r.title)
        url = _escape_markdown_url(r.url)
        lines.append(f"{i}. [{title}]({url})")
        if r.snippet:
            lines.append(f"   {r.snippet}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> Fonte: DuckDuckGo (busca automática via Scylla CLI).")
    return "\n".join(lines)