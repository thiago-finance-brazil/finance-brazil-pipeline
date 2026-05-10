"""Cliente Perplexity Sonar — descobre notícias recentes em fontes confiáveis.

Usa response_format JSON Schema pra forçar saída estruturada (suportado por
sonar/sonar-pro desde meados de 2025). Em caso de payload malformado, faz
fallback pra parse manual com `json.loads`.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger
from pydantic import ValidationError

from pipeline.config import get_settings
from pipeline.sources.models import NewsItem
from pipeline.sources.whitelist import WhitelistEntry, is_whitelisted

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar"
DEFAULT_TIMEOUT = 60.0
# Perplexity API aceita até 10 domínios em search_domain_filter
MAX_DOMAIN_FILTER = 10

# Patterns que indicam URL de hub/listagem em vez de matéria específica.
# Cobre os casos mais comuns dos portais brasileiros (InfoMoney, Valor, etc).
INDEX_URL_PATTERNS = (
    "/tudo-sobre/",
    "/tags/",
    "/tag/",
    "/categoria/",
    "/categorias/",
    "/secao/",
    "/topicos/",
    "/topico/",
    "/assunto/",
    "/assuntos/",
    "/temas/",
    "/tema/",
)

SYSTEM_PROMPT = """Você é um assistente que busca notícias econômicas brasileiras em fontes confiáveis. Para cada query, retorne JSON estruturado contendo uma lista de notícias relevantes nas últimas 24-72 horas.

REGRAS CRÍTICAS:
1. Cada URL DEVE ser do artigo individual (ex.: /noticia/2026/05/10/empresa-balanco-1t26 ou /economia/2026/05/itau-lucra-12-bi.html), NUNCA páginas de listagem (/tudo-sobre/, /tags/, /categoria/, /balancos/, /economia/ sem slug específico).
2. Se uma fonte só tem URL de hub/índice/tag, NÃO inclua o item.
3. Cada item: título exato (como aparece no artigo), URL completa do artigo, resumo de 2 frases (máximo 280 caracteres), data de publicação ISO 8601 quando disponível.
4. Priorize fontes oficiais (Banco Central, B3, CVM, Tesouro) e jornais econômicos consolidados (Valor Econômico, InfoMoney, Estadão Economia, Folha Mercado).
5. Retorne APENAS JSON válido, sem texto adicional, sem markdown, sem explicações."""

NEWS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                    "published_at": {"type": "string"},
                },
                "required": ["title", "url", "summary"],
            },
        }
    },
    "required": ["items"],
}


class PerplexityResult:
    """Resultado bruto de uma chamada — útil pra cost tracking no chamador."""

    def __init__(
        self,
        items: list[NewsItem],
        input_tokens: int,
        output_tokens: int,
        raw_citations: list[str],
    ) -> None:
        self.items = items
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.raw_citations = raw_citations


def _is_specific_article_url(url: str) -> bool:
    """Filtro client-side: rejeita URLs que parecem hub/índice/tag.

    Cinto-de-segurança caso o LLM ignore a regra do system prompt.
    """
    lowered = url.lower()
    return not any(pattern in lowered for pattern in INDEX_URL_PATTERNS)


def _call_sonar(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
    domain_filter: list[str] | None = None,
) -> dict[str, Any]:
    """POST cru pra Sonar com response_format JSON Schema + opcional domain filter."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"schema": NEWS_SCHEMA},
        },
    }
    if domain_filter:
        # Perplexity API aceita no máximo 10 domínios
        payload["search_domain_filter"] = domain_filter[:MAX_DOMAIN_FILTER]
    response = httpx.post(
        PERPLEXITY_API_URL,
        headers={
            "Authorization": f"Bearer {settings.perplexity_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def journalism_domains(
    whitelist: dict[str, WhitelistEntry], max_domains: int = MAX_DOMAIN_FILTER
) -> list[str]:
    """Retorna domínios de tier 3-4 (jornalismo) ordenados por weight desc.

    Tier 1-2 (órgãos oficiais como BCB/B3/CVM e agências como Reuters/Bloomberg)
    ficam de fora porque publicam comunicados/PDFs/atas, não matérias
    jornalísticas. Usar tier 1-2 no `search_domain_filter` sufocava a Perplexity:
    em testes, retornava 0 resultados ou só PDFs CVM em vez de matérias canônicas.

    Para fact-check específico (ex.: "qual foi a Selic anunciada hoje"), o
    chamador pode passar `use_domain_filter=False` e fazer sua própria seleção
    de domínios oficiais.
    """
    journalism = [
        (domain, entry)
        for domain, entry in whitelist.items()
        if entry["tier"] in (3, 4)
    ]
    journalism.sort(key=lambda x: x[1]["weight"], reverse=True)
    return [d for d, _ in journalism[:max_domains]]


def _parse_response(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Extrai items + citations do payload Perplexity. Tolerante a markdown."""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        logger.error(f"Resposta Perplexity sem choices/content: {e}")
        return [], []
    citations = data.get("citations", []) or []
    # Tenta JSON puro primeiro
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: extrai bloco JSON de markdown (```json ... ```)
        import re

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if not match:
            logger.error(f"Resposta Perplexity não é JSON válido: {content[:200]!r}")
            return [], citations
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.error(f"JSON malformado mesmo após extração: {e}")
            return [], citations
    items = parsed.get("items", []) if isinstance(parsed, dict) else []
    return items, citations


def search_news(
    query: str,
    whitelist: dict[str, WhitelistEntry],
    *,
    max_results: int = 10,
    min_weight: float = 0.65,
    model: str = DEFAULT_MODEL,
    use_domain_filter: bool = True,
) -> PerplexityResult:
    """Busca notícias via Perplexity Sonar com filtragem por whitelist.

    Args:
        query: pergunta em linguagem natural.
        whitelist: dict carregado por `load_whitelist()`.
        max_results: máximo de resultados após filtragem (default 10).
        min_weight: filtra fontes com `weight >= min_weight` (default 0.65).
        model: modelo Perplexity (default "sonar").
        use_domain_filter: se True, usa `search_domain_filter` da Perplexity
            com os top-10 domínios por weight (default True).

    Returns:
        PerplexityResult com items ordenados por weight desc, contagem de
        tokens (pra cost tracking) e citations brutas (pra debug).
    """
    logger.info(f"Perplexity search: {query!r} (max={max_results}, min_weight={min_weight})")
    domain_filter = journalism_domains(whitelist) if use_domain_filter else None
    if domain_filter:
        logger.debug(f"  domain_filter ({len(domain_filter)}): {domain_filter}")
    try:
        data = _call_sonar(query, model=model, domain_filter=domain_filter)
    except httpx.HTTPStatusError as e:
        logger.error(f"Perplexity HTTP {e.response.status_code}: {e.response.text[:200]}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Perplexity request error: {e}")
        raise

    raw_items, citations = _parse_response(data)
    usage = data.get("usage", {}) or {}
    input_tokens = int(usage.get("prompt_tokens", 0))
    output_tokens = int(usage.get("completion_tokens", 0))

    # Enriquece + filtra por whitelist + filtro de URL específica
    enriched: list[NewsItem] = []
    rejected_index = 0
    for item in raw_items:
        url = item.get("url", "")
        if not _is_specific_article_url(url):
            logger.debug(f"  ⊘ URL de hub/índice: {url}")
            rejected_index += 1
            continue
        entry = is_whitelisted(url, whitelist)
        if entry is None:
            logger.debug(f"  ⊘ não whitelisted: {url}")
            continue
        if entry["weight"] < min_weight:
            logger.debug(f"  ⊘ peso baixo ({entry['weight']:.2f}): {url}")
            continue
        try:
            news = NewsItem(
                title=item["title"],
                url=url,
                summary=item.get("summary", ""),
                source_name=entry["name"],
                source_tier=entry["tier"],
                source_weight=entry["weight"],
                published_at=item.get("published_at") or None,
            )
        except (ValidationError, KeyError) as e:
            logger.warning(f"  ⊘ item inválido: {e}")
            continue
        enriched.append(news)

    # Ordena por weight desc, trunca em max_results
    enriched.sort(key=lambda n: n.source_weight, reverse=True)
    enriched = enriched[:max_results]

    suffix = f" ({rejected_index} URLs de índice rejeitadas)" if rejected_index else ""
    logger.info(
        f"Perplexity OK: {len(raw_items)} brutos → {len(enriched)} whitelisted{suffix} "
        f"(tokens in={input_tokens} out={output_tokens})"
    )
    return PerplexityResult(
        items=enriched,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw_citations=citations,
    )
