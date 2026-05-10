"""Whitelist de fontes confiáveis — sincroniza com tabela `source_whitelist` no Supabase.

Carrega em memória uma única vez por execução (cache no chamador). Lookup
por hostname com fallback de 1 nível de subdomínio (ex.: `m.valor.globo.com`
→ `valor.globo.com`). Não vai além disso para evitar falso positivo
perigoso (`g1.globo.com` ≠ `valor.globo.com`).
"""
from __future__ import annotations

from typing import TypedDict
from urllib.parse import urlparse

from loguru import logger

from pipeline.storage.supabase import get_client


class WhitelistEntry(TypedDict):
    """Metadados de uma fonte whitelisted."""

    domain: str
    name: str
    tier: int
    weight: float
    active: bool


def load_whitelist() -> dict[str, WhitelistEntry]:
    """Carrega fontes ativas da tabela `source_whitelist` em dict para lookup O(1).

    Returns:
        Dict `domain → WhitelistEntry`. Apenas registros com `active=true`.
    """
    client = get_client()
    response = (
        client.table("source_whitelist")
        .select("domain,name,tier,weight,active")
        .eq("active", True)
        .execute()
    )
    rows = response.data or []
    whitelist: dict[str, WhitelistEntry] = {}
    for row in rows:
        domain = (row["domain"] or "").lower().strip()
        if not domain:
            continue
        whitelist[domain] = {
            "domain": domain,
            "name": row["name"],
            "tier": int(row["tier"]),
            "weight": float(row["weight"]),
            "active": bool(row["active"]),
        }
    logger.debug(f"Whitelist carregada: {len(whitelist)} fontes ativas")
    return whitelist


def is_whitelisted(url: str, whitelist: dict[str, WhitelistEntry]) -> WhitelistEntry | None:
    """Verifica se a URL pertence a um domínio whitelisted.

    Args:
        url: URL completa (ex.: "https://valor.globo.com/financas/...").
        whitelist: dict carregado por `load_whitelist()`.

    Returns:
        WhitelistEntry se whitelisted, None caso contrário.

    Lógica de match:
        1. Extrai hostname da URL.
        2. Lowercase + remove `www.` do início.
        3. Lookup direto no dict.
        4. Se não encontrou e o hostname tem 3+ componentes, tira 1 nível
           de subdomínio e tenta de novo (ex.: `m.valor.globo.com` → `valor.globo.com`).
    """
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except (ValueError, AttributeError):
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    # Direct match
    if host in whitelist:
        return whitelist[host]
    # Try removing one subdomain level
    parts = host.split(".")
    if len(parts) > 2:
        candidate = ".".join(parts[1:])
        if candidate in whitelist:
            return whitelist[candidate]
    return None
