# Data Observability & SQL Lineage Benchmark Results

- **Evaluation Date:** 2026-11-18
- **Hardware Platform:** Apple A18 Pro (8.0 GB RAM)
- **Operating System:** Darwin 25.4.0
- **Python Version:** 3.14.6

---

## 1. Column-Level SQL Lineage Parsing Throughput

| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Queries Parsed** | `100` complex queries | CTEs, joins, aggregations, aliases |
| **Graph Generated** | `114` nodes, `800` edges | Unified column-level DAG |
| **Parsing Throughput** | **`1,056.2 queries/sec`** | sqlglot AST column dependency extraction |
| **Median Latency (p50)** | **`0.725 ms`** | Query-to-graph projection |
| **95th Percentile Latency (p95)** | **`1.16 ms`** | Deep CTE expression traversal |

---

## 2. Downstream Blast Radius Traversal Latency

| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Pipeline Depth** | `20` consecutive hops | Staging to executive analytical marts |
| **Impacted Nodes Resolved** | `1` column dependencies | Transitive forward BFS graph walk |
| **Median Traversal Latency (p50)** | **`5.08 µs`** | In-memory adjacency list walk |
| **95th Percentile Latency (p95)** | **`16.35 µs`** | Full DAG reachability resolution |

---

## 3. Statistical Anomaly Detection Latency

| Monitor Type | Evaluation Latency (µs) | Methodology |
| :--- | :--- | :--- |
| **Freshness Monitor** | **`1.87 µs`** | $O(1)$ SLA delta threshold comparison |
| **Volume Anomaly Detector** | **`13.92 µs`** | Rolling 3-sigma Z-score on 30-day window |
| **Distribution Drift Detector** | **`558.81 µs`** | Kolmogorov-Smirnov test + 10-decile PSI |

---

## Reproduce Benchmarks

```bash
python scripts/run_observability_benchmarks.py
```
