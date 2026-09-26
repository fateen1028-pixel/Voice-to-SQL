"""Intent understanding and ambiguity detection service."""
import re
from typing import Any
from model.query_models import StructuredIntent
from services.clarification_service import ClarificationService


NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
    "ஒன்னாவது": 1, "ரெண்டாவது": 2, "மூணாவது": 3, "நாலாவது": 4, "அஞ்சாவது": 5, "ஆறாவது": 6, "ஏழாவது": 7, "எட்டாவது": 8, "ஒன்பதாவது": 9, "பத்தாவது": 10
}


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

        # A. Dynamic ID / Primary Key number & number-word extraction
        id_match = re.search(
            r"\b(?:(?:[a-z0-9_]+\s+)?id|record|row|ஐடி)\s*(?:no\.?|num\.?|number|நம்பர்|=|#|:)?\s*([a-zA-Z0-9_\u0B80-\u0BFF]+)\b",
            normalized,
        )
        if id_match and matched_table and matched_table in schema:
            raw_id_val = id_match.group(1).lower()
            parsed_id = None
            if raw_id_val.isdigit():
                parsed_id = int(raw_id_val)
            elif raw_id_val in NUMBER_WORDS:
                parsed_id = NUMBER_WORDS[raw_id_val]

            if parsed_id is not None:
                table_cols = schema[matched_table].get("columns", [])
                pk_col = next((c["name"] for c in table_cols if c.get("primary_key") or c["name"].lower() in ("id", f"{matched_table.rstrip('s')}_id")), "id")
                filter_column = pk_col
                filter_value = parsed_id

        if not filter_column:
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
        if any(p in normalized for p in ("what can you do", "what operations", "how to use", "what are options", "help", "என்ன செய்ய முடியும்")):
            return "AMBIGUOUS"

        # Check explicit verb groups (English + Day-to-Day Spoken Tamil + Tanglish)
        has_delete = bool(
            re.search(r"\b(delete|remove|erase|purge|neekku|azhi|thookku|thookidunga|thooki|azhichidu|azhichidunga)\b", normalized)
        ) or any(w in normalized for w in ("நீக்கு", "அழி", "நீக்கவும்", "அழிக்கவும்", "தூக்கு", "தூக்குங்க", "தூக்கிடுங்க", "தூக்கி", "அழிச்சிடு", "அழிச்சிடுங்க"))

        has_update = bool(
            re.search(r"\b(update|change|modify|set|increase|decrease|adjust|rename|maatru|puthuppi|maathividu|maathividunga|maathu|maathunga|thiruthu)\b", normalized)
        ) or any(w in normalized for w in ("மாற்று", "புதுப்பி", "மாற்றவும்", "மாத்து", "மாத்துங்க", "மாத்திவிடு", "மாத்திவிடுங்க"))

        has_insert = bool(
            re.search(r"\b(insert|add|create|register|store|put|make\s+.*\s+a\s+member|saer|saerka|podu|podunga|serthudu|serthudunga|saerthu|ullidu)\b", normalized)
        ) or any(w in normalized for w in ("சேர்", "சேர்க்க", "சேர்க்கவும்", "சேரு", "உள்ளிடு", "போடு", "போடுங்க", "சேர்த்துடு", "சேர்த்துடுங்க", "சேர்த்து", "சேர்த்துவிடு"))

        has_select = bool(
            re.search(r"\b(show|list|get|view|find|how\s+many|which|display|fetch|search|count|top|best|kaatu|kaattunga|kaanum|kudu|kudunga|eduthukko|thedu|edu|evlo|evalo|ethana|yavlo|yaaru)\b", normalized)
        ) or any(w in normalized for w in ("காட்டு", "காட்டுங்க", "காண்பி", "எடு", "பட்டியலிடு", "தேடு", "பார்ப்போம்", "குடு", "குடுங்க", "எடுத்துக்கோ", "எவ்வளவு", "எத்தனை", "யாரு", "எந்த"))

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

        # Check secondary patterns (e.g. "add ... to", "new ...", Tamil additions)
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

        set_text_norm = normalized.split(" where ", 1)[0] if " where " in normalized else normalized
        set_text_raw = raw.split(" where ", 1)[0] if " where " in normalized.lower() else raw

        # Dynamic Tamil / Tanglish transliteration dictionary for schema column roots
        col_transliterations = {
            "name": ("பெயர்", "பெயரை", "பெயரு", "name", "title"),
            "location": ("லொகேஷன்", "இடம்", "இருப்பிடம்", "location", "loc", "city"),
            "email": ("மின்னஞ்சல்", "ஈமெயில்", "மெயில்", "email", "mail"),
            "phone": ("தொலைபேசி", "போன்", "மொபைல்", "phone", "mobile", "contact"),
            "salary": ("சம்பளம்", "ஊதியம்", "salary", "pay", "income", "wage"),
            "role": ("பதவி", "பொறுப்பு", "வேலை", "role", "designation", "position"),
            "status": ("நிலை", "ஸ்டேட்டஸ்", "status", "state"),
            "date": ("தேதி", "நாள்", "date", "joined", "created"),
            "address": ("முகவரி", "அட்ரஸ்", "address"),
            "city": ("நகரம்", "சிட்டி", "city"),
            "department": ("டிபார்ட்மென்ட்", "டிபார்ட்மென்ட்ட", "department", "dept"),
        }

        # 0. English Explicit Entity Name Extractor (e.g. "department named science", "named Charlie", "employee Michael Jackson")
        named_match = re.search(
            r"\b(?:named|called|name\s+is|named\s+as|called\s+as|with\s+name|with\s+the\s+name)\s+['\"]?([A-Za-z0-9_.-]+(?:\s+[A-Za-z0-9_.-]+)*|[\u0B80-\u0BFF]+)['\"]?",
            set_text_raw,
            re.I,
        )
        for c in cols:
            c_name = c["name"]
            c_low = c_name.lower()
            is_name_col = any(term in c_low for term in ("name", "full_name", "title", "label")) or c_low.endswith("_name")
            if is_name_col and c_name not in extracted:
                if named_match:
                    val_candidate = named_match.group(1).strip()
                    val_words = []
                    for w in val_candidate.split():
                        if w.lower() in ("with", "for", "in", "at", "location", "salary", "role", "dept"):
                            break
                        val_words.append(w)
                    if val_words:
                        extracted[c_name] = " ".join(val_words)
                else:
                    name_m = re.search(
                        r"\b(?:employee|customer|user|person|named|name)\s+([A-Z][a-zA-Z0-9_]*(?:\s+[A-Z][a-zA-Z0-9_]*)*)\b",
                        set_text_raw,
                    )
                    if name_m:
                        val_candidate = name_m.group(1).strip()
                        if val_candidate.lower() not in ("table", "database", "record", "row", "data"):
                            extracted[c_name] = val_candidate

        # 1. Dynamic Noun Marker Extraction: `<value> ங்கிற/என்கிற/என்ற/nu/enra <target>`
        # Example: "science ங்கிற டிபார்ட்மென்ட்ட" -> value="science" for name/department_name column
        noun_marker_matches = re.findall(
            r"([A-Za-z0-9_]+)\s*(?:ங்கிற|என்கிற|என்ற|enra|nu|இன்கிற)\s*([A-Za-z0-9_அ-ஹஃா-்]+)",
            set_text_raw,
            re.I,
        )
        for val_found, target_found in noun_marker_matches:
            t_low = target_found.lower()
            val_clean = val_found.strip()
            for c in cols:
                c_name = c["name"]
                c_low = c_name.lower()
                is_name_col = any(term in c_low for term in ("name", "title", "label"))
                target_matches_table_or_col = (
                    c_low in t_low or t_low in c_low or "department" in t_low or "டிபார்ட்மென்ட்" in t_low or "table" in t_low or "record" in t_low
                )
                if is_name_col and target_matches_table_or_col and c_name not in extracted:
                    extracted[c_name] = val_clean

        # 2. Dynamic Pattern Extraction for every column in the table schema
        for c in cols:
            c_name = c["name"]
            c_name_low = c_name.lower()
            if c_name in extracted:
                continue

            # DO NOT extract string values into autoincrement / primary key ID columns
            is_pk_id = c.get("primary_key") or c_name_low == "id" or c_name_low.endswith("_id")
            if is_pk_id:
                pk_num_m = re.search(r"\b" + re.escape(c_name_low) + r"\s*(?:=|\bis\b|:)?\s*(\d+)\b", set_text_norm)
                if pk_num_m:
                    extracted[c_name] = int(pk_num_m.group(1))
                continue

            short_col = c_name_low.replace("_id", "").replace("_name", "").replace("_date", "").replace("_address", "")
            search_terms = [c_name_low, short_col]
            for term, trans_list in col_transliterations.items():
                if term in c_name_low or c_name_low in term:
                    search_terms.extend(trans_list)

            # Search `<col_term> [is|=|to|:] <value>` or `<col_term> <value>`
            ignored_words = {
                "of", "for", "a", "an", "the", "as", "is", "to", "with", "in", "by", "on", "at", "from", "and", "or",
                "table", "database", "record", "row", "data", "departments", "employees", "customers", "orders", "products"
            }
            for term in search_terms:
                pat = (
                    r"\b"
                    + re.escape(term)
                    + r"\b(?:\s+(?:=|\bis\b|\bto\b|\bof\b|\bfor\b|\bas\b|:|\bwith\b|இருக்கு|ஆன|வந்துகிட்டு|வந்து))*\s*['\"]?([A-Za-z0-9_.,@%+-]+(?:\s+[A-Za-z0-9_.,@%+-]+)*|[\u0B80-\u0BFF]+)['\"]?"
                )
                match = re.search(pat, set_text_raw, re.I)
                if match:
                    val = match.group(1).strip()
                    val = re.sub(r"[\sலஇல்]+$", "", val).strip()
                    # Strip out trailing keywords if regex matched into next clause
                    clean_words = []
                    for w in val.split():
                        if w.lower() in ("with", "for", "to", "and", "in", "where", "with a", "a"):
                            break
                        clean_words.append(w)
                    val = " ".join(clean_words).strip()
                    val_num = val.replace(",", "")
                    if val and val.lower() not in ignored_words and val.lower() not in (c_name_low, short_col):
                        extracted[c_name] = int(val_num) if val_num.isdigit() else val
                        break

            # 3. Dynamic Format Extractors (Email, Phone, Number/Salary, Date)
            if c_name not in extracted:
                if any(t in c_name_low for t in ("email", "mail")):
                    em = re.search(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b", set_text_norm)
                    if em:
                        extracted[c_name] = em.group(1)
                elif any(t in c_name_low for t in ("phone", "mobile", "contact", "cell")):
                    pm = re.search(r"\b(\+?\d[\d\s-]{7,15}\d)\b", set_text_norm)
                    if pm:
                        extracted[c_name] = pm.group(1).replace(" ", "").replace("-", "")
                elif any(t in c_name_low for t in ("salary", "pay", "wage", "income", "compensation")):
                    sm = re.search(r"\b(?:salary|compensation|pay|wage|remuneration|income|சம்பளம்)\b(?:\s+(?:of|is|to|=|:))?\s*['\"]?\$?\s*([\d,]+(?:\.\d+)?)\b", set_text_norm)
                    if sm:
                        num_str = sm.group(1).replace(",", "")
                        try:
                            extracted[c_name] = int(float(num_str)) if float(num_str).is_integer() else float(num_str)
                        except ValueError:
                            extracted[c_name] = sm.group(1)

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
            elif intent.resolved_slots.get("filter_definition") or intent.resolved_slots.get("all_records"):
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
            if not intent.filter_column and not intent.filter_value and "where" not in raw_lower and "all" not in raw_lower and not intent.resolved_slots.get("filter_definition") and not intent.resolved_slots.get("all_records"):
                missing.append("filter_definition")

        elif intent.operation == "SELECT":
            subj_terms = ("best", "biggest", "largest", "sales", "top", "worst", "popular")
            if any(term in (intent.target or "") for term in subj_terms) or any(term in intent.vague_terms for term in subj_terms) or any(term in raw_lower for term in subj_terms):
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

        new_op = self._resolve_operation(selection_norm)
        starts_query_verb = any(selection_norm.startswith(verb) for verb in ("show ", "list ", "get ", "view ", "find ", "select ", "delete ", "remove ", "update ", "insert ", "add "))
        if new_op in ("INSERT", "UPDATE", "DELETE") or starts_query_verb:
            return self.extract_intent(selection, schema)

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
            if "all" in selection_norm or "everything" in selection_norm:
                intent.resolved_slots["all_records"] = True

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
        text_lower = text.lower()

        tamil_table_map = {
            "employees": ("ஊழியர்", "ஊழியர்கள்", "பணியாளர்", "பணியாளர்கள்", "வேலைஆட்கள்", "oozhiyar", "paniyaalar"),
            "customers": ("வாடிக்கையாளர்", "வாடிக்கையாளர்கள்", "vaadikkaiyaalar"),
            "orders": ("ஆர்டர்", "ஆர்டர்கள்", "வாங்குதல்", "ஆர்டரை"),
            "products": ("தயாரிப்பு", "பொருட்கள்", "பண்டங்கள்"),
        }

        for table in schema:
            t_lower = table.lower()
            t_sing = t_lower.rstrip("s")
            if t_lower in words or t_sing in words:
                return table
            syns = tamil_table_map.get(t_lower, ())
            if any(syn in text_lower for syn in syns):
                return table

        for table, meta in schema.items():
            col_names = [c["name"].lower() for c in meta.get("columns", [])]
            if any(w in col_names for w in words if len(w) > 2):
                return table
        return None



