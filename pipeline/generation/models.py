"""Modelos Pydantic da camada de geração.

`GeneratedArticle` é o schema que Claude DEVE retornar via tool use forçado.
Pydantic v2 valida bounds (tamanhos de string, contagem de palavras, número
fixo de impact_points). Falhas de validação ficam visíveis no log antes
de chegar ao Supabase.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CategorySlug = Literal[
    "mercado", "empresas", "economia", "juros",
    "cambio", "tributario", "credito", "politica",
]


class ImpactPoint(BaseModel):
    """Item do Box Impacto Prático — sempre 5 por matéria."""

    keyword: str = Field(
        ...,
        min_length=2,
        max_length=40,
        description="Rótulo curto do impacto, 2-4 palavras (ex.: 'Bancos privados', 'Crédito PJ').",
    )
    text: str = Field(
        ...,
        min_length=20,
        max_length=400,
        description="Ação CONCRETA e ACIONÁVEL pro empresário, 1-2 frases. Não generalidade.",
    )


class GeneratedArticle(BaseModel):
    """Matéria pronta pra gravar no Supabase com status='review'.

    Os bounds vêm da spec do Finance Brazil. As `description` de cada campo
    são repassadas a Claude via JSON Schema da tool — fundamentais pra ele
    respeitar tamanhos exatos (especialmente word count em `content`).
    """

    title: str = Field(
        ...,
        min_length=50,
        max_length=110,
        description="Título da matéria, 60-90 caracteres. Factual, com número-chave quando possível.",
    )
    subtitle: str = Field(
        ...,
        min_length=80,
        max_length=220,
        description="Subtítulo, 120-180 caracteres, 1 frase. Resume 'o quê' + 'por que importa'.",
    )
    excerpt: str = Field(
        ...,
        min_length=150,
        max_length=400,
        description="Texto do card de listagem, 200-280 caracteres, 2 frases.",
    )
    content: str = Field(
        ...,
        min_length=500,
        description=(
            "Markdown com 4-6 parágrafos. OBRIGATORIAMENTE entre 400 e 600 palavras "
            "(não menos que 400). Sem subtítulos/headings. Use **negrito** em "
            "números importantes."
        ),
    )
    impact_points: list[ImpactPoint] = Field(
        ...,
        min_length=5,
        max_length=5,
        description="EXATAMENTE 5 pontos do Box Impacto Prático, cobrindo ângulos diferentes.",
    )
    tags: list[str] = Field(
        ...,
        min_length=3,
        max_length=7,
        description="3-7 tags em kebab-case lowercase (tickers, nomes próprios, conceitos).",
    )
    category_slug: CategorySlug = Field(
        ...,
        description="Escolher 1 categoria. Quando couber em duas, escolha a MAIS específica.",
    )
    source_quote: str = Field(
        ...,
        min_length=20,
        max_length=400,
        description="Trecho LITERAL da fonte primária (10-30 palavras). Não inventar.",
    )
    image_query: str = Field(
        ...,
        min_length=3,
        max_length=60,
        description=(
            "Query EM INGLÊS para buscar imagem no Unsplash. 2-5 palavras, "
            "conceitual e visual. NUNCA nomes próprios (Selic, Copom, Petrobras, "
            "nomes de pessoas). Use conceitos visuais universais. "
            "Exemplos válidos: 'interest rates', 'stock market trading', "
            "'oil refinery', 'tax forms', 'central bank building', "
            "'corporate office', 'currency exchange'. "
            "Exemplos INVÁLIDOS: 'Selic Copom', 'Roberto Campos Neto', "
            "'Petrobras 1T26', 'reforma tributária'."
        ),
    )

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: list[str]) -> list[str]:
        """Lowercase + strip + dedup preservando ordem."""
        seen: set[str] = set()
        out: list[str] = []
        for tag in v:
            t = tag.lower().strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    @field_validator("content")
    @classmethod
    def _word_count_bounds(cls, v: str) -> str:
        """Content em markdown deve ter ~400-600 palavras (margem 300-800)."""
        words = len(v.split())
        if not (300 <= words <= 800):
            raise ValueError(
                f"content deve ter ~400-600 palavras (margem 300-800), recebeu {words}"
            )
        return v


class GenerationResult(BaseModel):
    """Saída de generate_article() — article + custo agregado."""

    article: GeneratedArticle
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


__all__ = ["ImpactPoint", "GeneratedArticle", "GenerationResult", "CategorySlug"]
