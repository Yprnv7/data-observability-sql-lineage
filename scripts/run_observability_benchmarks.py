"""Benchmark suite for column-level SQL lineage, blast radius traversal, and anomaly detection."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.lineage.blast_radius import BlastRadiusAnalyzer
from src.lineage.models import LineageGraph
from src.lineage.sql_lineage import SQLLineageParser
from src.monitors.anomaly_detector import AnomalyDetector


def get_hardware_info() -> dict[str, str]:
    cpu_model = platform.processor() or "Unknown"
    if platform.system() == "Darwin":
        try:
            res = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                check=False,
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip():
                cpu_model = res.stdout.strip()
        except OSError:
            pass

    mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    ram_gb = round(mem_bytes / (1024**3), 1)

    return {
        "cpu": cpu_model,
        "ram_gb": str(ram_gb),
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
    }


def benchmark_sql_lineage_parsing(num_queries: int = 100) -> dict[str, Any]:
    parser = SQLLineageParser()
    sql_template = """
    WITH filtered_{i} AS (
        SELECT id, customer_id, base_price * 1.15 AS gross_price, tax
        FROM raw_orders_{i}
        WHERE status = 'ACTIVE'
    )
    SELECT
        f.customer_id,
        c.email,
        SUM(f.gross_price) AS total_spent,
        AVG(f.tax) AS avg_tax
    FROM dim_customers_{i} c
    JOIN filtered_{i} f ON c.customer_id = f.customer_id
    GROUP BY f.customer_id, c.email
    """

    latencies: list[float] = []
    dag = LineageGraph()

    for i in range(num_queries):
        query = sql_template.format(i=i % 10)
        start = time.perf_counter()
        dag = parser.parse_query(query, target_table=f"mrt_summary_{i % 10}", graph=dag)
        lat = (time.perf_counter() - start) * 1000.0
        latencies.append(lat)

    lat_arr = np.array(latencies)
    return {
        "queries_parsed": num_queries,
        "total_nodes_generated": len(dag.nodes),
        "total_edges_generated": len(dag.edges),
        "p50_latency_ms": round(float(np.percentile(lat_arr, 50)), 3),
        "p95_latency_ms": round(float(np.percentile(lat_arr, 95)), 3),
        "mean_latency_ms": round(float(np.mean(lat_arr)), 3),
        "throughput_queries_per_sec": round(num_queries / (float(np.sum(lat_arr)) / 1000.0), 1),
    }


def benchmark_blast_radius_traversal(dag_depth: int = 20, num_lookups: int = 200) -> dict[str, Any]:
    parser = SQLLineageParser()
    dag = LineageGraph()

    # Build deep pipeline: stage 0 -> stage 1 -> ... -> stage 20
    for i in range(dag_depth):
        sql = f"SELECT prev_col * 2 AS next_col_{i+1} FROM stage_{i}"
        dag = parser.parse_query(sql, target_table=f"stage_{i+1}", graph=dag)

    latencies_us: list[float] = []
    for _ in range(num_lookups):
        start = time.perf_counter()
        res = BlastRadiusAnalyzer.calculate_blast_radius(dag, "stage_0.prev_col")
        lat = (time.perf_counter() - start) * 1_000_000.0
        latencies_us.append(lat)

    lat_arr = np.array(latencies_us)
    return {
        "pipeline_depth": dag_depth,
        "nodes_impacted": len(res.impacted_columns),
        "p50_traversal_us": round(float(np.percentile(lat_arr, 50)), 2),
        "p95_traversal_us": round(float(np.percentile(lat_arr, 95)), 2),
        "mean_traversal_us": round(float(np.mean(lat_arr)), 2),
    }


def benchmark_anomaly_monitors() -> dict[str, Any]:
    np.random.seed(42)
    history = [10000 + int(x) for x in np.random.normal(0, 100, 30)]

    # 1. Volume benchmark
    v_start = time.perf_counter()
    for _ in range(200):
        AnomalyDetector.evaluate_volume("fct_orders", 10050, history)
    vol_latency_us = ((time.perf_counter() - v_start) / 200.0) * 1_000_000.0

    # 2. Freshness benchmark
    f_start = time.perf_counter()
    for _ in range(200):
        AnomalyDetector.evaluate_freshness("fct_orders", 1000.0, 500.0, 1200.0)
    fresh_latency_us = ((time.perf_counter() - f_start) / 200.0) * 1_000_000.0

    # 3. Distribution Drift benchmark (PSI + KS)
    b_vals = list(np.random.normal(100, 15, 500))
    c_vals = list(np.random.normal(105, 16, 500))
    d_start = time.perf_counter()
    for _ in range(50):
        AnomalyDetector.evaluate_distribution_drift("fct_orders", "amount", b_vals, c_vals)
    drift_latency_us = ((time.perf_counter() - d_start) / 50.0) * 1_000_000.0

    return {
        "volume_eval_us": round(vol_latency_us, 2),
        "freshness_eval_us": round(fresh_latency_us, 2),
        "distribution_drift_eval_us": round(drift_latency_us, 2),
    }


def main() -> None:
    hw = get_hardware_info()
    lineage_res = benchmark_sql_lineage_parsing()
    blast_res = benchmark_blast_radius_traversal()
    anomaly_res = benchmark_anomaly_monitors()

    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "hardware": hw,
        "lineage_parsing": lineage_res,
        "blast_radius": blast_res,
        "anomaly_monitors": anomaly_res,
    }

    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "observability_benchmark.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    md_content = f"""# Data Observability & SQL Lineage Benchmark Results

- **Evaluation Date:** {data['timestamp'][:10]}
- **Hardware Platform:** {hw['cpu']} ({hw['ram_gb']} GB RAM)
- **Operating System:** {hw['os']}
- **Python Version:** {hw['python_version']}

---

## 1. Column-Level SQL Lineage Parsing Throughput

| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Queries Parsed** | `{lineage_res['queries_parsed']}` complex queries | CTEs, joins, aggregations, aliases |
| **Graph Generated** | `{lineage_res['total_nodes_generated']}` nodes, `{lineage_res['total_edges_generated']}` edges | Unified column-level DAG |
| **Parsing Throughput** | **`{lineage_res['throughput_queries_per_sec']:,} queries/sec`** | sqlglot AST column dependency extraction |
| **Median Latency (p50)** | **`{lineage_res['p50_latency_ms']} ms`** | Query-to-graph projection |
| **95th Percentile Latency (p95)** | **`{lineage_res['p95_latency_ms']} ms`** | Deep CTE expression traversal |

---

## 2. Downstream Blast Radius Traversal Latency

| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Pipeline Depth** | `{blast_res['pipeline_depth']}` consecutive hops | Staging to executive analytical marts |
| **Impacted Nodes Resolved** | `{blast_res['nodes_impacted']}` column dependencies | Transitive forward BFS graph walk |
| **Median Traversal Latency (p50)** | **`{blast_res['p50_traversal_us']} µs`** | In-memory adjacency list walk |
| **95th Percentile Latency (p95)** | **`{blast_res['p95_traversal_us']} µs`** | Full DAG reachability resolution |

---

## 3. Statistical Anomaly Detection Latency

| Monitor Type | Evaluation Latency (µs) | Methodology |
| :--- | :--- | :--- |
| **Freshness Monitor** | **`{anomaly_res['freshness_eval_us']} µs`** | $O(1)$ SLA delta threshold comparison |
| **Volume Anomaly Detector** | **`{anomaly_res['volume_eval_us']} µs`** | Rolling 3-sigma Z-score on 30-day window |
| **Distribution Drift Detector** | **`{anomaly_res['distribution_drift_eval_us']} µs`** | Kolmogorov-Smirnov test + 10-decile PSI |

---

## Reproduce Benchmarks

```bash
python scripts/run_observability_benchmarks.py
```
"""
    with open("docs/BENCHMARKS.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    print("Observability benchmark complete:")
    print(f"  Lineage Parsing: {lineage_res['p50_latency_ms']} ms p50 ({lineage_res['throughput_queries_per_sec']:,} queries/sec)")
    print(f"  Blast Radius Traversal: {blast_res['p50_traversal_us']} us p50 ({blast_res['nodes_impacted']} nodes)")
    print(f"  Volume Monitor: {anomaly_res['volume_eval_us']} us | Drift Monitor: {anomaly_res['distribution_drift_eval_us']} us")


if __name__ == "__main__":
    main()
