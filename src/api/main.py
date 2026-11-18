"""FastAPI application for SQL lineage parsing, data observability, and blast radius analysis."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.lineage.blast_radius import BlastRadiusAnalyzer
from src.lineage.models import (
    BlastRadiusResult,
    IncidentAlert,
    LineageGraph,
)
from src.lineage.sql_lineage import SQLLineageParser
from src.monitors.alerts import IncidentAlertManager
from src.monitors.anomaly_detector import AnomalyDetector

app = FastAPI(
    title="Data Observability & SQL Lineage API",
    description="Automated column-level SQL lineage parsing (sqlglot), statistical anomaly detection, and blast radius impact analysis.",
    version="0.1.0",
)

PARSER = SQLLineageParser()
ACTIVE_DAG = LineageGraph()


class ParseSQLRequest(BaseModel):
    sql: str
    target_table: str = "target_table"


class VolumeMonitorRequest(BaseModel):
    table_name: str
    observed_count: int
    historical_counts: list[int]


class FreshnessMonitorRequest(BaseModel):
    table_name: str
    last_updated_epoch: float
    sla_seconds: float
    current_epoch: float | None = None


class DriftMonitorRequest(BaseModel):
    table_name: str
    column_name: str
    baseline_values: list[float]
    current_values: list[float]
    psi_threshold: float = 0.20


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "data-observability-sql-lineage"}


@app.post("/v1/lineage/parse", response_model=LineageGraph)
def parse_sql(payload: ParseSQLRequest) -> LineageGraph:
    if not payload.sql.strip():
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")

    global ACTIVE_DAG
    ACTIVE_DAG = PARSER.parse_query(
        sql=payload.sql,
        target_table=payload.target_table,
        graph=ACTIVE_DAG,
    )
    return ACTIVE_DAG


@app.get("/v1/lineage/blast-radius", response_model=BlastRadiusResult)
def get_blast_radius(corrupted_fqdn: str) -> BlastRadiusResult:
    if not corrupted_fqdn.strip():
        raise HTTPException(status_code=400, detail="corrupted_fqdn cannot be empty")

    return BlastRadiusAnalyzer.calculate_blast_radius(ACTIVE_DAG, corrupted_fqdn)


@app.post("/v1/monitors/evaluate-volume", response_model=IncidentAlert)
def monitor_volume(payload: VolumeMonitorRequest) -> IncidentAlert:
    eval_res = AnomalyDetector.evaluate_volume(
        table_name=payload.table_name,
        observed_count=payload.observed_count,
        historical_counts=payload.historical_counts,
    )

    blast: BlastRadiusResult | None = None
    if eval_res.is_anomaly:
        # Check blast radius for the table
        blast = BlastRadiusAnalyzer.calculate_blast_radius(ACTIVE_DAG, f"{payload.table_name}.*")

    return IncidentAlertManager.create_alert(anomaly=eval_res, blast_radius=blast)


@app.post("/v1/monitors/evaluate-freshness", response_model=IncidentAlert)
def monitor_freshness(payload: FreshnessMonitorRequest) -> IncidentAlert:
    eval_res = AnomalyDetector.evaluate_freshness(
        table_name=payload.table_name,
        last_updated_epoch=payload.last_updated_epoch,
        sla_seconds=payload.sla_seconds,
        current_epoch=payload.current_epoch,
    )

    blast: BlastRadiusResult | None = None
    if eval_res.is_anomaly:
        blast = BlastRadiusAnalyzer.calculate_blast_radius(ACTIVE_DAG, f"{payload.table_name}.*")

    return IncidentAlertManager.create_alert(anomaly=eval_res, blast_radius=blast)


@app.post("/v1/monitors/evaluate-drift", response_model=IncidentAlert)
def monitor_drift(payload: DriftMonitorRequest) -> IncidentAlert:
    eval_res = AnomalyDetector.evaluate_distribution_drift(
        table_name=payload.table_name,
        column_name=payload.column_name,
        baseline_values=payload.baseline_values,
        current_values=payload.current_values,
        psi_threshold=payload.psi_threshold,
    )

    blast: BlastRadiusResult | None = None
    if eval_res.is_anomaly:
        fqdn = f"{payload.table_name}.{payload.column_name}"
        blast = BlastRadiusAnalyzer.calculate_blast_radius(ACTIVE_DAG, fqdn)

    return IncidentAlertManager.create_alert(anomaly=eval_res, blast_radius=blast)
