"""Entry point do pipeline Finance Brazil. Roda 1 ciclo completo:

    queries fixas
        → busca (Perplexity Sonar)
        → corroboração (auto-match + busca externa)
        → geração (Claude Sonnet 4.6 com tool use forçado)
        → validação (confidence + warnings + filtros)
        → save (articles status='review'/'rejected' + pipeline_logs)

DRY_RUN=true (default) NÃO persiste no banco. Use DRY_RUN=false para gravar.

Cap por query: MAX_ARTICLES_PER_QUERY (default 2). Total máximo por run =
len(QUERIES) × MAX_ARTICLES_PER_QUERY.

Resiliência:
    - Try/except por matéria (uma falha não derruba a run)
    - Try/except por query (uma query problemática não derruba o run)
    - Erros agregados em pipeline_logs.details.errors
"""
from __future__ import annotations

import sys
import time
from uuid import uuid4

from loguru import logger

from pipeline.config import get_settings, setup_logging
from pipeline.generation.claude import generate_article
from pipeline.generation.postprocess import postprocess_article
from pipeline.sources.corroborate import corroborate
from pipeline.sources.perplexity import search_news
from pipeline.sources.whitelist import load_whitelist
from pipeline.storage.logger import PipelineLogger
from pipeline.storage.supabase import load_categories, save_article
from pipeline.utils.cost_tracker import claude_sonnet_cost, perplexity_cost
from pipeline.validation.orchestrator import validate

# TODO Dia 6+: mover pra config externa (queries.yml ou tabela queries).
QUERIES: list[str] = [
    "balanços de empresas brasileiras nas últimas 48 horas",
    "decisão de juros do Copom Banco Central esta semana",
    "câmbio dólar real movimento esta semana",
    "reforma tributária CBS IBS notícias últimas",
    "fusões aquisições IPO empresas brasileiras semana",
]

MAX_ARTICLES_PER_QUERY: int = 2


def _process_item(item, gen_categories, plog, run_id, settings, query_label) -> None:
    """Processa 1 item corroborado: gera → valida → save (ou dry-run).

    Erros desta função são contidos pelo caller. Aqui só fazemos try/except
    no que precisar refinar a mensagem.
    """
    title_short = item.primary.title[:70]
    logger.info(f"  → {title_short}…")

    # === GENERATE ===
    t0 = time.perf_counter()
    gen = generate_article(item, gen_categories)
    article = gen.article
    enriched = postprocess_article(article, item.primary)
    plog.inc("generated")
    gen_ms = (time.perf_counter() - t0) * 1000
    gen_cost = claude_sonnet_cost(
        gen.input_tokens,
        gen.output_tokens,
        gen.cache_creation_tokens,
        gen.cache_read_tokens,
    )
    plog.add_stage_cost("generate", duration_ms=gen_ms, cost_usd=gen_cost)

    # === VALIDATE ===
    t0 = time.perf_counter()
    result = validate(item, article)
    val_ms = (time.perf_counter() - t0) * 1000
    plog.add_stage_cost("validate", duration_ms=val_ms)
    plog.inc(result.decision)
    logger.info(
        f"    decision={result.decision} confidence={result.confidence_score:.3f} "
        f"warnings={len(result.warnings)}"
    )

    # === SAVE ===
    target_status = "review" if result.decision in ("publish", "flag") else "rejected"
    if settings.dry_run:
        logger.info(
            f"    [DRY] Would save: slug={enriched['slug']} status={target_status}"
        )
        return

    t0 = time.perf_counter()
    secondary_dump = [s.model_dump(mode="json") for s in item.secondary_sources]
    saved = save_article(
        payload=enriched,
        status=target_status,
        confidence_score=result.confidence_score,
        validation_warnings=result.warnings,
        secondary_sources=secondary_dump,
        run_id=run_id,
        categories=gen_categories,
    )
    save_ms = (time.perf_counter() - t0) * 1000
    plog.add_stage_cost("save", duration_ms=save_ms)
    plog.inc("saved")
    logger.success(
        f"    saved: id={saved['id']} slug={saved['slug']} status={saved['status']}"
    )


def main() -> int:
    """Executa 1 ciclo do pipeline. Sempre retorna 0 (run parcial > zero)."""
    setup_logging()
    settings = get_settings()
    run_id = uuid4()

    logger.info("=" * 70)
    logger.info(f"PIPELINE START — run_id={run_id} dry_run={settings.dry_run}")
    logger.info("=" * 70)

    plog = PipelineLogger(run_id, dry_run=settings.dry_run)

    # Carrega dados estáticos uma vez
    whitelist = load_whitelist()
    gen_categories = load_categories()
    logger.info(
        f"Whitelist: {len(whitelist)} fontes | Categorias: {len(gen_categories)}"
    )

    for query in QUERIES:
        plog.inc("queries")
        logger.info("")
        logger.info(f"Query: {query!r}")
        try:
            # === SEARCH (primária + corroboração) ===
            t0 = time.perf_counter()
            primary = search_news(query, whitelist, max_results=5, min_weight=0.65)
            if not primary.items:
                logger.warning(f"  Query sem itens whitelisted, pulando.")
                search_ms = (time.perf_counter() - t0) * 1000
                search_cost = perplexity_cost(primary.input_tokens, primary.output_tokens)
                plog.add_stage_cost("search", duration_ms=search_ms, cost_usd=search_cost)
                continue

            corroborated, cost_corr = corroborate(primary.items, whitelist, min_sources=2)
            search_ms = (time.perf_counter() - t0) * 1000
            search_cost = perplexity_cost(
                primary.input_tokens + cost_corr["input_tokens"],
                primary.output_tokens + cost_corr["output_tokens"],
            )
            plog.add_stage_cost("search", duration_ms=search_ms, cost_usd=search_cost)

            top_n = corroborated[:MAX_ARTICLES_PER_QUERY]
            logger.info(
                f"  {len(primary.items)} primários, {len(corroborated)} corroborados, "
                f"processando {len(top_n)} (cap MAX_ARTICLES_PER_QUERY={MAX_ARTICLES_PER_QUERY})"
            )

            for item in top_n:
                try:
                    _process_item(item, gen_categories, plog, run_id, settings, query)
                except Exception as e:  # noqa: BLE001
                    msg = f"item {item.primary.title[:60]!r}: {e}"
                    logger.exception(msg)
                    plog.record_error("item", msg)
                    continue

        except Exception as e:  # noqa: BLE001
            msg = f"query {query!r}: {e}"
            logger.exception(msg)
            plog.record_error("query", msg)
            continue

    # === FINALIZE ===
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"RUN COMPLETO — run_id={run_id} dry_run={settings.dry_run}")
    logger.info("=" * 70)
    s = plog.summary
    logger.info(f"  queries:    {s['queries']}")
    logger.info(f"  generated:  {s['generated']}")
    logger.info(f"  saved:      {s['saved']}")
    logger.info(f"  publish:    {s['publish']}")
    logger.info(f"  flag:       {s['flag']}")
    logger.info(f"  reject:     {s['reject']}")
    logger.info(f"  errors:     {s['errors']}")
    logger.info(f"  custo:      ${plog.cost_usd:.4f}")
    for stage, metrics in plog.stages.items():
        logger.info(
            f"    {stage}: {metrics['duration_ms']:.0f}ms / ${metrics['cost_usd']:.4f}"
        )

    plog.finalize(status="success" if plog.summary["errors"] == 0 else "warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
