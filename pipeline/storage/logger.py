"""PipelineLogger — agrega métricas de uma execução e persiste em `pipeline_logs`.

Modelo: 1 row por run com `details` JSONB hierárquico (escolhido sobre 1 row
por stage). Estrutura:

    {
      "started_at": "...",
      "completed_at": "...",
      "summary": {queries, generated, saved, publish, flag, reject, errors},
      "stages": {search, generate, validate, save: {duration_ms, cost_usd}},
      "errors": [{stage, message}]
    }

Em DRY_RUN, NÃO persiste no banco — apenas loga o resumo final.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger

from pipeline.storage.supabase import get_client

# Stages reconhecidos no `details.stages` JSONB
StageName = str  # "search" | "generate" | "validate" | "save"


class PipelineLogger:
    """Agregador de métricas de uma execução do pipeline.

    Uso:
        plog = PipelineLogger(run_id, dry_run=False)
        plog.inc("queries")
        plog.add_stage_cost("search", duration_ms=1234, cost_usd=0.005)
        plog.record_error("generate", "Anthropic timeout")
        plog.finalize(status="success")
    """

    def __init__(self, run_id: UUID, dry_run: bool = False) -> None:
        self.run_id = run_id
        self.dry_run = dry_run
        self._started_at = datetime.now(timezone.utc)
        self._start_perf = time.perf_counter()
        self.summary: dict[str, int] = {
            "queries": 0,
            "generated": 0,
            "saved": 0,
            "publish": 0,
            "flag": 0,
            "reject": 0,
            "errors": 0,
        }
        self.stages: dict[str, dict[str, float]] = {}
        self.errors: list[dict[str, Any]] = []
        self.cost_usd: float = 0.0

    def inc(self, key: str, n: int = 1) -> None:
        """Incrementa contador do summary."""
        self.summary[key] = self.summary.get(key, 0) + n

    def add_cost(self, usd: float) -> None:
        """Agrega custo total da run."""
        self.cost_usd += usd

    def add_stage_cost(
        self, stage: StageName, *, duration_ms: float = 0.0, cost_usd: float = 0.0
    ) -> None:
        """Agrega métricas de um stage. Pode ser chamado múltiplas vezes
        (acumula duration_ms e cost_usd)."""
        s = self.stages.setdefault(stage, {"duration_ms": 0.0, "cost_usd": 0.0})
        s["duration_ms"] += duration_ms
        s["cost_usd"] += cost_usd
        self.cost_usd += cost_usd

    def record_error(self, stage: StageName, message: str) -> None:
        """Append em `details.errors` + incrementa summary['errors']."""
        self.errors.append({"stage": stage, "message": message[:500]})
        self.inc("errors")

    def finalize(self, status: str = "success") -> dict[str, Any] | None:
        """Persiste row em `pipeline_logs` (no-op se DRY_RUN). Retorna a row
        inserida ou None em DRY_RUN."""
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((time.perf_counter() - self._start_perf) * 1000)

        row = {
            "run_id": str(self.run_id),
            "stage": "run",
            "status": status,
            "duration_ms": duration_ms,
            "cost_usd": round(self.cost_usd, 6),
            "details": {
                "started_at": self._started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "summary": self.summary,
                "stages": self.stages,
                "errors": self.errors,
            },
        }

        if self.dry_run:
            logger.info(
                f"[DRY] Skipping pipeline_logs insert. Would persist: "
                f"{row['details']['summary']} cost=${row['cost_usd']}"
            )
            return None

        try:
            client = get_client()
            response = client.table("pipeline_logs").insert(row).execute()
            inserted = (response.data or [{}])[0]
            logger.success(f"pipeline_logs row inserida: run_id={self.run_id}")
            return inserted
        except Exception as e:  # noqa: BLE001
            logger.error(f"Falha ao persistir pipeline_logs: {e}")
            return None
