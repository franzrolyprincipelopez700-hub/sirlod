from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models import Base


class ModelVersion(Base):
    __tablename__ = "ml_modelos"

    version: Mapped[UUID] = mapped_column(primary_key=True)
    modulo: Mapped[str]
    modo: Mapped[str]
    estado: Mapped[str]
    activo: Mapped[bool] = mapped_column(default=False)
    algoritmo: Mapped[str | None]
    entorno: Mapped[dict[str, str]] = mapped_column(JSONB)
    evaluacion: Mapped[dict[str, Any]] = mapped_column(JSONB)
    artefacto: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    sha256: Mapped[str | None]
    firma: Mapped[str | None]
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attendance(Base):
    __tablename__ = "ml_asistencias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    detalle_id: Mapped[int] = mapped_column(ForeignKey("detalle_permisos.id_d"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("trabajadores.id_t"))
    resultado: Mapped[str]
    evidencia: Mapped[str] = mapped_column(Text)
    registrado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prediction(Base):
    __tablename__ = "ml_predicciones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[UUID] = mapped_column(ForeignKey("ml_modelos.version"))
    referencia: Mapped[str]
    puntuacion: Mapped[float]
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attempt(Base):
    __tablename__ = "ml_intentos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("users.id_u"))
    permiso_id: Mapped[int | None] = mapped_column(ForeignKey("permisos.id_p"))
    resultado: Mapped[str]
    franja: Mapped[str]
    ocurrido: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Incident(Base):
    __tablename__ = "ml_incidentes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("users.id_u"))
    tipo: Mapped[str]
    estado: Mapped[str] = mapped_column(default="pendiente")
    referencia: Mapped[str] = mapped_column(unique=True)
    alerta_id: Mapped[int | None] = mapped_column(ForeignKey("ml_incidentes.id"), unique=True)
    asistencia_id: Mapped[int | None] = mapped_column(ForeignKey("ml_asistencias.id"))
    version: Mapped[UUID | None] = mapped_column(ForeignKey("ml_modelos.version"))
    evidencia: Mapped[dict[str, Any]] = mapped_column(JSONB)
    gravedad: Mapped[str | None]
    ocurrido: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Policy(Base):
    __tablename__ = "ml_normas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str]
    gravedad: Mapped[str]
    medida: Mapped[str]
    minimo_previas: Mapped[int]
    maximo_horas: Mapped[int | None]
    fundamento: Mapped[str]
    criterio: Mapped[str]
    aprobacion: Mapped[str | None]
    autor_id: Mapped[int] = mapped_column(ForeignKey("trabajadores.id_t"))
    aprobador_id: Mapped[int | None] = mapped_column(ForeignKey("trabajadores.id_t"))
    aprobada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vigente: Mapped[bool] = mapped_column(default=False)


class Measure(Base):
    __tablename__ = "ml_medidas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incidente_id: Mapped[int] = mapped_column(ForeignKey("ml_incidentes.id"))
    norma_id: Mapped[int] = mapped_column(ForeignKey("ml_normas.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("trabajadores.id_t"))
    tipo: Mapped[str]
    estado: Mapped[str]
    motivo: Mapped[str]
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Appeal(Base):
    __tablename__ = "ml_descargos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    medida_id: Mapped[int] = mapped_column(ForeignKey("ml_medidas.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("users.id_u"))
    texto: Mapped[str]
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decision: Mapped[str | None]
    revisor_id: Mapped[int | None] = mapped_column(ForeignKey("trabajadores.id_t"))
    revisado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Decision(Base):
    __tablename__ = "ml_decisiones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incidente_id: Mapped[int | None] = mapped_column(ForeignKey("ml_incidentes.id"))
    norma_id: Mapped[int | None] = mapped_column(ForeignKey("ml_normas.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("trabajadores.id_t"))
    accion: Mapped[str]
    motivo: Mapped[str]
    datos: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
