import logging
import re
from typing import Any
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

    def generate(
        self,
        message: str,
        schema: dict[str, dict],
        prior_sql: str | None = None,
        is_postgres: bool = False,
        intent: Any | None = None,
    ) -> str:
        if not schema:
            raise SqlGenerationError("No matching database tables were found for that request.")

        if intent and hasattr(intent, "is_complete") and not intent.is_complete:
            raise SqlGenerationError("Cannot generate SQL for incomplete natural language intent.")

        placeholder_keys = ("mock", "your_key", "your_llm_api_key", "your_gemini_api_key", "your_gemini_api_key_here")
        valid_key = bool(self.api_key and self.api_key.strip() and self.api_key not in placeholder_keys)
        if self.provider == "sample-model":
            try:
                sql = self._generate_with_sample_model(message, schema)
                if sql:
                    return sql
            except Exception as exc:
                logger.warning("sample-model provider failed: %s. Falling back to deterministic generator.", exc)
        elif self.provider in ("openai", "groq", "ollama", "gemini") and valid_key:
            try:
                sql = self._generate_with_llm(message, schema, prior_sql, is_postgres, intent=intent)
                if sql:
                    return sql
            except Exception as exc:
                logger.warning("LLM generation provider failed: %s. Falling back to deterministic generator.", exc)

        return self._generate_fallback(message, schema, prior_sql, is_postgres, intent)

    def _generate_with_sample_model(self, message: str, schema: dict[str, dict]) -> str | None:
        import sys
        from pathlib import Path
        sample_model_dir = Path(__file__).resolve().parents[2] / "sample-model"
        ckpt_path = sample_model_dir / "models" / "best.pt"
        if not ckpt_path.exists():
            return None
        if str(sample_model_dir) not in sys.path:
            sys.path.insert(0, str(sample_model_dir))
        try:
            from inference.predict import load_pipeline, predict_one
            schema_lines = []
            for t_name, meta in schema.items():
                cols = []
                for c in meta.get("columns", []):
                    col_desc = f"    {c['name']}: {c.get('type', 'text').lower()}"
                    if c.get("primary_key"):
                        col_desc += " pk"
                    cols.append(col_desc)
                schema_lines.append(f"{t_name}(\n" + ",\n".join(cols) + "\n)")
            schema_text = "\n".join(schema_lines)

            model, cfg, tok = load_pipeline(ckpt_path)
            pred = predict_one(model, cfg, tok, schema_text, message)
            if pred.get("status") == "CLEAR" and pred.get("sql"):
                return pred["sql"]
        except Exception as exc:
            logger.warning("Error running sample-model prediction: %s", exc)
        return None


    def _generate_with_llm(
        self, message: str, schema: dict[str, dict], prior_sql: str | None, is_postgres: bool, intent: Any | None = None
    ) -> str | None:
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
When the request asks for 'top N', 'first N', or best/highest/lowest items, always include an appropriate ORDER BY clause along with LIMIT N.
When a specific year (e.g. 2025) is requested for dates, use explicit upper and lower bounds (e.g., date >= '2025-01-01' AND date < '2026-01-01').
For INSERT queries, ensure all non-nullable columns are supplied with appropriate values to satisfy table constraints.

Schema:
{schema_str}
"""

        user_content = message
        if prior_sql:
            user_content = f"Prior Query Context:\n{prior_sql}\n\nFollow-up Request:\n{message}"

        if intent and hasattr(intent, "operation"):
            system_prompt += f"\nHARD CONSTRAINT: Target Operation = {intent.operation}\n"
            if getattr(intent, "table", None):
                system_prompt += f"HARD CONSTRAINT: Target Table = {intent.table}\n"
            if getattr(intent, "set_columns", None):
                system_prompt += f"HARD CONSTRAINT: Set Columns/Values = {intent.set_columns}\n"
            system_prompt += f"You MUST generate a {intent.operation} statement. Do NOT generate a different SQL operation.\n"

        # 1. Gemini Provider Support
        if self.provider == "gemini":
            candidate_models = [
                self.model,
                "gemini-3.6-flash",
                "gemma-4-26b-a4b-it",
                "gemini-3.1-flash-lite",
            ]
            models: list[str] = []
            for m in candidate_models:
                if m and m not in ("gpt-4o-mini", "mock") and m not in models:
                    models.append(m)

            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                for model_name in models:
                    native_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                    native_payload = {
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_content}"}]}],
                        "generationConfig": {"temperature": 0.0},
                    }
                    try:
                        resp = client.post(native_url, json=native_payload, headers={"Content-Type": "application/json"})
                        if resp.status_code == 200:
                            candidates = resp.json().get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts:
                                    return self._clean_sql_output(parts[0].get("text", ""))
                        logger.warning("Gemini model '%s' returned status %d: %s", model_name, resp.status_code, resp.text[:150])
                    except Exception as exc:
                        logger.warning("Gemini native API call error on '%s': %s", model_name, exc)

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

    def _generate_fallback(
        self, message: str, schema: dict[str, dict], prior_sql: str | None, is_postgres: bool, intent: Any | None = None
    ) -> str:
        text = message.lower().strip()

        # Handle raw DDL or malicious DDL attempts by forwarding statement to firewall
        for ddl_op in ("drop", "truncate", "alter", "create"):
            if re.search(r"\b" + ddl_op + r"\s+table\b", text):
                target = re.search(r"\b" + ddl_op + r"\s+table\s+(\w+)", text)
                t_name = target.group(1) if target else "target"
                return f"{ddl_op.upper()} TABLE {t_name}"

        # Handle raw malformed SQL input (e.g. "select from from employees")
        if re.search(r"\bselect\b.*\bfrom\s+from\b", text):
            t_first = list(schema.keys())[0] if schema else "target"
            return f"SELECT FROM FROM {t_first}"

        # Table matching: intent table first, then text matching, then prior_sql
        table = (intent.table if intent and hasattr(intent, "table") and intent.table else None) or self._match_table(text, schema)
        if not table and prior_sql:
            m = re.search(r"\bfrom\s+([a-z_][\w]*)", prior_sql, re.I)
            if m and m.group(1) in schema:
                table = m.group(1)

        if not table:
            stop_words = {
                "show", "list", "get", "view", "find", "all", "the", "from", "where", "select",
                "sort", "by", "order", "only", "first", "top", "give", "me", "data", "number",
                "information", "details", "record", "records", "with", "and", "that", "have",
            }
            nouns = set(re.findall(r"\b[a-z]{3,}\b", text)) - stop_words
            table_names_lower = [t.lower() for t in schema]
            if nouns and not any(n in table_names_lower or n.rstrip("s") in table_names_lower for n in nouns):
                raise SqlGenerationError("I could not map that request to a table in the connected database.")
            raise SqlGenerationError("Target table is required before SQL generation.")

        columns = {c["name"].lower(): c["name"] for c in schema[table]["columns"]}
        col_list = list(columns.values())

        # Structured Intent Operation Handling
        if intent and hasattr(intent, "operation"):
            if intent.operation == "INSERT":
                return self._insert_intent(intent, table, columns, schema)
            elif intent.operation == "UPDATE":
                return self._update_intent(intent, table, columns, schema)
            elif intent.operation == "DELETE":
                return self._delete_intent(intent, table, columns, col_list)

        # DELETE request
        if re.search(r"\b(delete|remove)\b", text):
            return self._delete(text, table, columns, schema)

        # UPDATE request
        if re.search(r"\bupdate\b", text):
            return self._update(text, table, columns, schema)

        # INSERT request
        if re.search(r"\b(insert|add|create)\b", text) and any(w in text for w in ("into", "new", "record", "customer", "employee", "order")):
            return self._insert(text, table, columns, schema)

        # ID filter for SELECT: "id number N", "id N", "id = N", "record N", "row N"
        id_match = re.search(r"\b(?:id\s*(?:number|=|#|:)?\s*|record\s*|row\s*)(\d+)\b", text)
        pk_col_name = next((c["name"] for c in schema[table]["columns"] if c.get("primary_key") or c["name"].lower() in ("id", f"{table.rstrip('s')}_id")), "id")
        if id_match and pk_col_name.lower() in columns:
            pk_col = columns[pk_col_name.lower()]
            pk_val = id_match.group(1)
            return f"SELECT * FROM {table} WHERE {pk_col} = {pk_val}"

        # Dynamic aggregation/join for clarification selections
        if "highest" in text or "total" in text or "most" in text or "spending" in text:
            numeric_col = next(
                (c["name"] for c in schema[table]["columns"] if any(t in c.get("type", "").upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC")) and c["name"].lower() not in ("id",)),
                None
            )

            rel_join = None
            pk_col = columns.get(pk_col_name.lower(), col_list[0])
            for rel_table, rel_meta in schema.items():
                for fk in rel_meta.get("foreign_keys", []):
                    if fk.get("foreign_table") == table:
                        num_col = next(
                            (c["name"] for c in rel_meta.get("columns", []) if any(t in c.get("type", "").upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC")) and c["name"].lower() not in ("id", fk["column"].lower())),
                            None
                        )
                        if num_col:
                            rel_join = (rel_table, fk["column"], num_col)
                            break
                if rel_join:
                    break

            if rel_join:
                r_table, r_fk_col, r_num_col = rel_join
                return f"SELECT {table}.*, SUM({r_table}.{r_num_col}) AS total_metric FROM {table} JOIN {r_table} ON {r_table}.{r_fk_col} = {table}.{pk_col} GROUP BY {table}.{pk_col} ORDER BY total_metric DESC LIMIT 10"
            elif numeric_col:
                return f"SELECT * FROM {table} ORDER BY {numeric_col} DESC LIMIT 10"

        # Conversational Follow-up Queries
        if prior_sql and any(term in text for term in ("sort", "top", "only", "first", "order") or [c for c in columns if c in text]):
            return self._follow_up(text, prior_sql, columns, schema, is_postgres)

        # Specific column requested (only if no ranking/sorting/top-N requested)
        target_col = next((c for c in columns if c in text and c not in ("id", "name")), None)
        if target_col and not any(w in text for w in ("top", "first", "highest", "lowest", "most", "sort", "by", "order")):
            return f"SELECT {columns[target_col]} FROM {table} LIMIT 100"

        # Year date filter handling
        yr_match = re.search(r"\b(20\d{2})\b", text)
        if yr_match:
            yr = yr_match.group(1)
            date_col = next((c["name"] for c in schema[table]["columns"] if any(term in c["name"].lower() for term in ("date", "created", "joined", "timestamp", "inserted"))), None)
            if date_col:
                next_yr = str(int(yr) + 1)
                return f"SELECT * FROM {table} WHERE {date_col} >= '{yr}-01-01' AND {date_col} < '{next_yr}-01-01'"

        limit_match = re.search(r"\b(?:top|first|latest)\s+(\d+)", text)
        if limit_match:
            limit = int(limit_match.group(1))
        elif any(w in text for w in ("first", "latest", "top 1", "first id", "first record", "first row")):
            limit = 1
        else:
            limit = self.settings.max_query_rows

        order_by = ""
        if any(w in text for w in ("top", "first", "highest", "lowest", "most", "sort", "by")):
            by_match = re.search(r"\bby\s+([a-z0-9_]+)", text)
            if by_match and by_match.group(1).lower() in columns:
                order_col = columns[by_match.group(1).lower()]
            else:
                order_col = next(
                    (c["name"] for c in schema[table]["columns"] if any(t in c.get("type", "").upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC", "DOUBLE")) and c["name"].lower() not in ("id",)),
                    col_list[0]
                )
            order_by = f" ORDER BY {order_col} DESC"

        return f"SELECT * FROM {table}{order_by}" + (f" LIMIT {limit}" if limit else "")

    def _match_table(self, text: str, schema: dict[str, dict]) -> str | None:
        for table in schema:
            t_lower = table.lower()
            if t_lower in text or t_lower.rstrip("s") in text:
                return table
        return None

    def _insert_intent(self, intent: Any, table: str, columns: dict[str, str], schema: dict[str, dict]) -> str:
        if not intent.set_columns:
            return self._insert(intent.raw_message, table, columns, schema)

        col_pairs = []
        val_pairs = []
        for col_key, val in intent.set_columns.items():
            matched_col = columns.get(col_key.lower(), col_key)
            col_pairs.append(matched_col)
            if isinstance(val, (int, float)):
                val_pairs.append(str(val))
            else:
                val_escaped = str(val).replace("'", "''")
                val_pairs.append(f"'{val_escaped}'")

        col_str = ", ".join(col_pairs)
        val_str = ", ".join(val_pairs)
        return f"INSERT INTO {table} ({col_str}) VALUES ({val_str})"

    def _update_intent(self, intent: Any, table: str, columns: dict[str, str], schema: dict[str, dict]) -> str:
        if not intent.set_columns:
            return self._update(intent.raw_message, table, columns, schema)

        set_exprs = []
        for col_key, val in intent.set_columns.items():
            matched_col = columns.get(col_key.lower(), col_key)
            if isinstance(val, (int, float)):
                set_exprs.append(f"{matched_col} = {val}")
            else:
                val_escaped = str(val).replace("'", "''")
                set_exprs.append(f"{matched_col} = '{val_escaped}'")

        set_str = ", ".join(set_exprs)

        where_str = ""
        if intent.filter_column and intent.filter_value is not None:
            f_col = columns.get(intent.filter_column.lower(), intent.filter_column)
            val = intent.filter_value
            if isinstance(val, (int, float)):
                where_str = f" WHERE {f_col} = {val}"
            else:
                where_str = f" WHERE {f_col} = '{val}'"

        return f"UPDATE {table} SET {set_str}{where_str}"

    def _delete_intent(self, intent: Any, table: str, columns: dict[str, str], col_list: list[str]) -> str:
        pk_col = next((c for c in col_list if c.lower() in ("id", f"{table.rstrip('s')}_id")), col_list[0])

        if intent.ordering_definition or intent.ordering_column:
            order_col = intent.ordering_column
            if not order_col and intent.ordering_definition:
                order_col = intent.ordering_definition.split()[0]
            if not order_col or order_col.lower() not in columns:
                order_col = pk_col
            else:
                order_col = columns[order_col.lower()]

            direction = intent.ordering_direction or "DESC"
            return f"DELETE FROM {table} WHERE {pk_col} = (SELECT {pk_col} FROM {table} ORDER BY {order_col} {direction} LIMIT 1)"

        if intent.filter_column and intent.filter_value:
            f_col = columns.get(intent.filter_column.lower(), intent.filter_column)
            return f"DELETE FROM {table} WHERE {f_col} = '{intent.filter_value}'"

        raise SqlGenerationError("DELETE query requires an explicit target filter condition or ordering predicate.")

    def _delete(self, text: str, table: str, columns: dict[str, str], schema: dict[str, dict] | None = None) -> str:
        words = text.split()
        table_meta = schema.get(table, {}) if schema else {}
        status_col = next((c["name"] for c in table_meta.get("columns", []) if any(term in c["name"].lower() for term in ("status", "state", "active", "condition", "flag"))), None)
        for word in words:
            if word not in ("delete", "remove", "from", table.lower(), table.lower().rstrip("s")) and len(word) > 2:
                if status_col:
                    return f"DELETE FROM {table} WHERE {status_col} = '{word}'"

        raise SqlGenerationError("Delete requests require an explicit target filter condition.")

    def _update(self, text: str, table: str, columns: dict[str, str], schema: dict[str, dict] | None = None) -> str:
        match = re.search(r"set\s+(\w+)\s+(?:to|=)\s+([\w-]+)", text)
        if match:
            col_name = match.group(1)
            val = match.group(2).replace("'", "''")
            target_col = columns.get(col_name.lower(), col_name)

            # Extract WHERE predicate if supplied
            where_match = re.search(r"where\s+(.+)$", text, re.I)
            if where_match:
                where_expr = where_match.group(1).strip()
                # Simple condition format standardisation
                w_eq = re.search(r"(\w+)\s*(?:=|\bis\b|to)\s*([\w@.-]+)", where_expr, re.I)
                if w_eq and w_eq.group(1).lower() in columns:
                    w_col = columns[w_eq.group(1).lower()]
                    w_val = w_eq.group(2)
                    w_val_str = f"'{w_val}'" if not w_val.isdigit() else w_val
                    return f"UPDATE {table} SET {target_col} = '{val}' WHERE {w_col} = {w_val_str}"
                return f"UPDATE {table} SET {target_col} = '{val}' WHERE {where_expr}"
            return f"UPDATE {table} SET {target_col} = '{val}'"

        raise SqlGenerationError("UPDATE query requires explicit SET column values.")

    def _insert(self, text: str, table: str, columns: dict[str, str], schema: dict[str, dict] | None = None) -> str:
        raw_insert = re.search(r"insert\s+into\s+(\w+)\s*\(([^)]+)\)\s*values\s*\(([^)]+)\)", text, re.I)
        if raw_insert:
            cols = raw_insert.group(2)
            vals = raw_insert.group(3)
            return f"INSERT INTO {table} ({cols}) VALUES ({vals})"

        # Extract explicit field values from text e.g. "name Alice with email alice@example.com"
        kv_pairs = re.findall(r"([a-z_]+)\s*(?:=|\bis\b|with|:|\s)\s*([\w@.-]+)", text, re.I)
        valid_kvs = []
        ignored_words = {"add", "insert", "new", "into", "table", "record", "customer", "employee", "order", "record", "data"}
        for k, v in kv_pairs:
            k_clean = k.lower().strip()
            if k_clean in columns and k_clean not in ignored_words and v.lower() not in ignored_words:
                val_str = f"'{v}'" if not v.isdigit() else v
                valid_kvs.append((columns[k_clean], val_str))

        if valid_kvs:
            col_str = ", ".join(k for k, _ in valid_kvs)
            val_str = ", ".join(v for _, v in valid_kvs)
            return f"INSERT INTO {table} ({col_str}) VALUES ({val_str})"

        raise SqlGenerationError("INSERT query requires explicit column values supplied in prompt or structured intent.")

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
                m_from = re.search(r"\bfrom\s+([a-z_][\w]*)", sql, re.I)
                curr_table = m_from.group(1) if m_from and m_from.group(1) in schema else list(schema.keys())[0]
                table_cols = schema.get(curr_table, {}).get("columns", [])
                text_col = next((c["name"] for c in table_cols if any(t in c.get("type", "").upper() for t in ("TEXT", "CHAR", "VARCHAR")) and not c.get("primary_key")), list(columns.values())[0])

                if "WHERE" in res_sql.upper():
                    res_sql = re.sub(r"(WHERE\s+)", f"\\1{text_col} = '{val}' AND ", res_sql, flags=re.I)
                elif "LIMIT" in res_sql.upper():
                    limit_match = re.search(r"\s+LIMIT\s+\d+", res_sql, flags=re.I)
                    limit_str = limit_match.group(0) if limit_match else ""
                    res_sql = re.sub(r"\s+LIMIT\s+\d+", "", res_sql, flags=re.I)
                    res_sql += f" WHERE {text_col} = '{val}'{limit_str}"
                else:
                    res_sql += f" WHERE {text_col} = '{val}'"

        return res_sql

