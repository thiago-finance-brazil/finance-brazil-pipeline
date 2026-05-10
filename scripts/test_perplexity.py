"""Hello-world Perplexity — query simples e printa resposta + citations.

Uso:
    uv run python scripts/test_perplexity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `pipeline` é importável quando rodando como script standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from loguru import logger  # noqa: E402

from pipeline.config import get_settings, setup_logging  # noqa: E402


def main() -> int:
    setup_logging()
    settings = get_settings()
    logger.info("Chamando Perplexity Sonar...")
    response = httpx.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.perplexity_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": "Qual a cotação atual do dólar em reais? Resposta em 1 frase.",
                }
            ],
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])
    logger.success(f"Resposta: {content}")
    if citations:
        logger.info(f"Citations ({len(citations)}):")
        for i, c in enumerate(citations[:5], 1):
            logger.info(f"  {i}. {c}")
    usage = data.get("usage", {})
    if usage:
        logger.info(
            f"Tokens: in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
