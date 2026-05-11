"""Cliente Unsplash API — busca imagem por query.

Retorna URL da 1ª imagem 'regular' (1080px wide, landscape, relevant order)
ou None em qualquer falha (sem key, erro de rede, sem resultados, etc).

Quota free do Unsplash: 50 req/h. Pipeline usa ~10 req/cron, sem risco.
"""
from __future__ import annotations

import httpx
from loguru import logger

from pipeline.config import get_settings

UNSPLASH_API = "https://api.unsplash.com/search/photos"
TIMEOUT_SECONDS = 8.0


def fetch_image_url(query: str) -> str | None:
    """Busca 1ª imagem relevante no Unsplash. Retorna URL ou None.

    Args:
        query: termo de busca (ex: "Roberto Campos Neto", "Selic Banco Central").
               Idealmente 2-5 palavras. Vazio retorna None.

    Returns:
        URL da imagem 'regular' (~1080px) ou None se:
        - UNSPLASH_ACCESS_KEY não configurada
        - Query vazia
        - Erro de rede / timeout
        - 0 resultados retornados
        - Resposta com formato inesperado
    """
    if not query or not query.strip():
        logger.debug("Unsplash: query vazia, skip")
        return None

    settings = get_settings()
    key = getattr(settings, "unsplash_access_key", "")
    if not key:
        logger.warning("Unsplash: UNSPLASH_ACCESS_KEY não configurada, skip")
        return None

    params = {
        "query": query.strip(),
        "per_page": 1,
        "orientation": "landscape",
        "order_by": "relevant",
    }
    headers = {"Authorization": f"Client-ID {key}"}

    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.get(UNSPLASH_API, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        logger.warning(f"Unsplash request falhou ('{query}'): {e}")
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Unsplash erro inesperado ('{query}'): {e}")
        return None

    results = data.get("results", [])
    if not results:
        logger.info(f"Unsplash: 0 resultados pra '{query}'")
        return None

    first = results[0]
    urls = first.get("urls", {})
    image_url = urls.get("regular")
    if not image_url:
        logger.warning(f"Unsplash: 1º resultado sem URL 'regular' pra '{query}'")
        return None

    logger.debug(f"Unsplash OK: '{query}' → {image_url[:80]}…")
    return image_url
