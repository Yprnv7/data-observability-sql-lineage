"""Tests for sqlglot-powered column-level SQL lineage parsing."""

from src.lineage.models import TransformationType
from src.lineage.sql_lineage import SQLLineageParser


def test_simple_select_column_lineage() -> None:
    parser = SQLLineageParser()
    sql = """
    SELECT
        id AS order_id,
        user_id,
        amount * 1.20 AS gross_amount,
        SUM(discount) AS total_discount
    FROM raw_orders
    """

    dag = parser.parse_query(sql, target_table="stg_orders")

    # Assert nodes
    assert "stg_orders.order_id" in dag.nodes
    assert "stg_orders.gross_amount" in dag.nodes
    assert "stg_orders.total_discount" in dag.nodes

    # Assert edges
    edges = {(e.source_fqdn, e.target_fqdn): e.transformation_type for e in dag.edges}
    assert ("raw_orders.id", "stg_orders.order_id") in edges
    assert ("raw_orders.amount", "stg_orders.gross_amount") in edges
    assert edges[("raw_orders.amount", "stg_orders.gross_amount")] == TransformationType.EXPRESSION
    assert edges[("raw_orders.discount", "stg_orders.total_discount")] == TransformationType.AGGREGATION


def test_multi_table_cte_and_join_lineage() -> None:
    parser = SQLLineageParser()
    sql = """
    WITH filtered_orders AS (
        SELECT order_id, customer_id, net_amount
        FROM fct_orders
        WHERE status = 'COMPLETED'
    )
    SELECT
        c.customer_id,
        c.email,
        SUM(fo.net_amount) AS lifetime_value
    FROM dim_customers c
    JOIN filtered_orders fo ON c.customer_id = fo.customer_id
    GROUP BY c.customer_id, c.email
    """

    dag = parser.parse_query(sql, target_table="mrt_customer_value")

    assert "mrt_customer_value.customer_id" in dag.nodes
    assert "mrt_customer_value.lifetime_value" in dag.nodes

    sources = {e.source_fqdn for e in dag.edges if e.target_fqdn == "mrt_customer_value.lifetime_value"}
    assert any("net_amount" in s for s in sources)
