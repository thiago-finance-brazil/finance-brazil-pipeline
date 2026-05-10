"""Modelos Pydantic compartilhados pela camada de busca (sources/).

Centraliza os tipos NewsItem e CorroboratedItem para evitar import circular
entre perplexity.py, corroborate.py e clients downstream (generation, validation).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class NewsItem(BaseModel):
    """Notícia individual descoberta via fonte (Perplexity).

    Já enriquecida com metadados da whitelist (source_name/tier/weight).
    """

    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    summary: str = Field(default="")
    source_name: str
    source_tier: int = Field(..., ge=1, le=4)
    source_weight: float = Field(..., ge=0.0, le=1.0)
    published_at: datetime | None = None

    @property
    def domain(self) -> str:
        """Hostname da URL (lowercase, sem www.)."""
        from urllib.parse import urlparse

        host = (urlparse(self.url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host


class CorroboratedItem(BaseModel):
    """NewsItem primário + fontes secundárias que confirmam o mesmo fato."""

    primary: NewsItem
    secondary_sources: list[NewsItem] = Field(default_factory=list)
    corroborated: bool = False
    confidence_boost: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def total_sources(self) -> int:
        """Conta primary + secundárias."""
        return 1 + len(self.secondary_sources)


# Permite usar `from pipeline.sources.models import HttpUrl` sem reimport.
__all__ = ["NewsItem", "CorroboratedItem", "HttpUrl"]
