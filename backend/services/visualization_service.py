"""Automatic result set visualization recommendation service."""
from typing import Any


class VisualizationService:
    def recommend(self, columns: list[str], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows or len(rows) < 2:
            if rows and len(rows) == 1 and len(rows[0]) == 1:
                col, val = next(iter(rows[0].items()))
                if isinstance(val, (int, float)):
                    return {"type": "kpi", "metric": col, "value": val}
            return None

        # Find category column (string/date) and numeric column (int/float)
        sample = rows[0]
        # Exclude ID columns from numeric chart metrics (id, customer_id, department_id, etc.)
        numeric_cols = [
            c for c in columns
            if isinstance(sample.get(c), (int, float))
            and c.lower() != "id"
            and not c.lower().endswith("_id")
        ]
        category_cols = [c for c in columns if isinstance(sample.get(c), str) and c.lower() != "id" and not c.lower().endswith("_id")]
        date_cols = [c for c in category_cols if any(d_kw in c.lower() for d_kw in ("date", "year", "month", "day", "created", "time"))]

        if not numeric_cols:
            return {"type": "table"}

        num_col = numeric_cols[0]

        if date_cols:
            return {
                "type": "line",
                "x_axis": date_cols[0],
                "y_axis": num_col,
                "title": f"{num_col.replace('_', ' ').title()} Over Time",
            }

        if category_cols:
            cat_col = category_cols[0]
            if len(rows) <= 5:
                return {
                    "type": "pie",
                    "category": cat_col,
                    "value": num_col,
                    "title": f"Distribution of {num_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                }
            return {
                "type": "bar",
                "x_axis": cat_col,
                "y_axis": num_col,
                "title": f"{num_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
            }

        return {"type": "table"}
