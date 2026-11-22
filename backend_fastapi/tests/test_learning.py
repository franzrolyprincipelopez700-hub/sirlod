from collections import Counter
from datetime import datetime, timedelta
from hashlib import sha256

import pytest
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import make_pipeline
from skops import io
from threadpoolctl import threadpool_limits

from app.core.clock import LIMA
from app.modules.learning.datasets import anomaly_features, demo_samples
from app.modules.learning.features import Sample
from app.modules.learning.registry import MODULES, load_artifact, scores
from app.modules.learning.training import fit, split


@pytest.mark.parametrize("module", MODULES)
async def test_demo_trains_evaluates_and_serializes(module):
    rows = demo_samples(module)
    result = fit(module, rows)
    assert result.status == "evaluado", result.metrics
    assert len(result.metrics["validacion"]) == 2
    assert result.metrics["prueba"]
    artifact = io.dumps(result.estimator)
    estimator = load_artifact(sha256(artifact).hexdigest(), artifact)
    examples = [row.features for row in rows[-12:]]
    actual = await scores(estimator, module, examples)
    assert actual == pytest.approx(await scores(result.estimator, module, examples))
    if module == "inasistencia":
        assert 0 < result.metrics["umbral_medio"] < result.metrics["umbral_alto"] < 1
        assert len(result.metrics["prueba"]["matriz_confusion"]) == 2
        assert result.metrics["prueba"]["calibracion"]
    if module == "anomalias":
        assert result.metrics["prueba"]["roc_auc_demo"] > 0.8
    with pytest.raises(ValueError, match="Integridad"):
        load_artifact("0" * 64, artifact)


@pytest.mark.parametrize("module", MODULES)
def test_insufficient_data_never_produces_estimator(module):
    result = fit(module, demo_samples(module)[:6])
    assert result.status == "insuficiente"
    assert result.estimator is None


def test_temporal_splits_purge_delayed_labels_and_keep_same_day_together():
    first = datetime(2025, 6, 1, 9, tzinfo=LIMA)
    unusual = Sample(first + timedelta(days=3), {"x": 1}, 1, first + timedelta(days=9))
    rows = [Sample(first + timedelta(days=i), {"x": i}, i % 2) for i in range(10)]
    train, validation, test = split([*rows, unusual], (0.5, 0.8))
    assert unusual not in train
    assert max(row.moment for row in train) < min(row.moment for row in validation)
    assert max(row.moment for row in validation) < min(row.moment for row in test)
    assert all("usuario" not in row.features for row in demo_samples("inasistencia"))
    assert anomaly_features(Counter({"solicitudes": 8}), 2, [2, 2, 4, 4])["aumento_solicitudes"] == 5


def test_artifacts_can_also_persist_alternative_candidates():
    samples = [{"hora": i, "losa": "1"} for i in range(120)]
    with threadpool_limits(limits=1):
        gradient = make_pipeline(DictVectorizer(sparse=False), HistGradientBoostingClassifier())
        gradient.fit(samples, [int(row["hora"] >= 60) for row in samples])
        neighbors = make_pipeline(DictVectorizer(sparse=False), LocalOutlierFactor(novelty=True))
        neighbors.fit(samples)
        for model, method in ((gradient, "predict_proba"), (neighbors, "score_samples")):
            artifact = io.dumps(model)
            restored = load_artifact(sha256(artifact).hexdigest(), artifact)
            sample = samples[:3]
            assert getattr(restored, method)(sample) == pytest.approx(getattr(model, method)(sample))
