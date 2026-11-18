"""Tests for transitive blast radius and impact analysis."""

from hypothesis import given
from hypothesis import strategies as st

from src.lineage.blast_radius import BlastRadiusAnalyzer
from src.lineage.models import (
    LineageEdge,
    LineageGraph,
    SeverityLevel,
)


def test_transitive_multi_hop_blast_radius() -> None:
    graph = LineageGraph()

    # Hop 1: raw -> stg
    graph.edges.append(LineageEdge(source_fqdn="raw_orders.amount", target_fqdn="stg_orders.amount"))
    # Hop 2: stg -> fct
    graph.edges.append(LineageEdge(source_fqdn="stg_orders.amount", target_fqdn="fct_orders.total_amount"))
    # Hop 3: fct -> mrt_finance & mrt_exec
    graph.edges.append(LineageEdge(source_fqdn="fct_orders.total_amount", target_fqdn="mrt_finance.daily_revenue"))
    graph.edges.append(LineageEdge(source_fqdn="fct_orders.total_amount", target_fqdn="mrt_exec.kpi_revenue"))

    res = BlastRadiusAnalyzer.calculate_blast_radius(graph, "raw_orders.amount")

    assert res.corrupted_node == "raw_orders.amount"
    assert res.max_depth == 3
    assert "stg_orders.amount" in res.impacted_columns
    assert "fct_orders.total_amount" in res.impacted_columns
    assert "mrt_finance.daily_revenue" in res.impacted_columns
    assert "mrt_exec.kpi_revenue" in res.impacted_columns

    assert "stg_orders" in res.impacted_tables
    assert "fct_orders" in res.impacted_tables
    assert "mrt_finance" in res.impacted_tables
    assert "mrt_exec" in res.impacted_tables
    assert res.severity == SeverityLevel.CRITICAL


def test_isolated_node_zero_blast_radius() -> None:
    graph = LineageGraph()
    res = BlastRadiusAnalyzer.calculate_blast_radius(graph, "raw_orders.unrelated_col")

    assert len(res.impacted_columns) == 0
    assert len(res.impacted_tables) == 0
    assert res.max_depth == 0
    assert res.severity == SeverityLevel.LOW


@given(st.integers(min_value=1, max_value=10))
def test_hypothesis_chain_depth_monotonicity(chain_length: int) -> None:
    graph = LineageGraph()
    for i in range(chain_length):
        src = f"table_{i}.col"
        dst = f"table_{i+1}.col"
        graph.edges.append(LineageEdge(source_fqdn=src, target_fqdn=dst))

    res = BlastRadiusAnalyzer.calculate_blast_radius(graph, "table_0.col")
    assert res.max_depth == chain_length
    assert len(res.impacted_columns) == chain_length
