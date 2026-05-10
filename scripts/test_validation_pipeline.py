"""Teste end-to-end com VALIDAÇÃO: busca → corroboração → geração → validação.

Pipeline completo até o ponto onde o orchestrator decide publish/flag/reject.
Não persiste no banco — só logs + custo.

Uso:
    uv run python scripts/test_validation_pipeline.py
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
from pipeline.validation.orchestrator import validate  # noqa: E402

# Preços 2026 (USD por 1M tokens)
SONAR_INPUT = 1.00
SONAR_OUTPUT = 1.00
SONNET_INPUT = 3.00
SONNET_OUTPUT = 15.00
SONNET_CACHE_WRITE = 3.75
SONNET_CACHE_READ = 0.30

QUERY = "Itaú balanço 1T26 lucro líquido R$ 12 bi"


def estimate_perp(input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1_000_000 * SONAR_INPUT + output_tokens / 1_000_000 * SONAR_OUTPUT


def estimate_claude(input_tokens: int, output_tokens: int, cache_create: int, cache_read: int) -> float:
    return (
        input_tokens / 1_000_000 * SONNET_INPUT
        + output_tokens / 1_000_000 * SONNET_OUTPUT
        + cache_create / 1_000_000 * SONNET_CACHE_WRITE
        + cache_read / 1_000_000 * SONNET_CACHE_READ
    )


def main() -> int:
    setup_logging()
    logger.info("=" * 70)
    logger.info("TESTE END-TO-END — busca + corroboração + geração + VALIDAÇÃO")
    logger.info("=" * 70)

    whitelist = load_whitelist()
    categories = load_categories()
    logger.success(f"Whitelist: {len(whitelist)} fontes | Categorias: {len(categories)}")

    # Busca
    logger.info(f"Query: {QUERY!r}")
    primary = search_news(QUERY, whitelist, max_results=5, min_weight=0.65)
    if not primary.items:
        logger.error("Nenhum item encontrado pelo Perplexity. Encerrando.")
        return 1

    # Corroboração
    corroborated, cost_corr = corroborate(primary.items, whitelist, min_sources=2)
    confirmed = [c for c in corroborated if c.corroborated]
    logger.success(f"{len(primary.items)} primários, {len(confirmed)}/{len(corroborated)} corroborados")

    # Alvo da geração
    target = next(iter(confirmed), corroborated[0])
    logger.info(f"Alvo: {target.primary.title!r}")

    # Geração
    gen = generate_article(target, categories)
    article = gen.article
    enriched = postprocess_article(article, target.primary)

    # ========== VALIDAÇÃO ==========
    logger.info("")
    logger.info("=" * 70)
    logger.info("VALIDAÇÃO")
    logger.info("=" * 70)
    result = validate(target, article)

    color_map = {"publish": "SUCCESS", "flag": "WARNING", "reject": "ERROR"}
    log_level = color_map.get(result.decision, "INFO")
    getattr(logger, log_level.lower())(f"DECISION: {result.decision.upper()}")
    logger.info(f"  confidence_score: {result.confidence_score:.4f}")
    logger.info(f"  warnings ({len(result.warnings)}): {result.warnings}")
    if result.rejection_reason:
        logger.error(f"  rejection_reason: {result.rejection_reason}")

    # Detalhes da matéria
    logger.info("")
    logger.info("Matéria avaliada:")
    logger.info(f"  título     ({len(article.title)} chars): {article.title}")
    logger.info(f"  slug:      {enriched['slug']}")
    logger.info(f"  categoria: {article.category_slug}")
    logger.info(f"  palavras:  {len(article.content.split())}")
    logger.info(f"  source:    {target.primary.source_name} (tier {target.primary.source_tier}, weight {target.primary.source_weight})")
    logger.info(f"  secondary: {[s.source_name for s in target.secondary_sources]}")
    logger.info(f"  corroborated: {target.corroborated} (boost +{target.confidence_boost:.2f})")

    # Custo
    perp_in = primary.input_tokens + cost_corr["input_tokens"]
    perp_out = primary.output_tokens + cost_corr["output_tokens"]
    perp_cost = estimate_perp(perp_in, perp_out)
    claude_cost = estimate_claude(
        gen.input_tokens, gen.output_tokens, gen.cache_creation_tokens, gen.cache_read_tokens
    )
    total = perp_cost + claude_cost
    logger.info("")
    logger.info(f"Custo: Perplexity ${perp_cost:.4f} + Claude ${claude_cost:.4f} = ${total:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
