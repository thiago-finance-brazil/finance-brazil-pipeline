"""Helpers de custo das chamadas de API (Claude + Perplexity).

Tabela de preços 2026 (USD por 1M tokens). Atualize aqui se a Anthropic
ou Perplexity mudarem os tiers — todos os módulos importam daqui.
"""
from __future__ import annotations

# Perplexity Sonar (entry tier)
SONAR_INPUT_USD_PER_M: float = 1.00
SONAR_OUTPUT_USD_PER_M: float = 1.00

# Claude Sonnet 4.6
SONNET_INPUT_USD_PER_M: float = 3.00
SONNET_OUTPUT_USD_PER_M: float = 15.00
SONNET_CACHE_WRITE_USD_PER_M: float = 3.75   # 1.25x base input
SONNET_CACHE_READ_USD_PER_M: float = 0.30    # 0.10x base input


def perplexity_cost(input_tokens: int, output_tokens: int) -> float:
    """Custo USD para uma chamada Perplexity sonar."""
    return (
        input_tokens / 1_000_000 * SONAR_INPUT_USD_PER_M
        + output_tokens / 1_000_000 * SONAR_OUTPUT_USD_PER_M
    )


def claude_sonnet_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Custo USD para uma chamada Claude Sonnet 4.6.

    Args:
        input_tokens: tokens regulares de input (NÃO inclui cache_create/read).
        output_tokens: tokens gerados.
        cache_creation_tokens: tokens cacheados nesta chamada (custo 1.25x).
        cache_read_tokens: tokens lidos do cache de chamada anterior (custo 0.10x).
    """
    return (
        input_tokens / 1_000_000 * SONNET_INPUT_USD_PER_M
        + output_tokens / 1_000_000 * SONNET_OUTPUT_USD_PER_M
        + cache_creation_tokens / 1_000_000 * SONNET_CACHE_WRITE_USD_PER_M
        + cache_read_tokens / 1_000_000 * SONNET_CACHE_READ_USD_PER_M
    )
