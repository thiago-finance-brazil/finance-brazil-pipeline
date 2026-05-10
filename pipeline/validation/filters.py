"""Filtros hard — rejeitam a matéria, que vai pro banco com `status='rejected'`.

Cinco filtros conforme spec. Apenas `duplicate_slug` e
`extremely_low_confidence` fazem checks reais (banco / score). Os outros
3 (`off_topic`, `no_sources`, `missing_critical_field`) são DEFENSIVE
CODING: as condições já foram validadas em camadas anteriores
(Pydantic Literal/Field na geração, search_news com min_weight). Mantidos
pra blindar contra mudanças de schema futuras.
"""
from __future__ import annotations

from pipeline.generation.models import GeneratedArticle
from pipeline.sources.models import CorroboratedItem
from pipeline.storage.supabase import check_duplicate_slug

EXTREMELY_LOW_CONFIDENCE = 0.50
MIN_PRIMARY_WEIGHT = 0.65


def should_reject(
    item: CorroboratedItem,
    article: GeneratedArticle,
    confidence_score: float,
    slug: str,
) -> tuple[bool, str | None]:
    """Aplica filtros hard. Retorna (rejeitado, motivo).

    Args:
        item: CorroboratedItem da Fase 2.
        article: GeneratedArticle da Fase 3.
        confidence_score: float 0.0-1.0 calculado em compute_confidence.
        slug: slug derivado do título (pra check de duplicata).

    Returns:
        (True, motivo) se rejeitado; (False, None) caso contrário.
    """
    # 1. duplicate_slug — único filtro com I/O ao banco
    if check_duplicate_slug(slug):
        return True, "duplicate_slug"

    # 2. extremely_low_confidence — único filtro real baseado no score
    if confidence_score < EXTREMELY_LOW_CONFIDENCE:
        return True, "extremely_low_confidence"

    # 3. off_topic — defensive: previously validated por Pydantic Literal
    if not article.category_slug:
        return True, "off_topic"

    # 4. no_sources — defensive: previously validated em search_news (min_weight)
    if item.primary.source_weight < MIN_PRIMARY_WEIGHT:
        return True, "no_sources"

    # 5. missing_critical_field — defensive: previously validated por Pydantic Field(...)
    if not (article.title and article.content and article.excerpt):
        return True, "missing_critical_field"

    return False, None
