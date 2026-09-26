"""Dynamic clarification options builder derived strictly from database schema and metadata."""
from typing import Any
from db.connection import Database
from db.schema_inspector import inspect_schema
from model.query_models import StructuredIntent


class ClarificationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def build_clarification(
        self, intent: StructuredIntent, missing_slot: str, schema: dict[str, dict] | None = None, language: str = "en"
    ) -> tuple[str, str, list[Any]]:
        if not schema:
            schema = inspect_schema(self.database)

        field = missing_slot
        is_ta = (language == "ta") or (intent.raw_message and any("\u0b80" <= char <= "\u0bff" for char in intent.raw_message))

        # 0. Missing Operation
        if missing_slot == "operation":
            if is_ta:
                question = "தரவை (data) என்ன செய்ய விரும்புகிறீர்கள்?"
                options = ["தரவைப் பார்க்க (View)", "புதிய தரவைச் சேர்க்க (Add)", "தரவை மாற்ற (Update)", "தரவை நீக்க (Delete)"]
            else:
                question = "What would you like to do with the data?"
                options = ["View data", "Add data", "Update data", "Delete data"]
            return question, field, options

        # Missing Required Column Value
        if missing_slot.startswith("field:"):
            col_name = missing_slot.split(":", 1)[1]
            table = intent.table or "target table"
            if is_ta:
                question = f"{table} அட்டவணையில் இந்த பதிவிற்கு {col_name} என்ன பயன்படுத்தப்பட வேண்டும்?"
            else:
                question = f"What {col_name} should be used for this record in the {table} table?"
            options = []
            return question, field, options

        # 1. Missing Table
        if missing_slot == "table":
            msg_lower = intent.raw_message.lower()
            if is_ta:
                question = f"எந்த அட்டவணையைப் (table) பயன்படுத்தி {intent.operation} செய்ய விரும்புகிறீர்கள்?"
            else:
                if "last" in msg_lower or intent.target == "last row":
                    question = f"Which table should I {intent.operation.lower()} the last row from?"
                else:
                    question = f"Which table would you like to {intent.operation.lower()}?"

            table_names = sorted(list(schema.keys()))
            options = table_names[:10] if len(table_names) > 10 else table_names
            return question, field, options

        # 2. Missing Ordering Definition (for relative terms: last, first, latest, oldest)
        if missing_slot == "ordering_definition":
            table = intent.table or "target table"
            cols = schema.get(table, {}).get("columns", []) if schema else []

            target_name = intent.target or "last row"
            if is_ta:
                question = f"{table} அட்டவணையில் '{target_name}' எதன் மூலம் வரிசைப்படுத்தப்பட வேண்டும்?"
            else:
                question = f"What should '{target_name}' mean for the {table} table?"

            options: list[str] = []
            entity = table[:-1] if table.endswith("s") else table

            # Inspect columns dynamically
            id_col = next((c["name"] for c in cols if c["name"].lower() in ("id", f"{entity.lower()}_id")), None)
            created_col = next((c["name"] for c in cols if any(term in c["name"].lower() for term in ("created", "joined", "timestamp", "date", "inserted"))), None)
            updated_col = next((c["name"] for c in cols if any(term in c["name"].lower() for term in ("updated", "modified"))), None)

            if is_ta:
                if id_col:
                    options.append(f"உயர்ந்த {entity} ID")
                if created_col:
                    options.append("சமீபத்தில் உருவாக்கப்பட்டது")
                if updated_col:
                    options.append("சமீபத்தில் புதுப்பிக்கப்பட்டது")
            else:
                if id_col:
                    options.append(f"Highest {entity} ID")
                if created_col:
                    options.append("Most recently created")
                if updated_col:
                    options.append("Most recently updated")

            # Fallback numeric/date columns in table
            if len(options) < 2:
                for c in cols:
                    c_name = c["name"]
                    c_type = c.get("type", "").upper()
                    if any(t in c_type for t in ("INT", "REAL", "FLOAT", "NUMERIC", "DATE", "TIME")) and not any(c_name in opt for opt in options):
                        options.append(f"Sort by {c_name} descending")

            if not options and cols:
                first_col = cols[0]["name"]
                options.append(f"Sort by {first_col} descending")

            if not options:
                options = ["Default schema ordering"]

            return question, field, options

        # 3. Missing Metric (for subjective terms: best, top, sales, popular, etc.)
        if missing_slot == "metric":
            target = intent.target or "items"
            table = intent.table

            if is_ta:
                question = f"'{target}' எதன் மூலம் கணக்கிடப்பட வேண்டும்?"
            else:
                question = f"What metric defines '{target}'?"
            options: list[str] = []

            if table and table in schema:
                cols = schema[table].get("columns", [])
                for c in cols:
                    c_name = c["name"]
                    c_type = c.get("type", "").upper()
                    if any(t in c_type for t in ("INT", "REAL", "FLOAT", "NUMERIC", "DOUBLE")):
                        if c_name.lower() not in ("id",):
                            options.append(f"Highest {c_name}")

                # Inspect foreign key relationships pointing to table
                for rel_table, rel_meta in schema.items():
                    for fk in rel_meta.get("foreign_keys", []):
                        if fk.get("foreign_table") == table:
                            # Related table found! Inspect numeric columns in related table
                            for r_col in rel_meta.get("columns", []):
                                r_type = r_col.get("type", "").upper()
                                if any(t in r_type for t in ("INT", "REAL", "FLOAT", "NUMERIC")) and r_col["name"].lower() not in ("id", fk["column"].lower()):
                                    options.append(f"Highest total {r_col['name']}")
                                    options.append(f"Most {rel_table}")
                                    options.append(f"Most recent {rel_table}")
                                    break

            # Fallback: search schema for numeric or revenue/spending/amount fields
            if not options:
                for t_name, t_meta in schema.items():
                    for c in t_meta.get("columns", []):
                        c_name = c["name"]
                        if any(term in c_name.lower() for term in ("total", "amount", "price", "salary", "revenue", "count")):
                            options.append(f"Highest total {c_name}")

            if not options:
                for t_name, t_meta in schema.items():
                    num_col = next((c["name"] for c in t_meta.get("columns", []) if any(t in c.get("type", "").upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC")) and c["name"].lower() not in ("id",)), None)
                    if num_col:
                        options.append(f"Highest {num_col}")
                    options.append(f"Most {t_name}")

            if not options:
                options = ["Highest value", "Most records", "Most recent activity"]

            seen = set()
            deduped = [opt for opt in options if not (opt in seen or seen.add(opt))]
            return question, field, deduped[:5]

        # 4. Missing Filter Definition
        if missing_slot == "filter_definition":
            target = intent.target or "records"
            table = intent.table or "table"
            target_display = "records" if (not target or target.lower() == table.lower() or target.lower() == f"{table.lower()} table") else target
            if is_ta:
                question = f"{table} அட்டவணையில் '{target_display}' எந்த நிபந்தனை மூலம் வடிகட்டப்பட வேண்டும்?"
            else:
                question = f"How should '{target_display}' be defined for the {table} table?"
            cols = schema.get(table, {}).get("columns", []) if schema and table in schema else []

            options = []
            status_col = next((c["name"] for c in cols if any(term in c["name"].lower() for term in ("status", "active", "state"))), None)
            if status_col:
                options.append(f"WHERE {status_col} = 'inactive'")
                options.append(f"WHERE {status_col} = 'active'")

            date_col = next((c["name"] for c in cols if any(term in c["name"].lower() for term in ("date", "created", "joined"))), None)
            if date_col:
                options.append(f"Oldest records by {date_col}")

            if not options:
                options = ["Filtered by condition", "All matching records"]

            return question, field, options

        if is_ta:
            return f"விடுபட்ட விவரத்தை ({missing_slot}) தெளிவுபடுத்தவும்.", field, ["விருப்பம் 1", "விருப்பம் 2"]
        return f"Could you clarify the missing information ({missing_slot})?", field, ["Option 1", "Option 2"]

    def generate_options(self, term: str, schema: dict[str, dict] | None = None) -> tuple[str, list[str]]:
        intent = StructuredIntent(operation="SELECT", target=term, raw_message=term)
        q, f, opts = self.build_clarification(intent, "metric", schema)
        return q, [str(o) for o in opts]


