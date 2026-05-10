"""Cliente Perplexity Sonar — descobre notícias recentes em fontes confiáveis.

Wrapper sobre a API OpenAI-compatible da Perplexity (chat/completions),
com extração das `citations` retornadas pelo modelo Sonar.
"""
from __future__ import annotations


def search_news(query: str) -> list[dict]:
    """Busca notícias via Perplexity Sonar.

    TODO: implementar.

    Args:
        query: pergunta em linguagem natural (ex.: "principais notícias do
            mercado financeiro brasileiro nas últimas 24h").

    Returns:
        Lista de dicts com {title, url, summary, source, published_at}.
    """
    raise NotImplementedError
