"""Templates de prompt para geração editorial.

Estilo Finance Brazil: análise prática para o dono de negócio brasileiro.
Tom profissional, sem jargão, com Box Impacto Prático ao final.
"""
from __future__ import annotations

# TODO: definir prompts. Stubs abaixo só para fixar o contrato.

SYSTEM_PROMPT: str = ""
"""System prompt definindo voz, audiência, restrições de fontes."""

ARTICLE_PROMPT_TEMPLATE: str = ""
"""Template do prompt principal — recebe source_data e gera matéria completa.

Variáveis esperadas: {title}, {summary}, {url}, {source}, {secondary_sources}.
"""
