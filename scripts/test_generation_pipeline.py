"""Teste end-to-end: busca → corroboração → GERAÇÃO via Claude.

Reusa o ciclo da Fase 2 (Perplexity + corroboração) e adiciona a etapa
de geração via Claude Sonnet 4.6 com tool use forçado + prompt caching.

Pega o 1º item corroborado (ou o 1º da lista, se nenhum corroborado),
manda pro Claude e printa a matéria gerada formatada. NÃO salva no banco.

Uso:
    uv run python scripts/test_generation_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `pipeline` é importável quando rodando como script standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from pipeline.config import setup_logging  # noqa: E402
from pipeline.generation.claude import generate_article  # noqa: E402
from pipeline.generation.postprocess import postprocess_article  # noqa: E402
from pipeline.sources.corroborate import corroborate  # noqa: E402
from pipeline.sources.perplexity import search_news  # noqa: E402
from pipeline.sources.whitelist import load_whitelist  # noqa: E402
from pipeline.storage.supabase import load_categories  # noqa: E402

# Preços 2026 (USD por 1M tokens) — atualize se mudar o tier
SONAR_INPUT = 1.00
SONAR_OUTPUT = 1.00
SONNET_INPUT = 3.00
SONNET_OUTPUT = 15.00
SONNET_CACHE_WRITE = 3.75   # 1.25x base input
SONNET_CACHE_READ = 0.30    # 0.10x base input

QUERY = "Itaú balanço 1T26 lucro líquido R$ 12 bi"


def estimate_perp_cost(input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1_000_000 * SONAR_INPUT + output_tokens / 1_000_000 * SONAR_OUTPUT


def estimate_claude_cost(
    input_tokens: int, output_tokens: int, cache_create: int, cache_read: int
) -> float:
    """Custo Claude considerando cache write/read separados do input regular."""
    # input_tokens já EXCLUI cache_creation e cache_read na API Anthropic
    return (
        input_tokens / 1_000_000 * SONNET_INPUT
        + output_tokens / 1_000_000 * SONNET_OUTPUT
        + cache_create / 1_000_000 * SONNET_CACHE_WRITE
        + cache_read / 1_000_000 * SONNET_CACHE_READ
    )


def main() -> int:
    setup_logging()
    logger.info("=" * 70)
    logger.info("TESTE END-TO-END — busca + corroboração + GERAÇÃO")
    logger.info("=" * 70)

    # 1. Whitelist + categorias
    whitelist = load_whitelist()
    categories = load_categories()
    logger.success(f"Whitelist: {len(whitelist)} fontes ativas")
    logger.success(f"Categorias: {len(categories)} ({', '.join(c['slug'] for c in categories)})")

    # 2. Busca primária
    logger.info("")
    logger.info(f"Query: {QUERY!r}")
    primary = search_news(QUERY, whitelist, max_results=5, min_weight=0.65)
    if not primary.items:
        logger.error("Nenhum item encontrado pelo Perplexity. Encerrando.")
        return 1
    logger.success(f"{len(primary.items)} itens primários (whitelisted)")

    # 3. Corroboração (auto + busca externa se necessário)
    logger.info("")
    logger.info("Corroboração...")
    corroborated, cost_corr = corroborate(primary.items, whitelist, min_sources=2)
    confirmed = [c for c in corroborated if c.corroborated]
    logger.success(f"{len(confirmed)}/{len(corroborated)} corroborados")

    # 4. Escolhe alvo da geração: 1º corroborado, fallback p/ 1º item
    target = next(iter(confirmed), corroborated[0])
    logger.info("")
    logger.info(f"Gerando matéria para: {target.primary.title!r}")
    logger.info(f"  fonte: {target.primary.source_name}")
    logger.info(f"  corroborado: {target.corroborated} ({len(target.secondary_sources)} fontes secundárias)")

    # 5. Geração via Claude Sonnet 4.6
    logger.info("")
    gen = generate_article(target, categories)
    article = gen.article

    # 6. Postprocess — slug, reading_time, source meta
    enriched = postprocess_article(article, target.primary)

    # 7. Output formatado
    logger.info("")
    logger.info("=" * 70)
    logger.info("MATÉRIA GERADA")
    logger.info("=" * 70)
    logger.success(f"TÍTULO     ({len(article.title)} chars):")
    logger.info(f"  {article.title}")
    logger.success(f"SUBTÍTULO  ({len(article.subtitle)} chars):")
    logger.info(f"  {article.subtitle}")
    logger.success(f"EXCERPT    ({len(article.excerpt)} chars):")
    logger.info(f"  {article.excerpt}")
    logger.success(f"CATEGORIA: {article.category_slug}")
    logger.success(f"TAGS:      {article.tags}")
    logger.success(f"SLUG:      {enriched['slug']}")
    logger.success(f"READING:   {enriched['reading_time_minutes']} min")
    logger.info("")
    logger.success(f"CONTENT ({len(article.content.split())} palavras):")
    for line in article.content.split("\n"):
        logger.info(f"  {line}")
    logger.info("")
    logger.success(f"BOX IMPACTO PRÁTICO ({len(article.impact_points)} pontos):")
    for i, p in enumerate(article.impact_points, 1):
        logger.info(f"  [{i}] {p.keyword}")
        logger.info(f"      {p.text}")
    logger.info("")
    logger.success(f"SOURCE QUOTE: {article.source_quote!r}")
    logger.info(f"  url: {enriched['source_url']}")
    logger.info(f"  name: {enriched['source_name']}")

    # 8. Custo
    perp_input = primary.input_tokens + cost_corr["input_tokens"]
    perp_output = primary.output_tokens + cost_corr["output_tokens"]
    perp_cost = estimate_perp_cost(perp_input, perp_output)
    claude_cost = estimate_claude_cost(
        gen.input_tokens, gen.output_tokens, gen.cache_creation_tokens, gen.cache_read_tokens
    )
    total = perp_cost + claude_cost
    logger.info("")
    logger.info("=" * 70)
    logger.info("CUSTO")
    logger.info("=" * 70)
    logger.info(
        f"Perplexity: in={perp_input:,} out={perp_output:,} → ${perp_cost:.4f}"
    )
    logger.info(
        f"Claude:     in={gen.input_tokens:,} out={gen.output_tokens:,} "
        f"cache_create={gen.cache_creation_tokens:,} cache_read={gen.cache_read_tokens:,} → ${claude_cost:.4f}"
    )
    logger.info(f"TOTAL:      ${total:.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
