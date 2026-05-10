"""Teste de gravação REAL no banco — 1 query, 1 matéria.

ATENÇÃO: este script desativa DRY_RUN e grava de verdade no Supabase.
Use APENAS pra validar save_article + log_pipeline_run com 1 matéria.

Diferenças do test_main_dryrun.py:
- DRY_RUN=false (grava no banco)
- 1 query só (não as 5 do main.py)
- MAX_ARTICLES_PER_QUERY=1 (não 2)

Custo estimado: ~$0.04
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Força DRY_RUN=false
os.environ["DRY_RUN"] = "false"

from pipeline.config import get_settings  # noqa: E402

get_settings.cache_clear()

# Override TEMPORÁRIO de QUERIES e MAX (sem editar main.py)
import pipeline.main as pmain  # noqa: E402

pmain.QUERIES = ["câmbio dólar real movimento esta semana"]
pmain.MAX_ARTICLES_PER_QUERY = 1

if __name__ == "__main__":
    sys.exit(pmain.main())
