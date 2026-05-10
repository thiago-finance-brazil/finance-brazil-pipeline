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

from pipeline.config import get_settings
from pipeline.generation.models import GeneratedArticle, GenerationResult
from pipeline.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from pipeline.sources.models import CorroboratedItem

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4000
TOOL_NAME = "publish_article"


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
        pydantic.ValidationError: se Claude retornar output que viola schema
            (raro com tool use forçado, mas possível em casos extremos).
        ValueError: se a resposta não contiver tool_use.
    """
    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)

    user_prompt = build_user_prompt(
        primary=item.primary,
        secondary=item.secondary_sources,
        corroborated=item.corroborated,
        categories=categories,
    )

    tool = _build_tool_schema()

    logger.info(
        f"Claude generate: {item.primary.title!r} "
        f"({len(item.secondary_sources)} fontes secundárias, model={model})"
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

    # Extrai o tool_use bloc — único elemento esperado dado tool_choice forçado
    tool_blocks = [b for b in msg.content if isinstance(b, ToolUseBlock)]
    if not tool_blocks:
        logger.error(f"Resposta Claude sem tool_use: {msg.content!r}")
        raise ValueError("Claude não chamou a tool publish_article")
    if tool_blocks[0].name != TOOL_NAME:
        raise ValueError(f"Tool inesperada: {tool_blocks[0].name}")

    article = GeneratedArticle.model_validate(tool_blocks[0].input)

    usage = msg.usage
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    logger.success(
        f"Claude OK: stop_reason={msg.stop_reason} "
        f"in={usage.input_tokens} out={usage.output_tokens} "
        f"cache_create={cache_creation} cache_read={cache_read}"
    )

    return GenerationResult(
        article=article,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_tokens=cache_creation,
        cache_read_tokens=cache_read,
    )
