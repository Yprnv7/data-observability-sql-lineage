"""Downstream blast radius and impact analysis for corrupted or missing data columns."""

from __future__ import annotations

import collections

from src.lineage.models import BlastRadiusResult, LineageGraph, SeverityLevel


class BlastRadiusAnalyzer:
    """Calculates the transitive downstream blast radius when a data node suffers an anomaly."""

    @staticmethod
    def calculate_blast_radius(graph: LineageGraph, corrupted_fqdn: str) -> BlastRadiusResult:
        # Build adjacency list: source_fqdn -> list[target_fqdn]
        adjacency: dict[str, list[str]] = collections.defaultdict(list)
        for edge in graph.edges:
            adjacency[edge.source_fqdn].append(edge.target_fqdn)

        visited: set[str] = set()
        queue: collections.deque[tuple[str, int]] = collections.deque([(corrupted_fqdn, 0)])
        max_depth = 0

        while queue:
            current, depth = queue.popleft()
            max_depth = max(max_depth, depth)

            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

        # Extract impacted tables
        impacted_columns = sorted(visited)
        impacted_tables = sorted({col.split(".")[0] for col in impacted_columns if "." in col})

        # Calculate severity based on downstream blast radius breadth
        if len(impacted_tables) >= 3 or any("finance" in t.lower() or "exec" in t.lower() for t in impacted_tables):
            severity = SeverityLevel.CRITICAL
        elif len(impacted_tables) >= 2:
            severity = SeverityLevel.HIGH
        elif len(impacted_columns) >= 1:
            severity = SeverityLevel.MEDIUM
        else:
            severity = SeverityLevel.LOW

        return BlastRadiusResult(
            corrupted_node=corrupted_fqdn,
            impacted_columns=impacted_columns,
            impacted_tables=impacted_tables,
            max_depth=max_depth,
            severity=severity,
        )
