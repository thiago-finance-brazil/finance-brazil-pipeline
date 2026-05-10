"""Detecta warnings de validação (não-bloqueantes — vão pro campo `validation_warnings`)."""
from __future__ import annotations


def detect_warnings(article: dict) -> list[str]:
    """Retorna lista de strings descrevendo issues a revisar manualmente.

    TODO: implementar checks como:
        - "single_source": só 1 fonte
        - "non_whitelisted_source": fonte fora da whitelist
        - "low_confidence": confidence_score < threshold
        - "missing_quote": sem citação direta
        - "old_news": published_at > 48h
    """
    raise NotImplementedError
