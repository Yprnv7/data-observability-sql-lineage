"""Column-level SQL lineage parser leveraging sqlglot AST traversal."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from src.lineage.models import (
    ColumnNode,
    LineageEdge,
    LineageGraph,
    TransformationType,
)


class SQLLineageParser:
    """Parses SQL queries into a column-level directed acyclic lineage graph."""

    def __init__(self, dialect: str = "duckdb") -> None:
        self.dialect = dialect

    def parse_query(
        self,
        sql: str,
        target_table: str = "target_table",
        graph: LineageGraph | None = None,
    ) -> LineageGraph:
        dag = graph or LineageGraph()
        parsed = sqlglot.parse_one(sql, read=self.dialect)

        # Detect target table from CREATE TABLE or INSERT INTO if present
        if isinstance(parsed, exp.Create) and parsed.this or isinstance(parsed, exp.Insert) and parsed.this:
            target_table = parsed.this.name

        # Extract source tables from FROM and JOIN
        source_tables: set[str] = set()
        for from_exp in parsed.find_all(exp.From):
            if from_exp.this and isinstance(from_exp.this, exp.Table):
                source_tables.add(from_exp.this.name)
        for join_exp in parsed.find_all(exp.Join):
            if join_exp.this and isinstance(join_exp.this, exp.Table):
                source_tables.add(join_exp.this.name)

        if not source_tables:
            source_tables.add("source_table")

        default_source_table = min(source_tables)

        # Process SELECT projections
        for select_exp in parsed.find_all(exp.Select):
            for item in select_exp.expressions:
                # Determine output column name
                if isinstance(item, exp.Alias):
                    out_col = item.alias
                    expr_ast = item.this
                elif isinstance(item, exp.Column):
                    out_col = item.name
                    expr_ast = item
                else:
                    out_col = item.alias_or_name
                    expr_ast = item

                target_fqdn = f"{target_table}.{out_col}"
                target_node = ColumnNode(
                    table_name=target_table,
                    column_name=out_col,
                    fqdn=target_fqdn,
                    expression=str(item),
                    is_source=False,
                )
                dag.nodes[target_fqdn] = target_node

                # Classify transformation type
                t_type = TransformationType.DIRECT
                if any(isinstance(node, (exp.Sum, exp.Count, exp.Avg, exp.Min, exp.Max)) for node in expr_ast.walk()):
                    t_type = TransformationType.AGGREGATION
                elif any(isinstance(node, (exp.Binary, exp.Case, exp.Func)) for node in expr_ast.walk()):
                    t_type = TransformationType.EXPRESSION

                # Extract referenced source columns
                source_cols = list(expr_ast.find_all(exp.Column))
                if source_cols:
                    for s_col in source_cols:
                        s_table = s_col.table or default_source_table
                        s_name = s_col.name
                        s_fqdn = f"{s_table}.{s_name}"

                        if s_fqdn not in dag.nodes:
                            dag.nodes[s_fqdn] = ColumnNode(
                                table_name=s_table,
                                column_name=s_name,
                                fqdn=s_fqdn,
                                is_source=True,
                            )

                        edge = LineageEdge(
                            source_fqdn=s_fqdn,
                            target_fqdn=target_fqdn,
                            transformation_type=t_type,
                        )
                        dag.edges.append(edge)
                else:
                    # Literal or expression without direct column reference
                    pass

        # Update tables list
        all_tables = {n.table_name for n in dag.nodes.values()}
        dag.tables = sorted(all_tables)

        return dag
