"""Result explanation service strictly bound to factual query result data."""
from typing import Any


class ResultService:
    def explain(self, rows: list[dict[str, Any]], user_message: str | None = None, language: str = "en") -> str | None:
        is_ta = (language == "ta") or (user_message and any("\u0b80" <= char <= "\u0bff" for char in user_message))

        if not rows:
            if is_ta:
                return "தரவுத்தளத்தில் பொருத்தமான பதிவுகள் எதுவும் கிடைக்கவில்லை."
            return "No matching records were found in the database."

        if len(rows) == 1:
            row = rows[0]
            if len(row) == 1:
                col, val = next(iter(row.items()))
                if is_ta:
                    return f"{col} க்கான முடிவு: {val}."
                return f"The result for {col} is {val}."

            # Formulate single row sentence
            parts = [f"{k}: {v}" for k, v in row.items() if v is not None]
            if is_ta:
                return f"1 பதிவு கண்டறியப்பட்டது: {', '.join(parts)}."
            return f"Found 1 record: {', '.join(parts)}."

        # Aggregate or multi-row summary
        first_row = rows[0]
        # Check if query was asking for highest/top value
        if user_message and any(w in user_message.lower() for w in ("highest", "top", "best", "max", "உயர்ந்த", "அதிகபட்ச")):
            name_col = next((k for k, v in first_row.items() if isinstance(v, str)), None)
            val_col = next((k for k, v in first_row.items() if isinstance(v, (int, float))), None)
            if name_col and val_col:
                if is_ta:
                    return f"{first_row[name_col]} மிக உயர்ந்த {val_col.replace('_', ' ')} கொண்டுள்ளது ({first_row[val_col]:,})."
                return f"{first_row[name_col]} has the highest {val_col.replace('_', ' ')} at {first_row[val_col]:,}."

        if is_ta:
            return f"வினவல் {len(rows)} பொருத்தமான பதிவுகளை வழங்கியுள்ளது."
        return f"Query returned {len(rows)} matching record(s)."
