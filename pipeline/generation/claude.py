"""Cliente Anthropic — gera matérias estilo Finance Brazil via Claude Sonnet 4.6.

Usa **tool use forçado** pra structured output: Claude obrigado a chamar a tool
`publish_article` cujo input_schema é o JSON Schema do `GeneratedArticle`. Isso
garante schema correto sem parse manual de JSON.

Usa **prompt caching** (`cache_control: ephemeral`) no SYSTEM_PROMPT — input
estável entre matérias. Cache hit reduz custo input em ~10x ($3/M → $0.30/M).
TTL 5min; cache write tem 1.25x ($3.75/M) na primeira chamada.
"""
from __future__ import annotations

from typing import Any

from anthropic import Anthropic
from anthropic.types import ToolUseBlock
from loguru import logger
from pydantic import ValidationError

from pipeline.config import get_settings
from pipeline.generation.models import GeneratedArticle, GenerationResult
from pipeline.generation.prompts import (
    SYSTEM_PROMPT,
    build_retry_addendum,
    build_user_prompt,
)
from pipeline.sources.models import CorroboratedItem

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4000
TOOL_NAME = "publish_article"
MAX_ATTEMPTS = 2  # original + 1 retry com prompt mais rigoroso


def _build_tool_schema() -> dict[str, Any]:
    """Constrói o JSON Schema da tool `publish_article` a partir do Pydantic model."""
    schema = GeneratedArticle.model_json_schema()
    return {
        "name": TOOL_NAME,
        "description": (
            "Publica uma matéria gerada no formato Finance Brazil. "
            "Todos os campos são obrigatórios e devem respeitar os bounds de tamanho."
        ),
        "input_schema": schema,
    }


def generate_article(
    item: CorroboratedItem,
    categories: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> GenerationResult:
    """Gera matéria via Claude Sonnet 4.6 com tool use forçado.

    Args:
        item: CorroboratedItem da Fase 2 (primary + secondary_sources).
        categories: lista de dicts {slug, name, description} do banco.
        model: identificador Claude (default sonnet-4-6).
        max_tokens: limite de tokens de saída (default 4000 — folgado pra
            matéria de 600 palavras + Box Impacto + estrutura).

    Returns:
        GenerationResult com article validado + contagens de tokens.

    Raises:
        anthropic.APIError: falhas da API.
        pydantic.ValidationError: se Claude violar bounds em AMBAS as
            MAX_ATTEMPTS tentativas (1ª + retry com prompt rigoroso).
        ValueError: se a resposta não contiver tool_use.
    """
    client = Anthropic(api_key=get_settings().anthropic_api_key)
    tool = _build_tool_schema()

    # Acumuladores de tokens — cobrem todas as tentativas (custo real total).
    total_in = 0
    total_out = 0
    total_cache_create = 0
    total_cache_read = 0
    last_error: ValidationError | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        user_prompt = build_user_prompt(
            primary=item.primary,
            secondary=item.secondary_sources,
            corroborated=item.corroborated,
            categories=categories,
        )
        if attempt > 1 and last_error is not None:
            user_prompt += build_retry_addendum(last_error)

        logger.info(
            f"Claude generate (attempt {attempt}/{MAX_ATTEMPTS}): "
            f"{item.primary.title!r} ({len(item.secondary_sources)} secundárias, model={model})"
        )

        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )

        usage = msg.usage
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        total_cache_create += getattr(usage, "cache_creation_input_tokens", 0) or 0
        total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0

        # Extrai o tool_use bloc — único elemento esperado dado tool_choice forçado
        tool_blocks = [b for b in msg.content if isinstance(b, ToolUseBlock)]
        if not tool_blocks:
            logger.error(f"Resposta Claude sem tool_use: {msg.content!r}")
            raise ValueError("Claude não chamou a tool publish_article")
        if tool_blocks[0].name != TOOL_NAME:
            raise ValueError(f"Tool inesperada: {tool_blocks[0].name}")

        try:
            article = GeneratedArticle.model_validate(tool_blocks[0].input)
        except ValidationError as e:
            last_error = e
            logger.warning(
                f"Pydantic violou bounds (attempt {attempt}/{MAX_ATTEMPTS}): {e}"
            )
            if attempt < MAX_ATTEMPTS:
                continue
            logger.error(
                f"Falha Pydantic definitiva após {MAX_ATTEMPTS} tentativas"
            )
            raise

        logger.success(
            f"Claude OK em {attempt} attempt(s): stop_reason={msg.stop_reason} "
            f"in_total={total_in} out_total={total_out} "
            f"cache_create={total_cache_create} cache_read={total_cache_read}"
        )
        return GenerationResult(
            article=article,
            input_tokens=total_in,
            output_tokens=total_out,
            cache_creation_tokens=total_cache_create,
            cache_read_tokens=total_cache_read,
        )

    # Defensive: o loop só sai por return ou raise. Se chegou aqui, há bug.
    raise RuntimeError("generate_article: loop terminou sem return/raise")
