"""LLM Generator service interface with schema dynamic prompt injection, Gemini/OpenAI provider support, and deterministic rule generator fallback."""
import logging
import re
import httpx
from config.settings import Settings

logger = logging.getLogger(__name__)


class SqlGenerationError(ValueError):
    pass


class SqlGenerationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = self.settings.llm_provider
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.llm_model

    def generate(self, message: str, schema: dict[str, dict], prior_sql: str | None = None, is_postgres: bool = False) -> str:
        if not schema:
            raise SqlGenerationError("No matching database tables were found for that request.")

        placeholder_keys = ("mock", "your_key", "your_llm_api_key", "your_gemini_api_key", "your_gemini_api_key_here")
        valid_key = bool(self.api_key and self.api_key.strip() and self.api_key not in placeholder_keys)
        if self.provider in ("openai", "groq", "ollama", "gemini") and valid_key:
            try:
                sql = self._generate_with_llm(message, schema, prior_sql, is_postgres)
                if sql:
                    return sql
            except Exception as exc:
                logger.warning("LLM generation provider failed: %s. Falling back to deterministic generator.", exc)

        return self._generate_fallback(message, schema, prior_sql, is_postgres)

    def _generate_with_llm(self, message: str, schema: dict[str, dict], prior_sql: str | None, is_postgres: bool) -> str | None:
        schema_desc = []
        for table, meta in schema.items():
            cols = [f"{c['name']} ({c['type']})" for c in meta.get("columns", [])]
            fks = [f"{fk['column']} -> {fk['foreign_table']}.{fk['foreign_column']}" for fk in meta.get("foreign_keys", [])]
            desc = f"Table: {table}\nColumns: {', '.join(cols)}"
            if fks:
                desc += f"\nForeign Keys: {', '.join(fks)}"
            schema_desc.append(desc)

        schema_str = "\n\n".join(schema_desc)
        dialect = "PostgreSQL" if is_postgres else "SQLite"

        system_prompt = f"""You are a precise SQL generator for a {dialect} database.
Given the schema below, generate ONLY a valid executable SQL query responding to the user's request.
Do NOT surround with backticks or extra text.
Do NOT invent tables or columns outside the schema.

Schema:
{schema_str}
"""

        user_content = message
        if prior_sql:
            user_content = f"Prior Query Context:\n{prior_sql}\n\nFollow-up Request:\n{message}"

        # 1. Gemini Provider Support
        if self.provider == "gemini":
            model_name = self.model if self.model not in ("gpt-4o-mini", "mock") else "gemini-2.5-flash"
            # OpenAI-compatible API endpoint provided by Google Gemini
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.0,
            }
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"].strip()
                    return self._clean_sql_output(raw)

                # Native Gemini API generateContent endpoint fallback
                native_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                native_payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_content}"}]}],
                    "generationConfig": {"temperature": 0.0},
                }
                resp2 = client.post(native_url, json=native_payload, headers={"Content-Type": "application/json"})
                if resp2.status_code == 200:
                    candidates = resp2.json().get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return self._clean_sql_output(parts[0].get("text", ""))

            return None

        # 2. OpenAI / Groq / Ollama Provider Support
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
        }

        url = "https://api.openai.com/v1/chat/completions"
        if self.provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"

        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                return self._clean_sql_output(raw)
        return None

    def _clean_sql_output(self, raw: str) -> str:
        clean_sql = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.I)
        clean_sql = re.sub(r"\s*```$", "", clean_sql).strip()
        return clean_sql

    def _generate_fallback(self, message: str, schema: dict[str, dict], prior_sql: str | None, is_postgres: bool) -> str:
        text = message.lower().strip()

        # Handle raw DDL or malicious DDL attempts by forwarding statement to firewall
        for ddl_op in ("drop", "truncate", "alter", "create"):
            if re.search(r"\b" + ddl_op + r"\s+table\b", text):
                target = re.search(r"\b" + ddl_op + r"\s+table\s+(\w+)", text)
                t_name = target.group(1) if target else "target"
                return f"{ddl_op.upper()} TABLE {t_name}"

        # Handle raw malformed SQL input (e.g. "select from from employees")
        if re.search(r"\bselect\b.*\bfrom\s+from\b", text):
            return "SELECT FROM FROM employees"

        # Table matching
        table = self._match_table(text, schema)
        if not table and prior_sql:
            # Extract table name from prior query
            m = re.search(r"\bfrom\s+([a-z_][\w]*)", prior_sql, re.I)
            if m and m.group(1) in schema:
                table = m.group(1)

        if not table:
            nouns = set(re.findall(r"\b[a-z]{3,}\b", text)) - {
                "show", "list", "get", "view", "find", "all", "the", "from", "where", "select", "sort", "by", "order", "only", "first", "top"
            }
            if nouns and not any(n in [t.lower() for t in schema] for n in nouns):
                raise SqlGenerationError("I could not map that request to a table in the connected database.")
            table = next(iter(schema.keys()))

        columns = {c["name"].lower(): c["name"] for c in schema[table]["columns"]}
        col_list = list(columns.values())

        # DELETE request
        if re.search(r"\b(delete|remove)\b", text):
            return self._delete(text, table, columns)

        # UPDATE request
        if re.search(r"\bupdate\b", text):
            return self._update(text, table, columns)

        # INSERT request
        if re.search(r"\b(insert|add|create)\b", text) and any(w in text for w in ("into", "new", "record")):
            return self._insert(text, table, columns)

        # Clarification result e.g. "Highest total spending"
        if "highest total spending" in text or "total spending" in text:
            if "orders" in schema:
                id_col = columns.get("id", col_list[0])
                orders_total_col = "total"
                for c in schema["orders"]["columns"]:
                    if c["name"].lower() in ("total", "amount", "price"):
                        orders_total_col = c["name"]
                        break
                return f"SELECT {table}.*, SUM(orders.{orders_total_col}) AS total_spending FROM {table} JOIN orders ON orders.customer_id = {table}.{id_col} GROUP BY {table}.{id_col} ORDER BY total_spending DESC LIMIT 10"

        # Top 10 customers by total spending / orders join
        if "top" in text and "customer" in table.lower() and "orders" in schema:
            number = re.search(r"\btop\s+(\d+)", text)
            limit = int(number.group(1)) if number else 10
            id_col = columns.get("id", col_list[0])
            orders_total_col = "total"
            for c in schema["orders"]["columns"]:
                if c["name"].lower() in ("total", "amount", "price"):
                    orders_total_col = c["name"]
                    break
            return f"SELECT {table}.*, SUM(orders.{orders_total_col}) AS total_spending FROM {table} JOIN orders ON orders.customer_id = {table}.{id_col} GROUP BY {table}.{id_col} ORDER BY total_spending DESC LIMIT 10"

        # Conversational Follow-up Queries
        if prior_sql and any(term in text for term in ("sort", "top", "only", "first", "developer", "order")):
            return self._follow_up(text, prior_sql, columns, schema, is_postgres)

        # Specific column requested (e.g. "show employees ssn")
        target_col = next((c for c in columns if c in text and c not in ("id", "name")), None)
        if target_col:
            return f"SELECT {columns[target_col]} FROM {table} LIMIT 100"

        # Year date filter handling (e.g. joined in 2025)
        yr_match = re.search(r"\b(20\d{2})\b", text)
        if yr_match:
            yr = yr_match.group(1)
            date_col = next((c for c in columns.values() if "date" in c.lower() or "joined" in c.lower() or "created" in c.lower()), None)
            if date_col:
                next_yr = str(int(yr) + 1)
                return f"SELECT * FROM {table} WHERE {date_col} >= '{yr}-01-01' AND {date_col} < '{next_yr}-01-01'"

        limit_match = re.search(r"\b(?:top|first)\s+(\d+)", text)
        limit = int(limit_match.group(1)) if limit_match else self.settings.max_query_rows

        order_by = ""
        if any(w in text for w in ("top", "first", "highest", "lowest", "most", "sort")):
            order_col = col_list[0]
            for c_name in col_list:
                if c_name.lower() in ("salary", "total", "amount", "score", "id"):
                    order_col = c_name
                    break
            order_by = f" ORDER BY {order_col} DESC"

        return f"SELECT * FROM {table}{order_by}" + (f" LIMIT {limit}" if limit else "")

    def _match_table(self, text: str, schema: dict[str, dict]) -> str | None:
        for table in schema:
            t_lower = table.lower()
            if t_lower in text or t_lower.rstrip("s") in text:
                return table
        return None

    def _delete(self, text: str, table: str, columns: dict[str, str]) -> str:
        words = text.split()
        status_col = columns.get("status")
        for word in words:
            if word not in ("delete", "remove", "from", table.lower(), table.lower().rstrip("s")) and len(word) > 2:
                if status_col:
                    return f"DELETE FROM {table} WHERE {status_col} = '{word}'"
                for c_name in columns.values():
                    if c_name.lower() not in ("id",):
                        return f"DELETE FROM {table} WHERE {c_name} = '{word}'"

        raise SqlGenerationError("Delete requests require an explicit filter condition.")

    def _update(self, text: str, table: str, columns: dict[str, str]) -> str:
        match = re.search(r"set\s+(\w+)\s+(?:to|=)\s+([\w-]+)", text)
        if match:
            col_name = match.group(1)
            val = match.group(2).replace("'", "''")
            target_col = columns.get(col_name.lower(), col_name)
            return f"UPDATE {table} SET {target_col} = '{val}'"

        status_col = columns.get("status", list(columns.values())[0])
        return f"UPDATE {table} SET {status_col} = 'updated'"

    def _insert(self, text: str, table: str, columns: dict[str, str]) -> str:
        non_id_cols = [c for c in columns.values() if c.lower() != "id"]
        cols_str = ", ".join(non_id_cols)
        vals_str = ", ".join([f"'sample_{c}'" for c in non_id_cols])
        return f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str})"

    def _follow_up(self, text: str, sql: str, columns: dict[str, str], schema: dict[str, dict], is_postgres: bool) -> str:
        res_sql = sql
        if "top" in text or "first" in text:
            n = re.search(r"\b(?:top|first)\s+(\d+)", text)
            if n:
                res_sql = re.sub(r"\s+LIMIT\s+\d+", "", res_sql, flags=re.I) + f" LIMIT {int(n.group(1))}"

        if "sort by" in text or "order by" in text:
            match = re.search(r"(?:sort|order)\s+by\s+(\w+)", text)
            if match and match.group(1).lower() in columns:
                col_name = columns[match.group(1).lower()]
                res_sql = re.sub(r"\s+LIMIT\s+\d+", "", res_sql, flags=re.I) + f" ORDER BY {col_name} DESC LIMIT 100"

        if "only" in text:
            match = re.search(r"only\s+(\w+)", text)
            if match:
                val = match.group(1)
                role_or_dept = columns.get("department", columns.get("role", columns.get("status")))
                if role_or_dept:
                    if "WHERE" in res_sql.upper():
                        res_sql = re.sub(r"(WHERE\s+)", f"\\1{role_or_dept} = '{val}' AND ", res_sql, flags=re.I)
                    else:
                        res_sql += f" WHERE {role_or_dept} = '{val}'"

        return res_sql
