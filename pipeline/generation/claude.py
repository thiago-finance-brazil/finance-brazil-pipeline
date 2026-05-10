"""Cliente Anthropic — gera matérias estilo Finance Brazil via Claude Sonnet."""
from __future__ import annotations


def generate_article(source_data: dict) -> dict:
    """Chama Claude com prompt editorial e retorna article dict pronto pra DB.

    TODO: implementar.

    Args:
        source_data: dict com {title, summary, url, source, secondary_sources, ...}
            vindo da camada de busca + corroboração.

    Returns:
        Dict com {title, subtitle, excerpt, content, tags, source_quote, ...}.
    """
    raise NotImplementedError
