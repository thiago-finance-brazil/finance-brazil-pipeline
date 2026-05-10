"""Persistência dos pipeline_runs na tabela `pipeline_logs`.

Cada execução do pipeline registra: run_id, status (success/error),
contagens (sources_searched, articles_generated, articles_saved),
tempo total, custo agregado.
"""
from __future__ import annotations


def log_run(run_id: str, status: str, metadata: dict) -> None:
    """Insere/atualiza linha em `pipeline_logs`.

    TODO: implementar.

    Args:
        run_id: UUID gerado no início da execução.
        status: 'running' | 'success' | 'error'.
        metadata: dict com contadores, duração, custo, erro.
    """
    raise NotImplementedError
