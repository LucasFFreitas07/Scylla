# Scylla CLI

Ferramenta de linha de comando para **visualizar e matar processos** no Linux, com
sessão interativa persistente (estilo Hermes Agent) e comandos one-shot.

## Instalação

Requer Python >= 3.11 e [uv](https://docs.astral.sh/uv/) (ou pipx).

```bash
uv tool install .
# ou: pipx install .
```

## Uso

### Modo interativo (persistente)

```bash
scylla
```

Abre uma tela de apresentação (logo, versão e dicas) e um prompt contínuo:

```
scylla> ps
scylla> kill 1234
scylla> help
scylla> exit
```

Comandos do shell: `ps`, `kill <PID>`, `help`, `clear`, `exit`. Tab autocompleta,
↑/↓ navega o histórico (salvo em `~/.cache/scylla/history`), `Ctrl+D` encerra.

### Modo one-shot

```bash
scylla ps                    # lista processos em tabela
scylla kill <PID>            # mata um processo (com confirmação)
scylla kill <PID> --yes      # sem confirmação (scripts)
scylla kill <PID> --force    # SIGKILL direto, sem SIGTERM
scylla --version             # mostra a versão
```

### Opções globais

| Opção | Descrição |
|---|---|
| `--version`, `-V` | Mostra a versão e sai |
| `--json-logs` | Logs estruturados em JSON (útil em pipes/CI) |
| `--no-color` | Desativa cores (também respeita `NO_COLOR` e `TERM=dumb`) |

## Comportamento do kill

1. Exibe um painel com os dados do processo (nome, PID, usuário, status, CMD).
2. Pede confirmação (questionary) — recusar cancela sem matar nada.
3. Envia **SIGTERM** e aguarda até 3s; se o processo continuar vivo, aplica **SIGKILL**.
4. `--force` envia SIGKILL direto.

O scylla nunca mata o próprio processo. Sem permissão (processo de outro usuário),
retorna erro claro com exit code 2.

## Exit codes

| Código | Significado |
|---|---|
| 0 | Sucesso (ou operação cancelada pelo usuário) |
| 1 | Erro de uso (PID inválido, etc.) |
| 2 | Erro de runtime (processo inexistente, permissão negada) |

## Desenvolvimento

```bash
uv sync                    # instala o ambiente
uv run scylla              # roda a partir do fonte
uv run pytest --cov=scylla # testes com cobertura
uv run ruff check .        # lint
uv run mypy src/           # checagem de tipos
```

## Estrutura

```
src/scylla/
├── cli.py            # app Typer: ps, kill, opções globais
├── shell.py          # REPL persistente (prompt_toolkit)
├── processes.py      # listagem/kill via psutil
├── ui.py             # rich: tabela, tela de apresentação, confirmação
├── logging_setup.py  # structlog (JSON em pipes, colorido no TTY)
└── errors.py         # exceções customizadas + exit codes
```

## Roadmap (próximas versões)

- Filtros: `scylla ps --name <substring>`, `--pid`, `--user`
- Exportação: `scylla ps --export <arquivo.csv|json>`
- Watch mode, matar por nome/porta, árvore de processos
