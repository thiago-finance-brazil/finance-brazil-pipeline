"""Orchestrator da camada de validação — combina confidence + warnings + filtros.

Decision logic:
    publish  → confidence >= 0.75 AND len(warnings) <= 1
    flag     → confidence >= 0.50 AND not should_reject (mas não é publish)
    reject   → should_reject == True OR confidence < 0.50

Storage:
    publish/flag → status='review' (humano revisa)
    reject       → status='rejected' (não exposto publicamente)

Esta camada apenas DECIDE. A persistência é responsabilidade da próxima fase.
"""
from __future__ import annotations

from loguru import logger

from pipeline.generation.models import GeneratedArticle
from pipeline.sources.models import CorroboratedItem
from pipeline.utils.slugify import slugify
from pipeline.validation.confidence import compute_confidence
from pipeline.validation.filters import should_reject
from pipeline.validation.models import ValidationResult
from pipeline.validation.warnings import detect_warnings

PUBLISH_CONFIDENCE = 0.75
FLAG_CONFIDENCE = 0.50
PUBLISH_MAX_WARNINGS = 1


def validate(item: CorroboratedItem, article: GeneratedArticle) -> ValidationResult:
    """Executa as 3 fases (confidence + warnings + filters) e devolve ValidationResult.

    Args:
        item: CorroboratedItem da Fase 2 (busca + corroboração).
        article: GeneratedArticle da Fase 3 (geração via Claude).

    Returns:
        ValidationResult com decision/confidence/warnings/rejection_reason.
    """
    confidence = compute_confidence(item)
    warnings = detect_warnings(item, article, confidence)

    slug = slugify(article.title)
    rejected, reason = should_reject(item, article, confidence, slug)

    if rejected:
        decision = "reject"
    elif confidence >= PUBLISH_CONFIDENCE and len(warnings) <= PUBLISH_MAX_WARNINGS:
        decision = "publish"
    else:
        decision = "flag"

    logger.info(
        f"validate: decision={decision} confidence={confidence:.3f} "
        f"warnings={len(warnings)} rejected={rejected}"
    )

    return ValidationResult(
        decision=decision,
        confidence_score=round(confidence, 4),
        warnings=warnings,
        rejection_reason=reason,
    )
