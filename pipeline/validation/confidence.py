"""Cálculo do confidence_score (0-1) baseado em corroboração, fontes, etc."""
from __future__ import annotations


def compute_confidence(article: dict) -> float:
    """Retorna score 0-1 representando confiança no fato reportado.

    TODO: implementar pesos por:
        - número de fontes corroborantes
        - status de whitelist das fontes
        - presença de citação direta (source_quote)
        - frescor (published_at recente)
    """
    raise NotImplementedError
