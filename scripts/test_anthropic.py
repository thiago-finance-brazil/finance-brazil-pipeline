"""Hello-world Claude — chama Haiku 4.5 com saudação simples.

Uso:
    uv run python scripts/test_anthropic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `pipeline` é importável quando rodando como script standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402
from loguru import logger  # noqa: E402

from pipeline.config import get_settings, setup_logging  # noqa: E402


def main() -> int:
    setup_logging()
    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)
    logger.info("Chamando Claude Haiku 4.5...")
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": "Diga olá em português, em 1 frase curta."}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text")
    logger.success(f"Resposta: {text}")
    logger.info(f"Tokens: in={msg.usage.input_tokens} out={msg.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
