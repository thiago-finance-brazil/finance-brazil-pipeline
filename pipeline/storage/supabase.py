"""Cliente Supabase — bypass RLS via SERVICE_ROLE_KEY (pipeline backend).

ATENÇÃO: a service role key tem privilégios administrativos. Nunca expor
para o cliente — só usar em ambientes server-side controlados (Railway, dev local).
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from pipeline.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Retorna cliente Supabase singleton (lazy + cached)."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def save_pending_article(article: dict) -> dict:
    """Insere artigo na tabela `articles` com status='pending'.

    TODO: implementar.

    Args:
        article: dict completo pronto pra DB (já passou pelo postprocess).

    Returns:
        Linha inserida (com id atribuído pelo banco).
    """
    raise NotImplementedError
