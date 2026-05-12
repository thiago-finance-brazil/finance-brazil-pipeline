"""Configuração do pipeline: carrega e valida variáveis de ambiente.

Use `get_settings()` em qualquer ponto do pipeline. As env vars são lidas
uma única vez (cache) e validadas via Pydantic — falha rápido se algo
estiver faltando.

Use `setup_logging()` no início de scripts/entrypoints para configurar
o loguru com formato amigável.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache

from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

load_dotenv()


class Settings(BaseModel):
    """Variáveis de ambiente validadas."""

    anthropic_api_key: str = Field(..., min_length=1)
    perplexity_api_key: str = Field(..., min_length=1)
    supabase_url: str = Field(..., min_length=1)
    supabase_service_role_key: str = Field(..., min_length=1)
    log_level: str = Field(default="INFO")
    dry_run: bool = Field(default=True)
    unsplash_access_key: str = Field(default="")
    source_mode: str = Field(default="rss")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna Settings singleton. Encerra o processo se algo faltar."""
    try:
        return Settings(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            perplexity_api_key=os.environ["PERPLEXITY_API_KEY"],
            supabase_url=os.environ["SUPABASE_URL"],
            supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            dry_run=os.environ.get("DRY_RUN", "true").lower() in ("true", "1", "yes"),
            unsplash_access_key=os.environ.get("UNSPLASH_ACCESS_KEY", ""),
            source_mode=os.environ.get("SOURCE_MODE", "rss"),
        )
    except KeyError as e:
        logger.error(f"Variável de ambiente obrigatória não definida: {e}")
        sys.exit(1)
    except ValidationError as e:
        logger.error(f"Configuração inválida: {e}")
        sys.exit(1)


def setup_logging(level: str = "INFO") -> None:
    """Configura loguru com formato amigável (timestamp + nível + módulo)."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
