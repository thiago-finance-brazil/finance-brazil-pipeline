"""Pós-processamento: limpeza, slugify, extração de tags, geração de excerpt."""
from __future__ import annotations


def postprocess(article: dict) -> dict:
    """Aplica limpezas finais antes de salvar no Supabase.

    TODO: implementar.
        - slugify do título → slug
        - extração de tags (se Claude não retornar estruturado)
        - excerpt = primeiras N palavras se não vier do modelo
        - validação de markdown
    """
    raise NotImplementedError
