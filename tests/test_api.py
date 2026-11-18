"""Integration tests for Data Observability and SQL Lineage API."""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_parse_sql_and_blast_radius_flow() -> None:
    sql = """
    SELECT
        raw_id AS id,
        user_email,
        price * qty AS total_amount
    FROM raw_transactions
    """

    # 1. Parse SQL
    parse_resp = client.post(
        "/v1/lineage/parse",
        json={"sql": sql, "target_table": "stg_transactions"},
    )
    assert parse_resp.status_code == 200
    dag_data = parse_resp.json()
    assert "stg_transactions.total_amount" in dag_data["nodes"]

    # 2. Query blast radius
    blast_resp = client.get(
        "/v1/lineage/blast-radius",
        params={"corrupted_fqdn": "raw_transactions.price"},
    )
    assert blast_resp.status_code == 200
    blast_data = blast_resp.json()
    assert "stg_transactions.total_amount" in blast_data["impacted_columns"]


def test_monitor_endpoints() -> None:
    # Volume monitor anomaly alert
    vol_resp = client.post(
        "/v1/monitors/evaluate-volume",
        json={
            "table_name": "fct_orders",
            "observed_count": 500,
            "historical_counts": [10000, 10200, 9900, 10100],
        },
    )
    assert vol_resp.status_code == 200
    vol_alert = vol_resp.json()
    assert vol_alert["anomaly"]["is_anomaly"] is True
    assert vol_alert["anomaly"]["anomaly_type"] == "VOLUME_DROP"

    # Freshness monitor nominal alert
    fresh_resp = client.post(
        "/v1/monitors/evaluate-freshness",
        json={
            "table_name": "dim_users",
            "last_updated_epoch": 1000.0,
            "sla_seconds": 500.0,
            "current_epoch": 1100.0,
        },
    )
    assert fresh_resp.status_code == 200
    fresh_alert = fresh_resp.json()
    assert fresh_alert["anomaly"]["is_anomaly"] is False


def test_validation_errors() -> None:
    res1 = client.post("/v1/lineage/parse", json={"sql": ""})
    assert res1.status_code == 400

    res2 = client.get("/v1/lineage/blast-radius", params={"corrupted_fqdn": ""})
    assert res2.status_code == 400
