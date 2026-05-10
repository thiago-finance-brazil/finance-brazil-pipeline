"""Cliente Supabase — bypass RLS via SERVICE_ROLE_KEY (pipeline backend).

ATENÇÃO: a service role key tem privilégios administrativos. Nunca expor
para o cliente — só usar em ambientes server-side controlados (Railway, dev local).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, TypedDict
from uuid import UUID

from loguru import logger
from supabase import Client, create_client

from pipeline.config import get_settings


class CategoryEntry(TypedDict):
    """Linha de `categories` — inclui `id` (UUID) pra FK em `articles.category_id`."""

    id: str
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

    Inclui `id` (UUID) pra resolver FK `articles.category_id` no save_article.
    """
    client = get_client()
    response = (
        client.table("categories")
        .select("id,slug,name,description,display_order")
        .order("display_order", desc=False)
        .execute()
    )
    rows = response.data or []
    logger.debug(f"Categorias carregadas: {len(rows)}")
    return [
        {
            "id": r["id"],
            "slug": r["slug"],
            "name": r["name"],
            "description": r.get("description"),
        }
        for r in rows
    ]


def _category_id_by_slug(slug: str, categories: list[CategoryEntry]) -> str | None:
    """Lookup helper. Retorna None se slug não existir."""
    for c in categories:
        if c["slug"] == slug:
            return c["id"]
    return None


def save_article(
    *,
    payload: dict[str, Any],
    status: str,
    confidence_score: float,
    validation_warnings: list[str],
    secondary_sources: list[dict[str, Any]],
    run_id: UUID,
    categories: list[CategoryEntry],
) -> dict[str, Any]:
    """Insere artigo na tabela `articles` resolvendo FK de categoria.

    Args:
        payload: dict do `postprocess_article()` — contém title, subtitle,
            excerpt, content, slug, category_slug, impact_points, tags,
            source_quote, source_url, source_name, reading_time_minutes.
        status: 'review' (publish/flag) ou 'rejected'.
        confidence_score: float 0.0-1.0 do orchestrator.
        validation_warnings: lista de warnings.
        secondary_sources: lista de NewsItem dumps (model_dump(mode='json')).
        run_id: UUID do pipeline run.
        categories: lista carregada por `load_categories()` pra resolver FK.

    Returns:
        Dict com {id, slug, status} da linha inserida.

    Raises:
        Exception: erros de constraint (ex.: status='rejected' rejeitado pela
            CHECK constraint se a migration `add-rejected-status.sql` não foi
            rodada). O erro é logado com instrução clara antes de re-raise.
    """
    category_slug = payload.get("category_slug")
    category_id = _category_id_by_slug(category_slug, categories) if category_slug else None
    if category_id is None:
        raise ValueError(
            f"category_slug {category_slug!r} não encontrado em load_categories()"
        )

    row = {
        "slug": payload["slug"],
        "title": payload["title"],
        "subtitle": payload.get("subtitle"),
        "content": payload["content"],
        "excerpt": payload["excerpt"],
        "category_id": category_id,
        "reading_time_minutes": payload.get("reading_time_minutes"),
        "tags": payload.get("tags", []),
        "impact_points": payload.get("impact_points", []),
        "source_name": payload.get("source_name"),
        "source_url": payload.get("source_url"),
        "source_quote": payload.get("source_quote"),
        "secondary_sources": secondary_sources,
        "confidence_score": confidence_score,
        "validation_warnings": validation_warnings,
        "pipeline_run_id": str(run_id),
        "status": status,
    }

    client = get_client()
    try:
        response = client.table("articles").insert(row).execute()
    except Exception as e:
        msg = str(e)
        if "violates check constraint" in msg and "status" in msg:
            logger.error(
                "Constraint articles_status_check rejeitou o status. Provável "
                "causa: scripts/add-rejected-status.sql não foi rodado no "
                "Supabase Studio. Veja instruções no arquivo SQL."
            )
        else:
            logger.error(f"Erro salvando artigo: {e}")
        raise

    inserted = (response.data or [{}])[0]
    return {
        "id": inserted.get("id"),
        "slug": inserted.get("slug"),
        "status": inserted.get("status"),
    }


def check_duplicate_slug(slug: str) -> bool:
    """Retorna True se já existe artigo com esse slug na tabela `articles`.

    Considera TODOS os status (pending/published/rejected/queue/etc) — duplicar
    slug em qualquer estado não faz sentido.
    """
    if not slug:
        return False
    client = get_client()
    response = (
        client.table("articles")
        .select("id", count="exact")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )
    return (response.count or 0) > 0


