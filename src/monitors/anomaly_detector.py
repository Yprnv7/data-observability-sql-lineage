"""Statistical data observability monitors: freshness, volume anomalies, and distribution drift."""

from __future__ import annotations

import time

import numpy as np
from scipy import stats

from src.lineage.models import AnomalyEvaluation, AnomalyType


class AnomalyDetector:
    """Evaluates telemetry metrics to detect freshness delays, volume spikes/drops, and distribution drift."""

    @staticmethod
    def evaluate_freshness(
        table_name: str,
        last_updated_epoch: float,
        sla_seconds: float,
        current_epoch: float | None = None,
    ) -> AnomalyEvaluation:
        now = current_epoch if current_epoch is not None else time.time()
        elapsed_sec = max(0.0, now - last_updated_epoch)
        is_delayed = elapsed_sec > sla_seconds
        deviation = round(elapsed_sec - sla_seconds, 1)

        desc = (
            f"Table '{table_name}' SLA breached by {deviation:.1f}s (elapsed: {elapsed_sec:.1f}s, SLA: {sla_seconds:.1f}s)"
            if is_delayed
            else f"Table '{table_name}' fresh (elapsed: {elapsed_sec:.1f}s within SLA: {sla_seconds:.1f}s)"
        )

        return AnomalyEvaluation(
            table_name=table_name,
            anomaly_type=AnomalyType.FRESHNESS_DELAY,
            is_anomaly=is_delayed,
            observed_value=round(elapsed_sec, 2),
            expected_value=round(sla_seconds, 2),
            deviation_score=deviation,
            description=desc,
        )

    @staticmethod
    def evaluate_volume(
        table_name: str,
        observed_count: int,
        historical_counts: list[int],
    ) -> AnomalyEvaluation:
        if len(historical_counts) < 3:
            return AnomalyEvaluation(
                table_name=table_name,
                anomaly_type=AnomalyType.VOLUME_DROP,
                is_anomaly=False,
                observed_value=float(observed_count),
                expected_value=float(observed_count),
                deviation_score=0.0,
                description="Insufficient history for volume anomaly detection",
            )

        mean_val = float(np.mean(historical_counts))
        std_val = float(np.std(historical_counts))

        std_val = max(std_val, 1.0)  # Prevent zero-division on static tables

        z_score = (observed_count - mean_val) / std_val
        is_spike = z_score >= 3.0
        is_drop = z_score <= -3.0

        anomaly_type = AnomalyType.VOLUME_SPIKE if z_score > 0 else AnomalyType.VOLUME_DROP
        is_anomaly = is_spike or is_drop

        desc = (
            f"Volume anomaly detected on '{table_name}': observed {observed_count:,} rows "
            f"(expected {mean_val:,.0f} ± {std_val:.1f}, Z={z_score:.2f})"
            if is_anomaly
            else f"Volume nominal on '{table_name}' ({observed_count:,} rows, Z={z_score:.2f})"
        )

        return AnomalyEvaluation(
            table_name=table_name,
            anomaly_type=anomaly_type,
            is_anomaly=is_anomaly,
            observed_value=float(observed_count),
            expected_value=round(mean_val, 1),
            deviation_score=round(abs(z_score), 2),
            description=desc,
        )

    @staticmethod
    def evaluate_distribution_drift(
        table_name: str,
        column_name: str,
        baseline_values: list[float],
        current_values: list[float],
        psi_threshold: float = 0.20,
    ) -> AnomalyEvaluation:
        if len(baseline_values) < 20 or len(current_values) < 20:
            return AnomalyEvaluation(
                table_name=table_name,
                column_name=column_name,
                anomaly_type=AnomalyType.DISTRIBUTION_DRIFT,
                is_anomaly=False,
                observed_value=0.0,
                expected_value=0.0,
                deviation_score=0.0,
                description="Insufficient sample size (< 20) for statistical drift testing",
            )

        # Kolmogorov-Smirnov test
        _ks_stat, p_val = stats.ks_2samp(baseline_values, current_values)

        # Compute Population Stability Index (PSI) using 10 quantile bins
        quantiles = np.linspace(0, 100, 11)
        bins = np.percentile(baseline_values, quantiles)
        bins[0] = -np.inf
        bins[-1] = np.inf

        base_counts, _ = np.histogram(baseline_values, bins=bins)
        curr_counts, _ = np.histogram(current_values, bins=bins)

        base_pct = np.maximum(base_counts / len(baseline_values), 1e-4)
        curr_pct = np.maximum(curr_counts / len(current_values), 1e-4)

        psi = float(np.sum((curr_pct - base_pct) * np.log(curr_pct / base_pct)))
        is_drift = psi >= psi_threshold and p_val < 0.05

        desc = (
            f"Significant distribution drift on '{table_name}.{column_name}': "
            f"PSI={psi:.3f} (threshold={psi_threshold}), KS p-val={p_val:.4e}"
            if is_drift
            else f"Distribution stable on '{table_name}.{column_name}' (PSI={psi:.3f})"
        )

        return AnomalyEvaluation(
            table_name=table_name,
            column_name=column_name,
            anomaly_type=AnomalyType.DISTRIBUTION_DRIFT,
            is_anomaly=is_drift,
            observed_value=round(psi, 4),
            expected_value=psi_threshold,
            deviation_score=round(psi, 4),
            p_value=round(float(p_val), 5),
            description=desc,
        )
