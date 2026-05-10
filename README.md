# Finance Brazil — Pipeline Editorial

Pipeline Python que descobre notícias econômicas em fontes confiáveis, gera matérias estilo Finance Brazil via Claude e salva no Supabase com `status='pending'` para revisão humana antes da publicação.

**Status:** 🚧 Em desenvolvimento — Dia 1 (estrutura inicial).

## Arquitetura

```
fontes confiáveis (Perplexity Sonar)
        │
        ▼
  corroboração + whitelist
        │
        ▼
   geração (Claude Sonnet)
        │
        ▼
  pós-processamento + validação
        │
        ▼
   Supabase (status='pending')
        │
        ▼
   revisão humana → status='published'
```

## Pré-requisitos

- **Python 3.12+** — instale via Homebrew: `brew install python@3.12`
- **uv** — package manager Python: `brew install uv`

## Setup local

```bash
# 1. Clone o repo (se ainda não fez)
git clone https://github.com/thiago-finance-brazil/finance-brazil-pipeline.git
cd finance-brazil-pipeline

# 2. Cria venv com Python 3.12 + instala deps
uv venv --python 3.12
uv sync

# 3. Configura variáveis de ambiente
cp .env.example .env
# edite .env e preencha as 4 chaves: ANTHROPIC_API_KEY, PERPLEXITY_API_KEY,
# SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
```

## Comandos

### Testes de conectividade (Dia 1)

Roda cada API isoladamente para validar credenciais e conexão:

```bash
uv run python scripts/test_anthropic.py     # Claude Haiku 4.5
uv run python scripts/test_perplexity.py    # Sonar
uv run python scripts/test_supabase.py      # SELECT 1 article
```

### Pipeline completo

```bash
# Modo dry-run (default — não persiste no banco)
DRY_RUN=true uv run python -m pipeline.main

# Modo escrita (persiste com status='pending')
DRY_RUN=false uv run python -m pipeline.main
```

## Estrutura

```
finance-brazil-pipeline/
├── pyproject.toml           # deps (uv)
├── .env.example             # template de configuração
├── Procfile                 # entry point Railway
├── railway.toml             # config Railway (cron a definir)
│
├── pipeline/
│   ├── main.py              # entry point: 1 ciclo completo
│   ├── config.py            # Settings (Pydantic) + setup loguru
│   ├── sources/             # descoberta (Perplexity, whitelist, corroboração)
│   ├── generation/          # geração via Claude (cliente, prompts, postproc)
│   ├── validation/          # confidence_score, warnings, filtros
│   ├── storage/             # Supabase (artigos) + logger (pipeline_runs)
│   └── utils/               # slugify, cost tracker
│
├── scripts/                 # testes manuais de conectividade
└── tests/                   # pytest (a popular)
```

## Deploy (Railway)

Push pra `main` dispara redeploy. O cron schedule fica em `railway.toml` — ainda comentado até o pipeline estar validado manualmente.

## Decisões de design

- **Pydantic v2** para validação de boundaries (env vars, payloads de API, rows do banco). TypedDict pra estruturas internas se virar útil.
- **Loguru** ao invés de stdlib `logging` — formato amigável out-of-the-box, configuração simples.
- **httpx** ao invés de requests — async-ready, melhor erro reporting, padrão moderno.
- **uv** ao invés de pip/poetry — mais rápido (Rust), gerencia Python + venv + deps numa ferramenta só.
- **SERVICE_ROLE_KEY** no Supabase (bypassa RLS) — pipeline backend escreve direto, sem auth de usuário.
