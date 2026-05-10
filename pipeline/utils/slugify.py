"""Geração de slugs URL-safe a partir de títulos."""
from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_length: int = 80) -> str:
    """Converte texto em slug URL-safe (lowercase, sem acentos, hífens).

    Exemplos:
        "Petrobras lucra R$ 30 bi"  → "petrobras-lucra-r-30-bi"
        "Câmbio: dólar a R$ 4,89"   → "cambio-dolar-a-r-4-89"

    Args:
        text: título original.
        max_length: limita o comprimento final (default 80).

    Returns:
        Slug pronto pra URL.
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")
