"""Data models for column-level SQL lineage, blast radius analysis, and data observability."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TransformationType(str, Enum):
    DIRECT = "DIRECT"
    AGGREGATION = "AGGREGATION"
    EXPRESSION = "EXPRESSION"
    JOIN = "JOIN"


class AnomalyType(str, Enum):
    FRESHNESS_DELAY = "FRESHNESS_DELAY"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    VOLUME_DROP = "VOLUME_DROP"
    DISTRIBUTION_DRIFT = "DISTRIBUTION_DRIFT"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ColumnNode(BaseModel):
    table_name: str
    column_name: str
    fqdn: str  # table_name.column_name
    expression: str = ""
    is_source: bool = False


class LineageEdge(BaseModel):
    source_fqdn: str
    target_fqdn: str
    transformation_type: TransformationType = TransformationType.DIRECT


class LineageGraph(BaseModel):
    nodes: dict[str, ColumnNode] = Field(default_factory=dict)
    edges: list[LineageEdge] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)


class BlastRadiusResult(BaseModel):
    corrupted_node: str
    impacted_columns: list[str]
    impacted_tables: list[str]
    max_depth: int
    severity: SeverityLevel


class AnomalyEvaluation(BaseModel):
    table_name: str
    column_name: str | None = None
    anomaly_type: AnomalyType
    is_anomaly: bool
    observed_value: float
    expected_value: float
    deviation_score: float  # e.g., Z-score, PSI, or latency delta
    p_value: float | None = None
    description: str


class IncidentAlert(BaseModel):
    alert_id: str
    timestamp: str
    severity: SeverityLevel
    anomaly: AnomalyEvaluation
    impacted_downstream_nodes: list[str]
    impacted_tables: list[str]
    summary: str
