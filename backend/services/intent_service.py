"""Intent understanding and ambiguity detection service."""
import re
from typing import Any
from model.query_models import StructuredIntent
from services.clarification_service import ClarificationService


class IntentService:
    def __init__(self, clarification_service: ClarificationService) -> None:
        self.clarification_service = clarification_service

    def extract_intent(
        self, message: str, schema: dict[str, dict] | None = None, active_context_table: str | None = None
    ) -> StructuredIntent:
        schema = schema or {}
        raw = message.strip()
        normalized = raw.lower()

        # 1. Check for raw SQL / DDL statements
        if any(ddl in normalized for ddl in ("attach database", "drop table", "truncate table", "select from from")):
            intent = StructuredIntent(operation="SELECT", raw_message=raw, is_complete=True)
            return intent

        # 2. Operation Resolution (Semantic, No SELECT-by-default)
        operation = self._resolve_operation(normalized, active_context_table)

        # 3. Table Matching & Invalid Table Detection
        matched_table = self._match_table(normalized, schema)
        if not matched_table and active_context_table and active_context_table in schema:
            matched_table = active_context_table

        table_invalid = False
        if not matched_table:
            # Check if user mentioned an explicit unknown noun that is not in schema or standard domain terms
            stop_words = {
                "can", "you", "could", "please", "would", "tell", "show", "list", "get", "view", "find", "all", "the", "from",
                "where", "select", "sort", "by", "order", "only", "first", "top", "give", "me", "data", "number",
                "information", "details", "record", "records", "row", "rows", "one", "ones", "with", "and", "that", "have",
                "delete", "remove", "update", "insert", "add", "create", "last", "best", "worst", "latest", "oldest", "recent", "recently",
                "newest", "active", "inactive", "this", "that", "those", "these", "it", "item", "items", "table", "database",
                "revenue", "biggest", "sales", "popular", "highest", "lowest", "employee", "customer", "order"
            }

            words = set(re.findall(r"\b[a-z]{3,}\b", normalized)) - stop_words
            table_names_lower = [t.lower() for t in schema]
            if words and not any(w in table_names_lower or w.rstrip("s") in table_names_lower for w in words):
                table_invalid = True

        # 4. Dynamic Column and Value Extraction (for INSERT / UPDATE / SELECT)
        set_columns: dict[str, Any] = {}
        if matched_table and matched_table in schema:
            set_columns = self._extract_set_columns(raw, normalized, schema[matched_table])

        # 5. Detect Target and Vague / Relative Terms
        vague_terms = []
        relative_words = ["last", "first", "latest", "oldest", "recent", "recently", "newest"]
        subjective_words = [
            "best", "worst", "highest", "lowest", "active", "inactive", "top", "bottom",
            "popular", "large", "small", "important", "successful", "failed", "sales", "biggest"
        ]

        for w in relative_words + subjective_words:
            if re.search(r"\b" + w + r"\b", normalized):
                vague_terms.append(w)

        target = None
        if "last row" in normalized or "last record" in normalized or "last one" in normalized or "delete the last" in normalized:
            target = "last row"
        elif "first row" in normalized or "first record" in normalized:
            target = "first row"
        elif vague_terms:
            first_vague = vague_terms[0]
            target = f"{first_vague} {matched_table or 'records'}"
        elif matched_table:
            target = matched_table

        # 6. Detect Limit, Metric, and Filter details
        limit = None
        top_match = re.search(r"\b(?:top|first|latest)\s+(\d+)\b", normalized)
        if top_match:
            limit = int(top_match.group(1))

        metric = None
        by_match = re.search(r"\bby\s+([a-z0-9_\s]+)", normalized)
        if by_match:
            metric = by_match.group(1).strip()

        ordering_column = None
        ordering_direction = "DESC"
        ordering_definition = None

        if "most recently created" in normalized or "latest created" in normalized or "recently created" in normalized:
            date_col = next((c["name"] for c in schema.get(matched_table, {}).get("columns", []) if any(term in c["name"].lower() for term in ("created", "joined", "timestamp", "date", "inserted"))), None) if matched_table else None
            date_col = date_col or "created_at"
            ordering_column = date_col
            ordering_direction = "DESC"
            ordering_definition = f"{date_col} DESC"
        elif "highest id" in normalized:
            pk_col = next((c["name"] for c in schema.get(matched_table, {}).get("columns", []) if c.get("primary_key") or c["name"].lower() in ("id", f"{matched_table.rstrip('s') if matched_table else ''}_id")), None) if matched_table else None
            pk_col = pk_col or "id"
            ordering_column = pk_col
            ordering_direction = "DESC"
            ordering_definition = f"{pk_col} DESC"

        # WHERE filter parsing
        filter_column = None
        filter_value = None
        where_match = re.search(r"\bwhere\s+(\w+)\s*(=|is|like)\s*['\"]?(\w+)['\"]?", normalized)
        if where_match:
            filter_column = where_match.group(1)
            filter_value = where_match.group(3)
        elif matched_table:
            table_cols = schema.get(matched_table, {}).get("columns", [])
            status_col = next((c["name"] for c in table_cols if any(term in c["name"].lower() for term in ("status", "active", "state", "condition", "flag"))), None)
            if status_col:
                for word in ("inactive", "active", "pending", "completed", "cancelled", "archived"):
                    if word in normalized:
                        filter_column = status_col
                        filter_value = word
                        break

        intent = StructuredIntent(
            operation=operation,
            table=matched_table,
            target=target,
            vague_terms=vague_terms,
            ordering_column=ordering_column,
            ordering_direction=ordering_direction,
            ordering_definition=ordering_definition,
            filter_column=filter_column,
            filter_value=filter_value,
            set_columns=set_columns,
            metric=metric,
            limit=limit,
            raw_message=raw,
        )
        if table_invalid:
            intent.resolved_slots["table_invalid"] = True

        self.analyze_completeness(intent, schema)
        return intent

    def _resolve_operation(self, normalized: str, context_table: str | None = None) -> str:
        # Check meta / capability questions
        if any(p in normalized for p in ("what can you do", "what operations", "how to use", "what are options", "help")):
            return "AMBIGUOUS"

        # Check explicit verb groups
        has_delete = bool(re.search(r"\b(delete|remove|erase|purge)\b", normalized))
        has_update = bool(re.search(r"\b(update|change|modify|set|increase|decrease|adjust|rename)\b", normalized))
        has_insert = bool(re.search(r"\b(insert|add|create|register|store|put|make\s+.*\s+a\s+member)\b", normalized))
        has_select = bool(re.search(r"\b(show|list|get|view|find|how\s+many|which|display|fetch|search|count|top|best)\b", normalized))
        if re.search(r"\bwhat\b\s+(is|are|was|were|total|average|sum|max|min|count|the)\b", normalized):
            has_select = True

        if has_insert and not has_select:
            return "INSERT"
        if has_update and not has_select:
            return "UPDATE"
        if has_delete and not has_select:
            return "DELETE"
        if has_select:
            return "SELECT"

        # Check secondary patterns (e.g. "add ... to", "new ...")
        if re.search(r"\badd\b.*\b(to|into)\b", normalized) or re.search(r"\bnew\s+(record|row|user|customer|employee|student|product|order|item)\b", normalized):
            return "INSERT"

        if re.search(r"\b(salary|status|role|address|phone|email|price|name)\s+(to|=)\b", normalized):
            return "UPDATE"

        if context_table:
            return "SELECT"

        return "AMBIGUOUS"

    def _extract_set_columns(self, raw: str, normalized: str, table_schema: dict) -> dict[str, Any]:
        cols = table_schema.get("columns", [])
        extracted: dict[str, Any] = {}

        # Isolate the SET portion of the text before any WHERE clause
        set_text_norm = normalized.split(" where ", 1)[0] if " where " in normalized else normalized
        set_text_raw = raw.split(" where ", 1)[0] if " where " in normalized.lower() else raw

        for c in cols:
            c_name = c["name"]
            c_name_low = c_name.lower()

            role_synonyms = ("role", "designation", "job_title", "role_name", "position")
            salary_synonyms = ("salary", "compensation", "pay", "remuneration", "wage")
            name_synonyms = ("name", "full_name", "staff_name", "employee_name", "employee", "customer_name", "customer")

            # Salary extraction
            if c_name_low in salary_synonyms or any(s in c_name_low for s in salary_synonyms):
                sal_match = re.search(r"\b(?:salary|compensation|pay|wage|remuneration)\b(?:\s+(?:of|to|=|:))?\s*['\"]?\$?\s*([\d,]+(?:\.\d+)?)\b", set_text_norm)
                if sal_match:
                    num_str = sal_match.group(1).replace(",", "")
                    try:
                        extracted[c_name] = int(float(num_str)) if float(num_str).is_integer() else float(num_str)
                    except ValueError:
                        extracted[c_name] = sal_match.group(1)

            # Role extraction
            if c_name_low in role_synonyms or any(s in c_name_low for s in role_synonyms):
                role_match = re.search(r"\b(?:role|designation|position|job_title|role_name)\b(?:\s+(?:of|to|=|:))?\s*['\"]?([a-zA-Z0-9_\s-]+?)['\"]?(?:\s+with|\s+to|\s+for|\s+in|\s*$)", set_text_raw, re.I)
                if role_match:
                    extracted[c_name] = role_match.group(1).strip()

            # Name / Entity Name extraction
            if c_name_low in name_synonyms or any(s in c_name_low for s in name_synonyms):
                name_match = re.search(r"\b(?:employee|customer|student|user|staff|member|person|name|full_name)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", set_text_raw)
                if not name_match:
                    name_match = re.search(r"\b(?:name|full_name)\s*(?:is|=|to|:)?\s*['\"]?([A-Za-z\s]{2,30})['\"]?", set_text_raw, re.I)
                if name_match:
                    val = name_match.group(1).strip()
                    if val.lower() not in ("table", "database", "record", "row", "data", "role", "salary", "dancer"):
                        extracted[c_name] = val

            # Generic `col = val` or `col to val` matching for schema column names in set_text
            gen_match = re.search(r"\b" + re.escape(c_name_low) + r"\b\s*(?:=|\bis\b|to|:)\s*['\"]?([\w@.-]+)['\"]?", set_text_norm)
            if gen_match and c_name not in extracted:
                val = gen_match.group(1)
                extracted[c_name] = int(val) if val.isdigit() else val

        return extracted

    def analyze_completeness(self, intent: StructuredIntent, schema: dict[str, dict]) -> tuple[bool, list[str]]:
        missing: list[str] = []

        if intent.resolved_slots.get("table_invalid"):
            intent.missing_slots = []
            intent.is_complete = True
            return True, []

        if intent.operation == "AMBIGUOUS":
            missing.append("operation")
            intent.missing_slots = missing
            intent.is_complete = False
            return False, missing

        # HARD REQUIREMENT: Table must be known and present in schema
        if not intent.table or intent.table not in schema:
            missing.append("table")

        raw_lower = intent.raw_message.lower()
        ambiguous_pronouns = ("that", "those", "them", "these", "this", "it")

        if intent.operation == "INSERT":
            if intent.table and intent.table in schema:
                cols_meta = schema[intent.table].get("columns", [])
                set_cols_lower = {k.lower(): v for k, v in intent.set_columns.items()}
                for c in cols_meta:
                    c_name = c["name"]
                    c_low = c_name.lower()
                    is_pk = c.get("primary_key", False) or c_low in ("id", f"{intent.table.rstrip('s')}_id")
                    not_null = not c.get("nullable", True)
                    no_default = c.get("default") is None
                    if not_null and no_default and not is_pk and c_low not in set_cols_lower:
                        missing.append(f"field:{c_name}")

        elif intent.operation == "DELETE":
            # Check for ambiguous references like "delete that", "delete those"
            words = set(re.findall(r"\b[a-z]+\b", raw_lower))
            has_ambiguous_pronoun = any(p in words for p in ambiguous_pronouns)

            if intent.ordering_definition or intent.ordering_column:
                pass
            elif intent.target in ("last row", "first row", "latest row", "oldest row", "last one", "first one") or any(t in intent.vague_terms for t in ("last", "first", "latest", "oldest", "recent")):
                missing.append("ordering_definition")
            elif intent.filter_column and intent.filter_value:
                pass
            elif has_ambiguous_pronoun:
                # "Delete that" / "Delete those" requires explicit target filter definition
                missing.append("filter_definition")
            elif "all" in raw_lower or "everything" in raw_lower:
                pass
            else:
                missing.append("filter_definition")

        elif intent.operation == "UPDATE":
            if not intent.set_columns and "set" not in raw_lower:
                missing.append("set_columns")
            if not intent.filter_column and not intent.filter_value and "where" not in raw_lower and "all" not in raw_lower:
                missing.append("filter_definition")

        elif intent.operation == "SELECT":
            subj_terms = ("best", "biggest", "largest", "sales", "top", "worst", "popular")
            if any(term in (intent.target or "") for term in subj_terms) or any(term in intent.vague_terms for term in subj_terms):
                if not intent.metric and not intent.ordering_column and not intent.limit:
                    missing.append("metric")

        intent.missing_slots = missing
        intent.is_complete = (len(missing) == 0)
        return intent.is_complete, missing

    def update_intent_with_selection(
        self, intent: StructuredIntent, selection: str, field: str, schema: dict[str, dict]
    ) -> StructuredIntent:
        selection_clean = selection.strip()
        selection_norm = selection_clean.lower()

        if field == "operation":
            op_map = {
                "view data": "SELECT",
                "add data": "INSERT",
                "update data": "UPDATE",
                "delete data": "DELETE",
                "select": "SELECT",
                "insert": "INSERT",
                "update": "UPDATE",
                "delete": "DELETE",
            }
            intent.operation = op_map.get(selection_norm, "SELECT")
            intent.resolved_slots["operation"] = intent.operation

        elif field == "table":
            for t in schema:
                if t.lower() == selection_norm or t.lower().rstrip("s") == selection_norm.rstrip("s"):
                    intent.table = t
                    break
            if not intent.table and selection_clean in schema:
                intent.table = selection_clean
            intent.resolved_slots["table"] = intent.table

        elif field.startswith("field:"):
            col_name = field.split(":", 1)[1]
            intent.set_columns[col_name] = selection_clean
            intent.resolved_slots[col_name] = selection_clean

        elif field == "ordering_definition":
            table_cols = schema.get(intent.table, {}).get("columns", []) if intent.table else []
            col_names = {c["name"].lower(): c["name"] for c in table_cols}

            if "id" in selection_norm:
                pk = next((c["name"] for c in table_cols if c.get("primary_key") or c["name"].lower() in ("id", f"{intent.table.rstrip('s') if intent.table else ''}_id")), "id")
                intent.ordering_column = pk
                intent.ordering_direction = "DESC"
                intent.ordering_definition = f"{pk} DESC"
            elif "created" in selection_norm or "recent" in selection_norm:
                c_col = next((c["name"] for c in table_cols if any(term in c["name"].lower() for term in ("created", "joined", "timestamp", "date"))), None)
                if c_col:
                    intent.ordering_column = c_col
                    intent.ordering_direction = "DESC"
                    intent.ordering_definition = f"{c_col} DESC"
                else:
                    intent.ordering_definition = "created_at DESC"
            elif "updated" in selection_norm:
                u_col = next((c["name"] for c in table_cols if any(term in c["name"].lower() for term in ("updated", "modified"))), None)
                if u_col:
                    intent.ordering_column = u_col
                    intent.ordering_direction = "DESC"
                    intent.ordering_definition = f"{u_col} DESC"
                else:
                    intent.ordering_definition = "updated_at DESC"
            else:
                intent.ordering_definition = selection_clean

            intent.resolved_slots["ordering_definition"] = intent.ordering_definition

        elif field == "metric":
            intent.metric = selection_clean
            intent.resolved_slots["metric"] = selection_clean

        elif field == "filter_definition":
            intent.resolved_slots["filter_definition"] = selection_clean
            if "=" in selection_clean:
                parts = selection_clean.replace("WHERE", "").split("=")
                if len(parts) == 2:
                    intent.filter_column = parts[0].strip()
                    intent.filter_value = parts[1].strip().strip("'\"")

        self.analyze_completeness(intent, schema)
        return intent

    def detect_clarification(self, message: str, schema: dict[str, dict] | None = None) -> tuple[str, list[str]] | None:
        normalized = message.lower().strip()
        if "meaning:" in normalized or "clarification:" in normalized:
            return None

        intent = self.extract_intent(message, schema)
        if not intent.is_complete:
            missing = intent.missing_slots[0]
            question, field, options = self.clarification_service.build_clarification(intent, missing, schema)
            return question, [str(o) for o in options]

        return None

    def is_prompt_injection(self, message: str) -> bool:
        normalized = message.lower()
        suspicious_patterns = [
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"system\s+prompt",
            r"bypass\s+security",
            r"disregard\s+prior",
        ]
        return any(re.search(pattern, normalized) for pattern in suspicious_patterns)

    def _match_table(self, text: str, schema: dict[str, dict]) -> str | None:
        words = set(re.findall(r"\b\w+\b", text.lower()))
        for table in schema:
            t_lower = table.lower()
            t_sing = t_lower.rstrip("s")
            if t_lower in words or t_sing in words:
                return table
        for table, meta in schema.items():
            col_names = [c["name"].lower() for c in meta.get("columns", [])]
            if any(w in col_names for w in words if len(w) > 2):
                return table
        return None



