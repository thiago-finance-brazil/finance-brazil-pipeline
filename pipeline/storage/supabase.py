"""Cliente Supabase — bypass RLS via SERVICE_ROLE_KEY (pipeline backend).

ATENÇÃO: a service role key tem privilégios administrativos. Nunca expor
para o cliente — só usar em ambientes server-side controlados (Railway, dev local).
"""
from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from loguru import logger
from supabase import Client, create_client

from pipeline.config import get_settings


class CategoryEntry(TypedDict):
    """Linha de `categories` usada pra alimentar o prompt da camada de geração."""

    slug: str
    name: str
    description: str | None


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Retorna cliente Supabase singleton (lazy + cached)."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def load_categories() -> list[CategoryEntry]:
    """Carrega categorias da tabela `categories` ordenadas por display_order.

    Usado pela camada de geração (prompts.py) pra dar a Claude a lista de
    valores válidos pra `category_slug` no schema.
    """
    client = get_client()
    response = (
        client.table("categories")
        .select("slug,name,description,display_order")
        .order("display_order", desc=False)
        .execute()
    )
    rows = response.data or []
    logger.debug(f"Categorias carregadas: {len(rows)}")
    return [
        {"slug": r["slug"], "name": r["name"], "description": r.get("description")}
        for r in rows
    ]


def save_pending_article(article: dict) -> dict:
    """Insere artigo na tabela `articles` com status='pending'.

    TODO: implementar.

    Args:
        article: dict completo pronto pra DB (já passou pelo postprocess).

    Returns:
        Linha inserida (com id atribuído pelo banco).
    """
    raise NotImplementedError
