"""Modelos Pydantic da camada de validação."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ValidationDecision = Literal["publish", "flag", "reject"]


class ValidationResult(BaseModel):
    """Resultado consolidado de uma execução do orchestrator de validação.

    - `publish`: confidence alto E poucos warnings — humano revisa rápido.
    - `flag`: confidence médio OU warnings críticos — humano vê primeiro.
    - `reject`: filtros hard ou confidence muito baixo — vai pro banco com
      `status='rejected'` (não exposto publicamente).

    Storage decide se persiste como `pending` (publish/flag) ou `rejected`.
    Esta camada apenas DECIDE — não persiste.
    """

    decision: ValidationDecision
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


__all__ = ["ValidationDecision", "ValidationResult"]
