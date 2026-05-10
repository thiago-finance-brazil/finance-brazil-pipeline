"""Pós-processamento: enriquecimentos finais antes do `articles` (Supabase).

Recebe `GeneratedArticle` validado + contexto da fonte primária e produz
um dict pronto pra insert. Calcula slug (utils.slugify), reading_time
e mescla campos da fonte original (URL + nome).
"""
from __future__ import annotations

from typing import Any

from pipeline.generation.models import GeneratedArticle
from pipeline.sources.models import NewsItem
from pipeline.utils.slugify import slugify

WORDS_PER_MINUTE = 200


def reading_time_minutes(content: str) -> int:
    """Tempo de leitura em minutos a partir do markdown (200 wpm). Mínimo 1."""
    words = len(content.split())
    return max(1, round(words / WORDS_PER_MINUTE))


def postprocess_article(
    article: GeneratedArticle, primary: NewsItem
) -> dict[str, Any]:
    """Enriquece o GeneratedArticle com slug, reading_time e metadata da fonte.

    Args:
        article: validado pelo Pydantic na geração.
        primary: NewsItem que originou a matéria (vai pro source_url/source_name).

    Returns:
        Dict pronto pra `INSERT INTO articles (...)` no Supabase. Não inclui
        `id`, `status`, `published_at`, `created_at`, `view_count` — esses
        ficam a cargo da camada de storage / banco.
    """
    payload = article.model_dump()
    payload["slug"] = slugify(article.title)
    payload["reading_time_minutes"] = reading_time_minutes(article.content)
    payload["source_url"] = primary.url
    payload["source_name"] = primary.source_name
    return payload
