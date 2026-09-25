"""Result explanation service strictly bound to factual query result data."""
from typing import Any


class ResultService:
    def explain(self, rows: list[dict[str, Any]], user_message: str | None = None) -> str | None:
        if not rows:
            return "No matching records were found in the database."

        if len(rows) == 1:
            row = rows[0]
            if len(row) == 1:
                col, val = next(iter(row.items()))
                return f"The result for {col} is {val}."
            
            # Formulate single row sentence
            parts = [f"{k}: {v}" for k, v in row.items() if v is not None]
            return f"Found 1 record: {', '.join(parts)}."

        # Aggregate or multi-row summary
        first_row = rows[0]
        # Check if query was asking for highest/top value
        if user_message and any(w in user_message.lower() for w in ("highest", "top", "best", "max")):
            name_col = next((k for k, v in first_row.items() if isinstance(v, str)), None)
            val_col = next((k for k, v in first_row.items() if isinstance(v, (int, float))), None)
            if name_col and val_col:
                return f"{first_row[name_col]} has the highest {val_col.replace('_', ' ')} at {first_row[val_col]:,}."

        return f"Query returned {len(rows)} matching record(s)."
