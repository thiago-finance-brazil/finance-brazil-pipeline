"""Cálculo do confidence_score (0.0–1.0).

Sinais combinados (sem double counting):

    base            = primary.source_weight        # 0.65–1.00 (whitelist)
    + confidence_boost                              # 0.00–0.30 (Dia 2, granular por fonte)
    + freshness_bonus                               # 0.00 / 0.02 / 0.05

Cap final em 1.00.

freshness_bonus:
    < 24h        → 0.05
    24h–72h      → 0.02
    >= 72h       → 0.00
    None         → 0.00 (neutro — sem dado, sem julgamento)

Decisão de NÃO incluir corroboration_bonus fixo: `confidence_boost` (calculado
em `corroborate_item` no Dia 2) já reflete corroboração granularmente
(0.10 por fonte secundária, capped em 0.30). Adicionar mais um bônus fixo
duplicaria o peso da corroboração.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.sources.models import CorroboratedItem


def _hours_since_publish(published_at: datetime | None) -> float | None:
    """Retorna horas desde published_at ou None se ausente.

    Trata datetimes naive como UTC.
    """
    if published_at is None:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - published_at
    return delta.total_seconds() / 3600


def _freshness_bonus(published_at: datetime | None) -> float:
    """Bônus de frescor. None = neutro (sem bônus, sem warning)."""
    hours = _hours_since_publish(published_at)
    if hours is None:
        return 0.0
    if hours < 24:
        return 0.05
    if hours < 72:
        return 0.02
    return 0.0


def compute_confidence(item: CorroboratedItem) -> float:
    """Score 0.0–1.0 baseado em fonte primária + corroboração + frescor."""
    base = item.primary.source_weight
    boost = item.confidence_boost
    freshness = _freshness_bonus(item.primary.published_at)
    return min(1.0, base + boost + freshness)
