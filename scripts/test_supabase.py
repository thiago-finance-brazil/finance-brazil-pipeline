"""Hello-world Supabase — lê 1 artigo published e printa título.

Uso:
    uv run python scripts/test_supabase.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `pipeline` é importável quando rodando como script standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from pipeline.config import setup_logging  # noqa: E402
from pipeline.storage.supabase import get_client  # noqa: E402


def main() -> int:
    setup_logging()
    logger.info("Conectando no Supabase...")
    client = get_client()
    response = (
        client.table("articles")
        .select("id,slug,title,status,published_at")
        .eq("status", "published")
        .order("published_at", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        logger.warning("Nenhum artigo published encontrado.")
        return 0
    article = response.data[0]
    logger.success(f"Artigo mais recente: {article['title']}")
    logger.info(f"  slug: {article['slug']}")
    logger.info(f"  publicado: {article['published_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
