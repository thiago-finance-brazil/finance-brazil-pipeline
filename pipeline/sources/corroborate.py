"""Corroboração: cruza notícias de fontes diferentes pra detectar fact pattern consistente.

Reduz falso positivo (single-source bias) — só promove pra geração os fatos
que aparecem em N+ fontes independentes.
"""
from __future__ import annotations


def corroborate(items: list[dict], min_sources: int = 2) -> list[dict]:
    """Filtra e enriquece itens corroborados em múltiplas fontes.

    TODO: implementar agrupamento semântico (similaridade de título/keyword).

    Args:
        items: lista bruta de notícias retornada por search_news.
        min_sources: número mínimo de fontes diferentes para considerar
            corroborado (default 2).

    Returns:
        Lista filtrada com campo extra `secondary_sources: list[str]`.
    """
    raise NotImplementedError
