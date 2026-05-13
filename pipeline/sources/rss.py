"""Cliente RSS — lê feeds de veículos brasileiros e retorna NewsItem.

Drop-in replacement pra search_news (Perplexity). Retorna RssResult
com interface compatível com PerplexityResult.

Diferenças vs Perplexity:
- Sem queries: lê últimas N matérias de cada feed
- Sem tokens: input_tokens=0, output_tokens=0 (RSS é grátis)
- Sem filtro de URL hub: RSS já só publica matérias específicas
- Filtragem por whitelist mesma (is_whitelisted)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
from loguru import logger
from pydantic import ValidationError

from pipeline.sources.models import NewsItem
from pipeline.sources.whitelist import WhitelistEntry, is_whitelisted

# Feeds RSS configurados. Adicionar/remover veículos aqui.
RSS_FEEDS: list[tuple[str, str]] = [
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
    ("Seu Dinheiro", "https://www.seudinheiro.com/feed/"),
    ("NeoFeed", "https://neofeed.com.br/feed/"),
    ("Brazil Journal", "https://braziljournal.com/feed/"),
    ("Money Times", "https://www.moneytimes.com.br/feed/"),
]

# Máximo de matérias lidas por feed em cada execução
MAX_PER_FEED = 10

# Apenas matérias publicadas nas últimas N horas
MAX_AGE_HOURS = 48


@dataclass
class RssResult:
    """Resultado da fetch — interface compatível com PerplexityResult."""

    items: list[NewsItem]
    input_tokens: int = 0
    output_tokens: int = 0
    raw_citations: list[str] = None

    def __post_init__(self):
        if self.raw_citations is None:
            self.raw_citations = []


def _parse_published(entry: dict) -> datetime | None:
    """Extrai published_at do entry. Tenta múltiplos campos."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _is_recent(published_at: datetime | None, max_age_hours: int) -> bool:
    """True se published_at é None (incluímos) ou dentro da janela."""
    if published_at is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return published_at >= cutoff


def pick_balanced(
    items: list[NewsItem],
    *,
    max_total: int = 10,
    per_source: int = 3,
) -> list[NewsItem]:
    """Round-robin por source_name pra garantir diversidade.

    Estratégia:
    1. Agrupa items por source_name (mantém ordem original dentro do grupo,
       que já está ordenada por weight/published_at do feedparser).
    2. Pra cada fonte, pega no máximo `per_source` matérias.
    3. Intercala round-robin: 1ª de cada fonte, 2ª de cada fonte, etc.
    4. Trunca em `max_total`.

    Exemplo (5 fontes, per_source=3, max_total=10):
    - InfoMoney tem 10 matérias → pega 3
    - Seu Dinheiro tem 8 → pega 3
    - NeoFeed tem 10 → pega 3
    - Brazil Journal tem 10 → pega 3
    - Money Times tem 10 → pega 3
    Total: 15 candidatos → intercala → trunca em 10
    Result: 2 InfoMoney, 2 SD, 2 NF, 2 BJ, 2 MT (perfeito 5x2)

    Edge case: se 1 fonte tem 0 matérias, skipa sem erro.
    Edge case: se total < max_total, retorna o que tem.
    """
    if not items:
        return []

    # Agrupa por source_name preservando ordem original
    by_source: dict[str, list[NewsItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    # Pega top `per_source` de cada fonte
    trimmed: dict[str, list[NewsItem]] = {
        source: items_list[:per_source]
        for source, items_list in by_source.items()
    }

    # Round-robin: pega 1ª de cada fonte, depois 2ª, etc
    # Ordena nomes pra ser determinístico (alfabético)
    sources_ordered = sorted(trimmed.keys())
    max_per_source = max((len(v) for v in trimmed.values()), default=0)

    balanced: list[NewsItem] = []
    for round_idx in range(max_per_source):
        for source in sources_ordered:
            if round_idx < len(trimmed[source]):
                balanced.append(trimmed[source][round_idx])
                if len(balanced) >= max_total:
                    return balanced

    return balanced


def fetch_rss_news(
    whitelist: dict[str, WhitelistEntry],
    *,
    max_per_feed: int = MAX_PER_FEED,
    max_age_hours: int = MAX_AGE_HOURS,
    min_weight: float = 0.65,
) -> RssResult:
    """Lê todos os RSS feeds configurados, retorna NewsItem agregados.

    Args:
        whitelist: dict de domínios → WhitelistEntry pra enriquecer tier/weight.
        max_per_feed: máximo de matérias por feed (default 10).
        max_age_hours: descarta matérias mais antigas que isso (default 48h).
        min_weight: filtra fontes com weight >= min_weight (default 0.65).

    Returns:
        RssResult com items agregados (ordenados por weight desc), interface
        compatível com PerplexityResult.
    """
    logger.info(
        f"RSS fetch: {len(RSS_FEEDS)} feeds, max_per_feed={max_per_feed}, "
        f"max_age_hours={max_age_hours}, min_weight={min_weight}"
    )

    all_items: list[NewsItem] = []
    stats = {"raw": 0, "stale": 0, "not_whitelisted": 0, "low_weight": 0, "kept": 0}

    for source_name, feed_url in RSS_FEEDS:
        try:
            logger.debug(f"  Lendo {source_name}: {feed_url}")
            parsed = feedparser.parse(feed_url)
            entries = parsed.entries[:max_per_feed]
            stats["raw"] += len(entries)
            logger.info(f"  {source_name}: {len(entries)} matérias brutas")

            for entry in entries:
                url = entry.get("link", "")
                if not url:
                    continue

                published_at = _parse_published(entry)
                if not _is_recent(published_at, max_age_hours):
                    stats["stale"] += 1
                    continue

                wl_entry = is_whitelisted(url, whitelist)
                if wl_entry is None:
                    stats["not_whitelisted"] += 1
                    logger.debug(f"    ⊘ não whitelisted: {url}")
                    continue

                if wl_entry["weight"] < min_weight:
                    stats["low_weight"] += 1
                    continue

                # Summary: feedparser dá em entry.summary ou entry.description
                summary = entry.get("summary", "") or entry.get("description", "")
                # Trunca summary em 500 chars (RSS às vezes vem com HTML longo)
                if len(summary) > 500:
                    summary = summary[:497] + "..."

                try:
                    news = NewsItem(
                        title=entry.get("title", "").strip(),
                        url=url,
                        summary=summary,
                        source_name=wl_entry["name"],
                        source_tier=wl_entry["tier"],
                        source_weight=wl_entry["weight"],
                        published_at=published_at,
                    )
                    all_items.append(news)
                    stats["kept"] += 1
                except (ValidationError, KeyError) as e:
                    logger.warning(f"    ⊘ item inválido em {source_name}: {e}")
                    continue

        except Exception as e:  # noqa: BLE001
            logger.error(f"  Falha lendo {source_name}: {e}")
            continue

    # NÃO ordena mais por weight desc — pick_balanced() cuida disso depois.
    # Mantém ordem natural dos feeds (mais recentes primeiro dentro de cada).

    # Log de distribuição por fonte (debug de diversidade)
    by_source_count: dict[str, int] = {}
    for item in all_items:
        by_source_count[item.source_name] = by_source_count.get(item.source_name, 0) + 1
    distribution = ", ".join(
        f"{s}={c}" for s, c in sorted(by_source_count.items())
    )

    logger.info(
        f"RSS OK: {stats['raw']} brutos → {stats['kept']} mantidos "
        f"(stale={stats['stale']}, not_whitelisted={stats['not_whitelisted']}, "
        f"low_weight={stats['low_weight']})"
    )
    if distribution:
        logger.info(f"RSS distribuição: {distribution}")

    return RssResult(items=all_items)
