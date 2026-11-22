from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2000)]
Kind = Literal["Normal", "Especial"]
Module = Literal["demanda", "anomalias", "inasistencia"]
MAX_DB_INTEGER = 2_147_483_647


class AttendanceIn(BaseModel):
    resultado: Literal["asistio", "inasistencia", "sin_verificar"]
    evidencia: Reason


class ReviewIn(BaseModel):
    decision: Literal["confirmar", "descartar", "anular"]
    motivo: Reason
    evidencia: Reason
    gravedad: Literal["ordinaria", "grave"] = "ordinaria"


class IncidentIn(BaseModel):
    usuario_id: int = Field(gt=0, le=MAX_DB_INTEGER)
    ocurrido: datetime | None = None
    asistencia_id: int | None = Field(default=None, gt=0)
    alerta_id: int | None = Field(default=None, gt=0)
    referencia_hecho: Reason | None = None
    evidencia: Reason

    @model_validator(mode="after")
    def source_required(self) -> "IncidentIn":
        if self.asistencia_id is None and self.referencia_hecho is None:
            raise ValueError("Indica la referencia del acta o registro que respalda el hecho")
        return self


class PolicyIn(BaseModel):
    tipo: Literal["inasistencia", "otro"]
    gravedad: Literal["ordinaria", "grave"]
    medida: Literal["preventiva", "advertencia", "suspension"]
    minimo_previas: int = Field(ge=0, le=MAX_DB_INTEGER)
    maximo_horas: int | None = Field(default=None, gt=0, le=MAX_DB_INTEGER)
    fundamento: Reason
    criterio: Reason

    @model_validator(mode="after")
    def duration_matches(self) -> "PolicyIn":
        if (self.medida == "advertencia") != (self.maximo_horas is None):
            raise ValueError("Las medidas restrictivas requieren un máximo de horas")
        if self.medida == "preventiva" and (self.tipo != "inasistencia" or self.gravedad != "ordinaria"):
            raise ValueError(
                "La restricción preventiva requiere una inasistencia verificada pendiente de revisión"
            )
        return self


class PolicyReviewIn(BaseModel):
    vigente: bool
    fundamento: Reason


class MeasureIn(BaseModel):
    norma_id: int = Field(gt=0)
    horas: int | None = Field(default=None, gt=0, le=MAX_DB_INTEGER)
    motivo: Reason
    verificacion: Reason


class MeasureReviewIn(BaseModel):
    decision: Literal["levantar", "anular"]
    motivo: Reason


class ExplanationIn(BaseModel):
    texto: Reason
