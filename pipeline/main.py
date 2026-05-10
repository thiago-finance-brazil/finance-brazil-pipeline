"""Entry point do pipeline. Roda 1 ciclo completo: busca → gera → valida → salva."""
from __future__ import annotations

import sys

from loguru import logger

from pipeline.config import get_settings, setup_logging


def main() -> int:
    """Roda o pipeline. Returna exit code (0 = sucesso)."""
    setup_logging()
    settings = get_settings()
    logger.info(f"Pipeline Finance Brazil — DRY_RUN={settings.dry_run}")
    logger.warning("Pipeline ainda não implementado — Dia 1 (estrutura)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
