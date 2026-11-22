import asyncio
import hmac
import json
import logging
import platform
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import version
from typing import Any
from uuid import UUID, uuid4

from skops import io
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.serialization import model_dict
from app.modules.learning.datasets import demo_samples, real_samples
from app.modules.learning.features import FEATURE_SCHEMA, SEED, Features
from app.modules.learning.models import ModelVersion
from app.modules.learning.schemas import Module
from app.modules.learning.training import fit

logger = logging.getLogger(__name__)
MODULES: tuple[Module, ...] = ("demanda", "anomalias", "inasistencia")
TRUSTED_TYPES = (
    "sklearn.calibration._CalibratedClassifier",
    "sklearn.calibration._SigmoidCalibration",
    "sklearn.ensemble._hist_gradient_boosting.binning._BinMapper",
    "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor",
    "sklearn.frozen._frozen.FrozenEstimator",
    "sklearn._loss._loss.CyHalfBinomialLoss",
    "sklearn._loss.loss.HalfBinomialLoss",
    "sklearn._loss.link.Interval",
    "sklearn._loss.link.LogitLink",
    "sklearn.metrics._dist_metrics.EuclideanDistance64",
    "sklearn.neighbors._kd_tree.KDTree",
    # Persisted only by our fitted forests. Database artifacts require a valid signature before loading.
    "sklearn.tree._tree.Tree",
)


def environment() -> dict[str, str]:
    return {
        "schema_features": FEATURE_SCHEMA,
        "semilla": str(SEED),
        "python": ".".join(platform.python_version_tuple()[:2]),
        **{package: version(package) for package in ("scikit-learn", "skops", "numpy", "scipy")},
    }


def metadata(model: ModelVersion) -> dict[str, Any]:
    return model_dict(model, exclude={"artefacto", "sha256", "firma"})


def sign(model: ModelVersion) -> str:
    key = (settings.ml_artifact_secret or settings.jwt_secret).encode()
    fields = {
        "version": str(model.version),
        "modulo": model.modulo,
        "modo": model.modo,
        "estado": model.estado,
        "algoritmo": model.algoritmo,
        "entorno": model.entorno,
        "evaluacion": model.evaluacion,
        "sha256": model.sha256,
    }
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hmac.new(key, b"sirlod:ml-artifact:v1\0" + payload, sha256).hexdigest()


@lru_cache(maxsize=12)
def load_artifact(digest: str, artifact: bytes) -> Any:
    if len(artifact) > 32_000_000 or sha256(artifact).hexdigest() != digest:
        raise ValueError("Integridad de artefacto rechazada")
    return io.loads(artifact, trusted=list(TRUSTED_TYPES))


async def model_artifact(db: AsyncSession, model: ModelVersion) -> Any:
    if (
        model.entorno != environment()
        or model.sha256 is None
        or model.firma is None
        or not hmac.compare_digest(model.firma, sign(model))
    ):
        return None
    artifact = await db.scalar(select(ModelVersion.artefacto).where(ModelVersion.version == model.version))
    if artifact is None:
        return None
    try:
        return await asyncio.to_thread(load_artifact, model.sha256, artifact)
    except Exception:
        logger.warning("Modelo %s ilegible. Reentrenamiento requerido.", model.version)
        return None


async def active_model(db: AsyncSession, module: Module) -> tuple[ModelVersion | None, Any]:
    model = await db.scalar(
        select(ModelVersion).where(
            ModelVersion.modulo == module,
            ModelVersion.activo.is_(True),
            ModelVersion.modo == "real",
            ModelVersion.estado == "evaluado",
        )
    )
    if model is None:
        return None, None
    estimator = await model_artifact(db, model)
    return (model, estimator) if estimator is not None else (None, None)


async def train(db: AsyncSession, module: Module, mode: str) -> ModelVersion:
    if settings.is_practice and mode == "real":
        raise AppError("En el entorno de práctica solo se entrenan versiones de práctica", 409)
    if mode not in {"real", "demo"}:
        raise ValueError("Modo de entrenamiento inválido")
    # Separate runs can train separate models; concurrent runs of the same type are rejected.
    lock_id = 670520 + MODULES.index(module) * 2 + int(mode == "demo")
    if not await db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_id}):
        raise AppError("Ya hay un entrenamiento en curso para este modelo y modo", 409)
    samples = demo_samples(module) if mode == "demo" else await real_samples(db, module)
    result = await asyncio.to_thread(fit, module, samples)
    artifact = None
    digest = None
    if result.estimator is not None and (mode == "demo" or result.status == "evaluado"):
        artifact = await asyncio.to_thread(io.dumps, result.estimator)
        digest = sha256(artifact).hexdigest()
        await asyncio.to_thread(load_artifact, digest, artifact)
    model = ModelVersion(
        version=uuid4(),
        modulo=module,
        modo=mode,
        estado=result.status,
        algoritmo=result.algorithm,
        entorno=environment(),
        evaluacion=result.metrics,
        artefacto=artifact,
        sha256=digest,
        activo=False,
    )
    if artifact is not None:
        model.firma = sign(model)
    db.add(model)
    await db.flush()
    return model


async def activate(db: AsyncSession, version_id: UUID) -> ModelVersion:
    if settings.is_practice:
        raise AppError("La activación institucional se gestiona desde el entorno institucional", 409)
    model = await db.get(ModelVersion, version_id)
    if model is None:
        raise AppError("Versión inexistente", 404)
    if model.modo != "real" or model.estado != "evaluado" or await model_artifact(db, model) is None:
        raise AppError("Solo se pueden activar versiones reales evaluadas y compatibles", 409)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": 670540 + MODULES.index(model.modulo)}
    )
    await db.execute(
        update(ModelVersion)
        .where(
            ModelVersion.modulo == model.modulo,
            ModelVersion.activo.is_(True),
            ModelVersion.version != version_id,
        )
        .values(activo=False)
    )
    await db.execute(update(ModelVersion).where(ModelVersion.version == version_id).values(activo=True))
    await db.refresh(model)
    return model


async def scores(estimator: Any, module: Module, features: list[Features]) -> list[float]:
    if not features:
        return []
    if module == "anomalias":
        values = await asyncio.to_thread(estimator.score_samples, features)
        return [-float(value) for value in values]
    values = await asyncio.to_thread(estimator.predict_proba, features)
    return [float(row[1]) for row in values]
