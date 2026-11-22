from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from statistics import pstdev, quantiles
from typing import Any

from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from app.core.clock import LIMA
from app.modules.learning.features import SEED, Sample
from app.modules.learning.schemas import Module


@dataclass
class TrainingResult:
    status: str
    algorithm: str | None
    metrics: dict[str, Any]
    estimator: Any = None


def split(samples: list[Sample], ratios: tuple[float, ...]) -> list[list[Sample]]:
    # Group on campus date. Purge labels still unknown when the next period begins.
    ordered = sorted(
        samples,
        key=lambda row: (
            row.moment,
            row.subject or 0,
            tuple(sorted(row.features.items())),
            row.label or 0,
        ),
    )
    days = sorted({row.moment.astimezone(LIMA).date() for row in ordered})
    if len(days) <= len(ratios):
        return [[] for _ in range(len(ratios) + 1)]
    cuts = [days[int(len(days) * ratio)] for ratio in ratios]
    parts: list[list[Sample]] = [[] for _ in range(len(cuts) + 1)]
    for row in ordered:
        day = row.moment.astimezone(LIMA).date()
        bucket = sum(day >= cut for cut in cuts)
        if row.known_at is None or bucket == len(cuts) or row.known_at.astimezone(LIMA).date() < cuts[bucket]:
            parts[bucket].append(row)
    return parts


def classification_metrics(y: list[int], probability: Any, threshold: float) -> dict[str, Any]:
    predicted = [p >= threshold for p in probability]
    actual_rate, mean_probability = calibration_curve(y, probability, n_bins=5, strategy="uniform")
    return {
        "brier": float(brier_score_loss(y, probability)),
        "log_loss": float(log_loss(y, probability, labels=[0, 1])),
        "roc_auc": float(roc_auc_score(y, probability)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "matriz_confusion": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
        "calibracion": [
            {"observado": float(actual), "predicho": float(pred)}
            for actual, pred in zip(actual_rate, mean_probability, strict=True)
        ],
    }


def labels(rows: list[Sample]) -> list[int]:
    return [int(row.label == 1) for row in rows]


def coverage(rows: list[Sample]) -> dict[str, Any]:
    return {
        "n": len(rows),
        "clases": dict(Counter(str(r.label) for r in rows if r.label is not None)),
        "inicio": min((r.moment.isoformat() for r in rows), default=None),
        "fin": max((r.moment.isoformat() for r in rows), default=None),
        "cuentas": len({r.subject for r in rows if r.subject is not None}),
    }


def supervised(module: Module, samples: list[Sample]) -> TrainingResult:
    noshow = module == "inasistencia"
    parts = split(samples, (0.50, 0.68, 0.83) if noshow else (0.60, 0.80))
    train, *middle, validation, test = parts
    metrics: dict[str, Any] = {"total": len(samples), "particiones": [coverage(p) for p in parts]}
    minimum = (24, 8, 8, 8) if noshow else (30, 10, 10)
    if (
        len({s.moment.astimezone(LIMA).date() for s in samples}) < (35 if noshow else 42)
        or any(min(labels(p).count(0), labels(p).count(1)) < n for p, n in zip(parts, minimum, strict=True))
        or (noshow and any(p["cuentas"] < 5 for p in metrics["particiones"]))
    ):
        metrics["motivo"] = "Cobertura temporal, usuarios o clases insuficientes por partición"
        return TrainingResult("insuficiente", None, metrics)

    candidates = {
        "Random Forest": RandomForestClassifier(n_estimators=80, min_samples_leaf=8, random_state=SEED),
        **(
            {"Regresión logística": LogisticRegression(max_iter=1000, random_state=SEED)}
            if noshow
            else {
                "HistGradientBoosting": HistGradientBoostingClassifier(
                    max_iter=100, min_samples_leaf=18, early_stopping=False, random_state=SEED
                )
            }
        ),
    }
    models: dict[str, Any] = {}
    validation_metrics: dict[str, Any] = {}
    for name, algo in candidates.items():
        pipe = make_pipeline(DictVectorizer(sparse=False), StandardScaler(), algo)
        pipe.fit([r.features for r in train], labels(train))
        if noshow:
            calibration = middle[0]
            pipe = CalibratedClassifierCV(FrozenEstimator(pipe), method="sigmoid").fit(
                [r.features for r in calibration], labels(calibration)
            )
        models[name] = pipe
        prob = pipe.predict_proba([r.features for r in validation])[:, 1]
        threshold = 0.5
        if noshow:
            # Threshold for operational follow-up, chosen on validation only.
            threshold = max(
                (i / 20 for i in range(2, 19)),
                key=lambda x: f1_score(labels(validation), prob >= x, zero_division=0),
            )
        validation_metrics[name] = {
            **classification_metrics(labels(validation), prob, threshold),
            "umbral": threshold,
        }

    winner = min(validation_metrics, key=lambda name: validation_metrics[name]["brier"])
    threshold = validation_metrics[winner]["umbral"]
    probability = models[winner].predict_proba([r.features for r in test])[:, 1]
    test_labels = labels(test)
    test_metrics = classification_metrics(test_labels, probability, threshold)
    baseline = sum(labels(train)) / len(train)
    baseline_brier = float(brier_score_loss(test_labels, [baseline] * len(test)))
    metrics.update(
        validacion=validation_metrics,
        prueba=test_metrics,
        base_brier=baseline_brier,
        umbral_alto=threshold,
        umbral_medio=threshold / 2,
        losas_entrenadas=sorted({int(r.features["losa"]) for r in train}),
        errores_por_hora={
            str(hour): {
                "n": len(indices),
                "brier": float(brier_score_loss([test_labels[i] for i in indices], probability[indices])),
            }
            for hour in sorted({int(row.features["hora"]) for row in test})
            if (indices := [i for i, row in enumerate(test) if row.features["hora"] == hour])
        },
    )
    qualified = test_metrics["brier"] < baseline_brier and test_metrics["roc_auc"] >= 0.60
    if noshow:
        qualified = qualified and test_metrics["recall"] > 0 and test_metrics["precision"] > 0
    if not qualified:
        metrics["motivo"] = "La prueba temporal no superó la línea base y los umbrales de calidad"
    return TrainingResult("evaluado" if qualified else "rechazado", winner, metrics, models[winner])


def stress_score(model: Any, features: list[dict[str, Any]]) -> float:
    # Controlled sensitivity check, since real unusual behavior has no ground truth.
    perturbed = [
        {name: value if name == "solicitudes_media_previa" else value * 3 + 5 for name, value in row.items()}
        for row in features
    ]
    raw = -model.score_samples(features)
    stressed = -model.score_samples(perturbed)
    return sum(bool(a > b) for a, b in zip(stressed, raw, strict=True)) / len(features)


def unsupervised(samples: list[Sample]) -> TrainingResult:
    train, validation, test = split(samples, (0.60, 0.80))
    metrics: dict[str, Any] = {
        "total": len(samples),
        "particiones": [coverage(p) for p in (train, validation, test)],
    }
    if (
        len({s.moment for s in samples}) < 12
        or len(train) < 70
        or min(len(validation), len(test)) < 25
        or len({s.subject for s in train}) < 15
        or any(len({tuple(s.features.values()) for s in part}) < 8 for part in (train, validation, test))
    ):
        metrics["motivo"] = "Se requieren más semanas y variedad de actividad por cuenta"
        return TrainingResult("insuficiente", None, metrics)
    models = {
        "Isolation Forest": make_pipeline(
            DictVectorizer(sparse=False),
            StandardScaler(),
            IsolationForest(n_estimators=80, random_state=SEED),
        ),
        "Local Outlier Factor": make_pipeline(
            DictVectorizer(sparse=False), StandardScaler(), LocalOutlierFactor(n_neighbors=20, novelty=True)
        ),
    }
    reference = [r.features for r in validation]
    evaluation: dict[str, Any] = {}
    for name, model in models.items():
        model.fit([r.features for r in train])
        scores = -model.score_samples(reference)
        measures = {
            "sensibilidad_perturbacion": stress_score(model, reference),
            "umbral": quantiles([float(score) for score in scores], n=100, method="inclusive")[96],
        }
        if len(set(labels(validation))) == 2:
            measures["roc_auc_demo"] = float(roc_auc_score(labels(validation), scores))
        evaluation[name] = measures
    demo = "roc_auc_demo" in evaluation["Isolation Forest"]
    winner = max(
        models,
        key=lambda name: evaluation[name].get("roc_auc_demo" if demo else "sensibilidad_perturbacion", 0),
    )
    threshold = evaluation[winner]["umbral"]
    features = [row.features for row in test]
    scores = -models[winner].score_samples(features)
    share = sum(bool(score > threshold) for score in scores) / len(scores)
    sensitivity = stress_score(models[winner], features)
    metrics.update(
        validacion=evaluation,
        prueba={"tasa_alertas": share, "sensibilidad_perturbacion": sensitivity},
        umbral=threshold,
        entrenamiento_hasta=max(r.moment for r in train).isoformat(),
        escala="Mayor valor indica mayor rareza; no representa una probabilidad",
    )
    if demo and len(set(labels(test))) == 2:
        metrics["prueba"]["roc_auc_demo"] = float(roc_auc_score(labels(test), scores))
    passed = sensitivity >= 0.80 and share <= 0.20 and pstdev(float(score) for score in scores) > 0
    if not passed:
        metrics["motivo"] = "Detección inestable en el periodo reservado de prueba"
    return TrainingResult("evaluado" if passed else "rechazado", winner, metrics, models[winner])


def fit(module: Module, samples: list[Sample]) -> TrainingResult:
    with threadpool_limits(limits=1):
        if module == "anomalias":
            return unsupervised(samples)
        return supervised(module, samples)


def newer_than_fit(moment: datetime, metadata: dict[str, Any]) -> bool:
    return moment > datetime.fromisoformat(metadata["entrenamiento_hasta"])
