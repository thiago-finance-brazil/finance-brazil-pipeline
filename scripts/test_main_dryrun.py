"""Roda pipeline.main em DRY_RUN forçado.

Ignora o valor de DRY_RUN no .env e força True (operações de banco viram
no-op + log "[DRY] Would save"). Útil pra:
- Validar fluxo end-to-end sem persistir
- Estimar custo Perplexity + Claude antes de ligar produção
- Debugar prompts/queries sem poluir tabela articles

Uso:
    uv run python scripts/test_main_dryrun.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Garante que `pipeline` é importável quando rodando como script standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Força DRY_RUN=true ANTES de importar pipeline.main (que cacheia settings).
os.environ["DRY_RUN"] = "true"

from pipeline.config import get_settings  # noqa: E402

# Limpa cache de settings caso já tenha sido carregado
get_settings.cache_clear()

from pipeline.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
