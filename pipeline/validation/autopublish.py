"""Decisão de auto-publicação — porteiro entre `status='review'` e `status='published'`.

Contexto (decisão editorial do Thiago, 03/ago/2026): o pipeline passou a
publicar direto o que antes ficava na fila de aprovação manual. Duas exceções
continuam exigindo olho humano antes de ir pro ar:

1. **Categoria `politica`** — matéria política tem risco reputacional e de
   enviesamento maior que o resto da editoria. Mesmo com as restrições do
   system prompt (não tomar posição partidária), o custo de um deslize
   publicado é alto demais pra confiar no automático.

2. **Loteria** — Finance Brazil é veículo de finanças pra empresário, não de
   resultado de sorteio. Feeds RSS de portais generalistas (G1, UOL, etc.)
   injetam muito conteúdo de Lotofácil/Mega-Sena na editoria de "economia",
   e essas matérias não têm valor editorial aqui. Ficam em revisão pro Thiago
   descartar manualmente.

O que não cai nessas duas regras vai direto pra `published`. Matérias com
`decision='reject'` nem chegam aqui — são barradas antes, em
`validation/orchestrator.py`.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Categoria que nunca é auto-publicada (slug do `CategorySlug` Literal).
POLITICS_SLUG: Final[str] = "politica"

#: Palavras-chave que denunciam matéria de loteria. Comparação é feita sobre o
#: título normalizado (lowercase, sem acentos), então basta listar uma grafia —
#: "lotofacil" cobre "Lotofácil". As variantes com/sem hífen e com/sem espaço
#: estão listadas porque a normalização não mexe em separadores.
#:
#: Só entram aqui termos ESPECÍFICOS de loteria — nomes próprios dos jogos e
#: do canal de pagamento (lotérica). Palavras amplas foram deliberadamente
#: deixadas de fora: "concurso" pegaria concurso público, "milionária" pegaria
#: "aquisição milionária de startup" (M&A, pauta legítima). Falso positivo aqui
#: joga matéria válida na fila de aprovação manual, que é exatamente o custo
#: que a auto-publicação existe pra eliminar. As loterias brasileiras sempre
#: aparecem pelo nome próprio no título, então o nome do jogo basta.
LOTTERY_KEYWORDS: Final[frozenset[str]] = frozenset({
    "loteria", "lotérica", "loterica", "lotofácil", "lotofacil",
    "mega-sena", "megasena", "mega sena", "quina", "timemania",
    "dupla sena", "lotomania", "dia de sorte", "super sete", "loteca"
})


def _strip_accents(text: str) -> str:
    """Remove acentos via decomposição NFKD, descartando os diacríticos."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize(text: str) -> str:
    """Normaliza pra comparação: sem acentos, lowercase, espaços colapsados."""
    return re.sub(r"\s+", " ", _strip_accents(text).lower()).strip()


def _build_lottery_pattern() -> re.Pattern[str]:
    """Compila as keywords num único regex com fronteiras de palavra.

    A fronteira é essencial: sem ela, "quina" casaria dentro de "máquina"
    e "esquina", mandando pra revisão matéria legítima sobre máquina pública
    ou maquininha de cartão.

    Usa lookarounds `(?<!\\w)` / `(?!\\w)` em vez de `\\b` porque `\\b` inverte
    o sentido quando a keyword começa ou termina em caractere não-alfanumérico
    — os lookarounds seguem corretos se alguém adicionar um termo assim depois.
    """
    alternatives = sorted(
        (re.escape(_normalize(kw)) for kw in LOTTERY_KEYWORDS),
        key=len,
        reverse=True,
    )
    return re.compile(rf"(?<!\w)(?:{'|'.join(alternatives)})(?!\w)")


_LOTTERY_RE: Final[re.Pattern[str]] = _build_lottery_pattern()


def is_lottery_title(title: str) -> bool:
    """True se o título menciona alguma loteria (case e acento insensíveis)."""
    return bool(_LOTTERY_RE.search(_normalize(title)))


def should_autopublish(category_slug: str, title: str) -> tuple[bool, str]:
    """Decide se a matéria pode ir direto pra 'published'.

    Args:
        category_slug: slug da categoria escolhida pelo modelo (ex.: 'economia').
        title: título da matéria gerada.

    Returns:
        (True, "") se pode auto-publicar.
        (False, motivo) se deve ir pra revisão humana — o motivo é texto curto
        pronto pra log (ex.: "categoria politica").
    """
    if _normalize(category_slug) == POLITICS_SLUG:
        return False, "categoria politica"

    if is_lottery_title(title):
        return False, "loteria detectada"

    return True, ""


__all__ = [
    "LOTTERY_KEYWORDS",
    "POLITICS_SLUG",
    "is_lottery_title",
    "should_autopublish",
]
