"""Detecta warnings (não-bloqueantes — vão pro campo `validation_warnings`).

Cada string identifica um motivo de revisão humana sem rejeitar a matéria.
Lista alinhada com a spec do Dia 4:

    single_source         — sem corroboração (secondary_sources vazio)
    low_confidence        — confidence_score < 0.75
    old_news              — published_at > 72h (None = neutro, não dispara)
    missing_quote         — source_quote vazio ou < 30 chars
    tier_4_only           — primary tier 4 E todas secondary tier 4
    subjective_language   — content contém palavras subjetivas (lista
                            conservadora; word boundaries; multi-token)
    missing_numbers       — content sem qualquer número (suspeito pra
                            matéria econômica)
    very_short_content    — content < 400 palavras
    very_long_content     — content > 700 palavras
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from pipeline.generation.models import GeneratedArticle
from pipeline.sources.models import CorroboratedItem

# Tokens com sinal subjetivo forte. Lista conservadora — "certamente",
# "com certeza" foram excluídos por falso positivo alto em texto neutro.
# Inclui variações de gênero/número porque \b...\b não pega flexões em PT-BR.
SUBJECTIVE_WORDS: tuple[str, ...] = (
    "alegadamente",
    "supostamente",
    "polêmico", "polêmica", "polêmicos", "polêmicas",
    "escândalo", "escândalos",
    "vergonhoso", "vergonhosa", "vergonhosos", "vergonhosas",
    "absurdo", "absurda", "absurdos", "absurdas",
    "devastador", "devastadora", "devastadores", "devastadoras",
    "desastroso", "desastrosa", "desastrosos", "desastrosas",
    "milagre", "milagres",
)

# Padrões multi-token (frases) — match por substring.
SUBJECTIVE_PHRASES: tuple[str, ...] = (
    "pode destruir",
)

LOW_CONFIDENCE_THRESHOLD = 0.75
OLD_NEWS_HOURS = 72
QUOTE_MIN_CHARS = 30
SHORT_CONTENT_WORDS = 400
LONG_CONTENT_WORDS = 700

_NUMBER_RE = re.compile(r"\d")


def _hours_since_publish(published_at: datetime | None) -> float | None:
    if published_at is None:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - published_at).total_seconds() / 3600


def _has_subjective(text: str) -> bool:
    """Detecta linguagem subjetiva: word-boundary match para tokens +
    substring match para frases multi-token."""
    lower = text.lower()
    for phrase in SUBJECTIVE_PHRASES:
        if phrase in lower:
            return True
    for word in SUBJECTIVE_WORDS:
        # \b com Unicode considera acentos como letras (default em Python re)
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return True
    return False


def detect_warnings(
    item: CorroboratedItem,
    article: GeneratedArticle,
    confidence_score: float,
) -> list[str]:
    """Retorna lista de warnings identificados na matéria."""
    warnings: list[str] = []

    if not item.secondary_sources:
        warnings.append("single_source")

    if confidence_score < LOW_CONFIDENCE_THRESHOLD:
        warnings.append("low_confidence")

    hours = _hours_since_publish(item.primary.published_at)
    if hours is not None and hours > OLD_NEWS_HOURS:
        warnings.append("old_news")

    if not article.source_quote or len(article.source_quote) < QUOTE_MIN_CHARS:
        warnings.append("missing_quote")

    primary_tier = item.primary.source_tier
    if primary_tier == 4 and all(s.source_tier == 4 for s in item.secondary_sources):
        warnings.append("tier_4_only")

    if _has_subjective(article.content):
        warnings.append("subjective_language")

    if not _NUMBER_RE.search(article.content):
        warnings.append("missing_numbers")

    word_count = len(article.content.split())
    if word_count < SHORT_CONTENT_WORDS:
        warnings.append("very_short_content")
    if word_count > LONG_CONTENT_WORDS:
        warnings.append("very_long_content")

    return warnings
