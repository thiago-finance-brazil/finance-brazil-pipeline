"""Corroboração: cruza notícias de fontes diferentes pra detectar fact pattern consistente.

Para cada item primário, faz nova busca Perplexity com keywords específicas
e marca como corroborado se encontrar N+ fontes diferentes apontando para
o mesmo fato (similaridade de título via difflib).

TODO (Dia 3+): clusterizar items primários por tema antes de corroborar
para reduzir custo (1 busca cobre N items relacionados em vez de N buscas).
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from loguru import logger

from pipeline.sources.models import CorroboratedItem, NewsItem
from pipeline.sources.perplexity import PerplexityResult, search_news
from pipeline.sources.whitelist import WhitelistEntry

# 0.45 calibrado para jornais diferentes cobrindo o mesmo fato com títulos
# próprios (ex.: "Itaú lucra R$ 12 bi" vs "Banco Itaú reporta lucro líquido
# de 12 bilhões"). Threshold mais alto (0.6) causava 0% corroboração mesmo
# com candidatos legítimos. Trade-off: aceita falso positivo se o tema for
# muito quente (várias matérias relacionadas mas distintas).
SIMILARITY_THRESHOLD = 0.45
MAX_KEYWORDS = 5

# Stopwords curtas em português que não ajudam discriminar tópico
PT_STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "por", "com", "sem", "em", "no", "na",
    "nos", "nas", "ao", "aos", "à", "às", "e", "ou", "mas", "que", "se", "um",
    "uma", "uns", "umas", "o", "a", "os", "as", "the", "of", "to", "for",
}


def _normalize(text: str) -> str:
    """Normaliza texto pra comparação: lowercase, sem acento, sem pontuação."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text.lower()).strip()


def extract_keywords(title: str, max_keywords: int = MAX_KEYWORDS) -> list[str]:
    """Extrai keywords mais discriminantes do título.

    Estratégia: tokens >= 3 chars, sem stopwords, ordem do título preservada,
    deduplicado, truncado em `max_keywords`. Prioriza nomes próprios e números
    (capitalização original do title preservada).
    """
    normalized = _normalize(title)
    tokens: list[str] = []
    seen: set[str] = set()
    for token in normalized.split():
        if len(token) < 3 or token in PT_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens[:max_keywords]


def title_similarity(a: str, b: str) -> float:
    """Razão de similaridade entre 2 títulos (0.0–1.0) via SequenceMatcher.

    Boa pra detectar reescritas conservadoras (mesma ordem de tokens, troca
    de uma palavra ou outra). Fraca quando 2 jornais reescrevem o título
    inteiro mantendo só os fatos centrais.
    """
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _discriminant_tokens(text: str, min_len: int = 4) -> set[str]:
    """Tokens com >= `min_len` chars, sem stopwords. Boas chaves de tópico."""
    return {
        t for t in _normalize(text).split() if len(t) >= min_len and t not in PT_STOPWORDS
    }


def topic_overlap(a: str, b: str) -> float:
    """Jaccard entre tokens discriminantes (>=4 chars, sem stopwords).

    Mais robusto que `title_similarity` pra detectar 2 jornais que cobrem
    o mesmo fato com títulos reescritos. Ex.:
        "Lucro do Itaú tem alta anual de 10,4%..."
        "Itaú tem lucro líquido recorrente de R$ 12,3 bi..."
    Tokens em comum (>=4 chars): {lucro, itau, alta, anual, ...} → ~0.55.
    """
    ta = _discriminant_tokens(a)
    tb = _discriminant_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


# Threshold para topic_overlap (Jaccard de tokens). Calibrado em 0.5: dois
# títulos sobre o mesmo fato (Itaú 1T26) atingem ~0.55; tópicos diferentes
# (Itaú 1T26 vs panorama 1T26 das empresas) ficam abaixo de 0.3.
TOPIC_OVERLAP_THRESHOLD = 0.5


def cross_match_primaries(
    items: list[NewsItem],
    *,
    overlap_threshold: float = TOPIC_OVERLAP_THRESHOLD,
) -> dict[int, list[NewsItem]]:
    """Auto-corroboração: para cada item, retorna outros items (de domínios
    diferentes) que descrevem o mesmo fato segundo `topic_overlap` (Jaccard
    de tokens discriminantes).

    Quando a busca primária já retorna múltiplos jornais sobre o mesmo fato,
    isso já é corroboração — não precisa de chamada Perplexity extra. Esta
    função detecta esses casos antes de pagar pela 2ª busca.

    Returns:
        Dict `index → [NewsItem corroborantes]`. Index ausente significa
        que o item não tem match dentro do conjunto e precisa de busca externa.
    """
    matches: dict[int, list[NewsItem]] = {}
    for i, a in enumerate(items):
        cross: list[NewsItem] = []
        for j, b in enumerate(items):
            if i == j or a.domain == b.domain:
                continue
            if topic_overlap(a.title, b.title) >= overlap_threshold:
                cross.append(b)
        if cross:
            matches[i] = cross
    return matches


def corroborate_item(
    item: NewsItem,
    whitelist: dict[str, WhitelistEntry],
    *,
    min_sources: int = 2,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[CorroboratedItem, PerplexityResult | None]:
    """Tenta encontrar fontes que corroboram o item primário.

    Args:
        item: NewsItem primário a corroborar.
        whitelist: dict da whitelist (passado adiante para search_news).
        min_sources: total mínimo de fontes (incluindo primary) para considerar
            corroborado. Default 2 = primary + 1 secundária.
        similarity_threshold: limiar de SequenceMatcher.ratio() para considerar
            que 2 títulos descrevem o mesmo fato.

    Returns:
        (CorroboratedItem, PerplexityResult | None) — segundo elemento permite
        ao chamador agregar custo de tokens.
    """
    keywords = extract_keywords(item.title)
    if not keywords:
        logger.warning(f"Sem keywords úteis em: {item.title!r}")
        return CorroboratedItem(primary=item), None

    query = " ".join(keywords) + " — outras fontes confirmando este fato nas últimas 48 horas"
    try:
        result = search_news(query, whitelist, max_results=10, min_weight=0.5)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Falha buscando corroboração para {item.title!r}: {e}")
        return CorroboratedItem(primary=item), None

    primary_domain = item.domain
    secondary: list[NewsItem] = []
    for candidate in result.items:
        if candidate.domain == primary_domain:
            continue  # exclui mesma fonte
        if candidate.url == item.url:
            continue  # exclui mesma URL
        sim = title_similarity(item.title, candidate.title)
        if sim < similarity_threshold:
            continue
        secondary.append(candidate)

    corroborated = (1 + len(secondary)) >= min_sources
    # Boost simples: cada fonte adicional adiciona 0.1, capped em 0.3
    boost = min(0.1 * len(secondary), 0.3)

    logger.info(
        f"  '{item.title[:60]}...' → {len(secondary)} fontes corroborantes "
        f"(corroborado={corroborated})"
    )
    return (
        CorroboratedItem(
            primary=item,
            secondary_sources=secondary,
            corroborated=corroborated,
            confidence_boost=boost,
        ),
        result,
    )


def corroborate(
    items: list[NewsItem],
    whitelist: dict[str, WhitelistEntry],
    *,
    min_sources: int = 2,
) -> tuple[list[CorroboratedItem], dict[str, int]]:
    """Para cada item, tenta encontrar fontes que confirmam o fato.

    Estratégia em 2 fases:
        1. **Auto-corroboração** (`cross_match_primaries`): items que vieram
           juntos na busca primária com títulos similares (de domínios
           diferentes) já são corroboração mútua — sem chamada Perplexity.
        2. **Busca externa** (`corroborate_item`): só items que não tiveram
           match na fase 1 fazem 2ª chamada Perplexity.

    Args:
        items: notícias retornadas por search_news (já filtradas por whitelist).
        whitelist: dict da whitelist.
        min_sources: total mínimo de fontes (default 2).

    Returns:
        (lista de CorroboratedItem, dict com agregado de custo
        {"input_tokens", "output_tokens", "calls"}).
    """
    results: list[CorroboratedItem] = []
    cost = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    auto_matches = cross_match_primaries(items)
    if auto_matches:
        logger.info(
            f"Auto-corroboração: {len(auto_matches)}/{len(items)} items com match entre primários"
        )

    for i, item in enumerate(items):
        cross = auto_matches.get(i, [])
        # Se já temos fontes suficientes via auto-match, evitamos a busca externa
        if (1 + len(cross)) >= min_sources:
            boost = min(0.1 * len(cross), 0.3)
            results.append(
                CorroboratedItem(
                    primary=item,
                    secondary_sources=cross,
                    corroborated=True,
                    confidence_boost=boost,
                )
            )
            logger.info(
                f"  '{item.title[:60]}...' → auto-corroborado por {len(cross)} primário(s)"
            )
            continue

        # Sem auto-match (ou insuficiente) → busca externa via Perplexity
        corroborated, perplexity_result = corroborate_item(
            item, whitelist, min_sources=min_sources - len(cross)
        )
        # Mescla auto-matches + secundários da busca externa
        if cross:
            corroborated.secondary_sources = cross + corroborated.secondary_sources
            corroborated.corroborated = (1 + len(corroborated.secondary_sources)) >= min_sources
            corroborated.confidence_boost = min(0.1 * len(corroborated.secondary_sources), 0.3)
        results.append(corroborated)
        if perplexity_result is not None:
            cost["input_tokens"] += perplexity_result.input_tokens
            cost["output_tokens"] += perplexity_result.output_tokens
            cost["calls"] += 1
    return results, cost
