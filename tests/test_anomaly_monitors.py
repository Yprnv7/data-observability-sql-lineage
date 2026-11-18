"""Tests for statistical data observability monitors: freshness, volume, and drift."""

import numpy as np

from src.lineage.models import AnomalyType
from src.monitors.anomaly_detector import AnomalyDetector


def test_freshness_evaluation() -> None:
    now = 1700000000.0

    # Fresh table (updated 300s ago, SLA is 600s)
    eval_fresh = AnomalyDetector.evaluate_freshness(
        table_name="fct_orders",
        last_updated_epoch=now - 300.0,
        sla_seconds=600.0,
        current_epoch=now,
    )
    assert eval_fresh.is_anomaly is False

    # Delayed table (updated 1200s ago, SLA is 600s)
    eval_delayed = AnomalyDetector.evaluate_freshness(
        table_name="fct_orders",
        last_updated_epoch=now - 1200.0,
        sla_seconds=600.0,
        current_epoch=now,
    )
    assert eval_delayed.is_anomaly is True
    assert eval_delayed.anomaly_type == AnomalyType.FRESHNESS_DELAY
    assert eval_delayed.deviation_score == 600.0


def test_volume_anomaly_detection() -> None:
    # Baseline ~10,000 rows with small std
    history = [10000, 10100, 9950, 10050, 9900, 10020, 10080]

    # Nominal volume
    eval_nominal = AnomalyDetector.evaluate_volume("fct_orders", 10040, history)
    assert eval_nominal.is_anomaly is False

    # Massive volume drop (only 2,000 rows -> Z > 3)
    eval_drop = AnomalyDetector.evaluate_volume("fct_orders", 2000, history)
    assert eval_drop.is_anomaly is True
    assert eval_drop.anomaly_type == AnomalyType.VOLUME_DROP
    assert eval_drop.deviation_score >= 3.0

    # Massive volume spike (35,000 rows -> Z > 3)
    eval_spike = AnomalyDetector.evaluate_volume("fct_orders", 35000, history)
    assert eval_spike.is_anomaly is True
    assert eval_spike.anomaly_type == AnomalyType.VOLUME_SPIKE


def test_distribution_drift_psi_and_ks() -> None:
    np.random.seed(42)

    # Baseline distribution: normal mean=100, std=15
    baseline = list(np.random.normal(loc=100, scale=15, size=500))

    # Stable current distribution: normal mean=100, std=15
    current_stable = list(np.random.normal(loc=100, scale=15, size=500))
    eval_stable = AnomalyDetector.evaluate_distribution_drift(
        table_name="fct_orders",
        column_name="order_amount",
        baseline_values=baseline,
        current_values=current_stable,
        psi_threshold=0.20,
    )
    assert eval_stable.is_anomaly is False
    assert eval_stable.observed_value < 0.20

    # Drifted current distribution: shifted mean=160, std=35
    current_drifted = list(np.random.normal(loc=160, scale=35, size=500))
    eval_drift = AnomalyDetector.evaluate_distribution_drift(
        table_name="fct_orders",
        column_name="order_amount",
        baseline_values=baseline,
        current_values=current_drifted,
        psi_threshold=0.20,
    )
    assert eval_drift.is_anomaly is True
    assert eval_drift.anomaly_type == AnomalyType.DISTRIBUTION_DRIFT
    assert eval_drift.observed_value >= 0.20
    assert eval_drift.p_value is not None
    assert eval_drift.p_value < 0.05
