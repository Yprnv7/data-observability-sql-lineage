"""Lineage-aware incident alerting and notification formatting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.lineage.models import (
    AnomalyEvaluation,
    BlastRadiusResult,
    IncidentAlert,
    SeverityLevel,
)


class IncidentAlertManager:
    """Correlates statistical anomalies with downstream lineage dependencies to generate actionable incident alerts."""

    @staticmethod
    def create_alert(
        anomaly: AnomalyEvaluation,
        blast_radius: BlastRadiusResult | None = None,
    ) -> IncidentAlert:
        alert_id = f"inc-{uuid.uuid4().hex[:10]}"
        timestamp = datetime.now(UTC).isoformat()

        impacted_cols = blast_radius.impacted_columns if blast_radius else []
        impacted_tables = blast_radius.impacted_tables if blast_radius else []

        severity = blast_radius.severity if blast_radius else SeverityLevel.MEDIUM
        if not anomaly.is_anomaly:
            severity = SeverityLevel.LOW

        target = f"{anomaly.table_name}.{anomaly.column_name}" if anomaly.column_name else anomaly.table_name
        downstream_msg = (
            f"Impacts {len(impacted_tables)} downstream tables ({', '.join(impacted_tables[:3])})"
            if impacted_tables
            else "No downstream dependencies affected"
        )

        summary = f"[{severity.value}] {anomaly.anomaly_type.value} on {target}: {anomaly.description}. {downstream_msg}."

        return IncidentAlert(
            alert_id=alert_id,
            timestamp=timestamp,
            severity=severity,
            anomaly=anomaly,
            impacted_downstream_nodes=impacted_cols,
            impacted_tables=impacted_tables,
            summary=summary,
        )
