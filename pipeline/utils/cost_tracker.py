"""Rastreamento de custo das chamadas de API (Claude + Perplexity).

Centraliza a tabela de preços por modelo e calcula custo cumulativo
de cada execução do pipeline. Útil pra alarme de orçamento e para
log em pipeline_logs.metadata.
"""
from __future__ import annotations


def track_call(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Calcula e loga custo da chamada. Retorna custo em USD.

    TODO: implementar com tabela de preços por modelo.

    Args:
        provider: "anthropic" | "perplexity".
        model: identificador do modelo (ex.: "claude-sonnet-4-6", "sonar").
        input_tokens: tokens de entrada.
        output_tokens: tokens gerados.

    Returns:
        Custo em USD desta chamada.
    """
    raise NotImplementedError
