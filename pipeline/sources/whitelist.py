"""Whitelist de fontes confiáveis — sincroniza com tabela `source_whitelist` no Supabase."""
from __future__ import annotations


def load_whitelist() -> set[str]:
    """Carrega domínios autorizados da tabela `source_whitelist`.

    TODO: implementar usando o cliente Supabase de pipeline.storage.supabase.

    Returns:
        Conjunto de domínios (ex.: {"valor.globo.com", "infomoney.com.br"}).
    """
    raise NotImplementedError


def is_whitelisted(url: str, whitelist: set[str]) -> bool:
    """Verifica se a URL pertence a um domínio whitelisted.

    TODO: implementar (extrair host da URL e checar contra whitelist).
    """
    raise NotImplementedError
