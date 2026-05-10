"""Teste end-to-end da camada de busca + corroboração.

Fluxo:
    1. Carrega whitelist do Supabase.
    2. Faz 1 busca primária via Perplexity Sonar.
    3. Para cada item retornado, tenta corroborar com novas buscas.
    4. Mostra resultado final com contagens e custo estimado.

Uso:
    uv run python scripts/test_search_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `pipeline` é importável quando rodando como script standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from pipeline.config import setup_logging  # noqa: E402
from pipeline.sources.corroborate import corroborate  # noqa: E402
from pipeline.sources.perplexity import search_news  # noqa: E402
from pipeline.sources.whitelist import load_whitelist  # noqa: E402

# Preço Sonar 2026 (USD por 1M tokens)
SONAR_INPUT_USD_PER_M = 1.00
SONAR_OUTPUT_USD_PER_M = 1.00

QUERY = "Itaú balanço 1T26 lucro líquido R$ 12 bi"


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Custo USD para um total de tokens no modelo sonar."""
    return (
        input_tokens / 1_000_000 * SONAR_INPUT_USD_PER_M
        + output_tokens / 1_000_000 * SONAR_OUTPUT_USD_PER_M
    )


def main() -> int:
    setup_logging()
    logger.info("=" * 70)
    logger.info("TESTE END-TO-END — busca + corroboração")
    logger.info("=" * 70)

    # 1. Whitelist
    whitelist = load_whitelist()
    logger.success(f"Whitelist: {len(whitelist)} fontes ativas")
    by_tier: dict[int, int] = {}
    for entry in whitelist.values():
        by_tier[entry["tier"]] = by_tier.get(entry["tier"], 0) + 1
    for tier in sorted(by_tier):
        logger.info(f"  tier {tier}: {by_tier[tier]} fontes")

    # 2. Busca primária
    logger.info("")
    logger.info(f"Query: {QUERY!r}")
    primary_result = search_news(QUERY, whitelist, max_results=10, min_weight=0.65)
    items = primary_result.items
    logger.success(f"{len(items)} itens passaram na whitelist (peso >= 0.65)")

    if not items:
        logger.warning("Nenhum item retornado pelo Perplexity após filtros. Encerrando.")
        return 0

    logger.info("")
    logger.info("ITENS PRIMÁRIOS:")
    for i, item in enumerate(items, 1):
        logger.info(f"  [{i}] {item.title}")
        logger.info(f"      url:    {item.url}")
        logger.info(
            f"      source: {item.source_name} (tier {item.source_tier}, "
            f"weight {item.source_weight:.2f})"
        )
        if item.summary:
            logger.info(f"      summary: {item.summary[:120]}...")
        logger.info("")

    # 3. Corroboração
    logger.info("=" * 70)
    logger.info(f"CORROBORAÇÃO ({len(items)} itens, ~1 busca cada)...")
    logger.info("=" * 70)
    corroborated, cost_corr = corroborate(items, whitelist, min_sources=2)

    # 4. Resultado final
    confirmed = [c for c in corroborated if c.corroborated]
    logger.info("")
    logger.info("=" * 70)
    logger.info("RESUMO FINAL")
    logger.info("=" * 70)
    logger.success(f"{len(items)} itens encontrados")
    logger.success(
        f"{len(confirmed)} itens corroborados (>= 2 fontes independentes)"
    )

    if confirmed:
        logger.info("")
        logger.info("ITENS CORROBORADOS:")
        for i, c in enumerate(confirmed, 1):
            logger.info(
                f"  [{i}] ✓ {c.primary.title[:80]}  ({c.total_sources} fontes, boost +{c.confidence_boost:.2f})"
            )
            for s in c.secondary_sources:
                logger.info(f"        + {s.source_name}: {s.url}")

    # Custo
    total_input = primary_result.input_tokens + cost_corr["input_tokens"]
    total_output = primary_result.output_tokens + cost_corr["output_tokens"]
    total_calls = 1 + cost_corr["calls"]
    total_cost = estimate_cost(total_input, total_output)
    logger.info("")
    logger.info(
        f"Custo: {total_calls} chamadas Perplexity | "
        f"in={total_input:,} out={total_output:,} tokens | "
        f"~${total_cost:.4f} USD"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
