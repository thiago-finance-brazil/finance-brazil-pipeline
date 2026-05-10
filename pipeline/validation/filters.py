"""Filtros hard (rejeita matéria) — vai direto pro lixo, sem virar `pending`."""
from __future__ import annotations


def should_reject(article: dict) -> bool:
    """Decide se matéria deve ser descartada antes mesmo de virar pending.

    TODO: implementar checks como:
        - duplicata (slug já existe no banco)
        - fora do escopo (não é economia/mercado/empresas)
        - spam ou low quality
    """
    raise NotImplementedError
