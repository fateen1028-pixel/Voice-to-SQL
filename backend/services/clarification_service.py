"""Dynamic clarification options builder derived from database schema and business terms."""
from db.connection import Database
from db.schema_inspector import inspect_schema


class ClarificationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def generate_options(self, term: str, schema: dict[str, dict] | None = None) -> tuple[str, list[str]]:
        if not schema:
            schema = inspect_schema(self.database)

        normalized = term.lower()

        if "customer" in normalized or "best" in normalized:
            options = []
            # Check for revenue/spending/total fields in orders table
            if "orders" in schema or "sales" in schema:
                options.append("Highest total spending")
                options.append("Most orders")
                options.append("Most recent purchases")
            else:
                options.append("Highest total spending")
                options.append("Most active")
                options.append("Oldest account")
            return "What do you mean by 'best customers'?", options

        if "sales" in normalized:
            return "What would you like to see for sales?", [
                "Total revenue",
                "Number of orders",
                "Units sold",
            ]

        if "performance" in normalized:
            return "What dimension of performance would you like to evaluate?", [
                "Total revenue generated",
                "Number of completed transactions",
                "Customer satisfaction / activity",
            ]

        return f"Could you clarify what you mean by '{term}'?", [
            f"Option A related to {term}",
            f"Option B related to {term}",
        ]
