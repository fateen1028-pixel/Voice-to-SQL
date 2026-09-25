# AI-Powered Voice & Natural Language Database Assistant (FastAPI Backend)

An enterprise-grade, hackathon-ready FastAPI backend for an AI-Powered Natural Language / Voice-to-SQL Database Assistant supporting PostgreSQL and SQLite.

The backend translates natural language text or spoken voice audio into safe, schema-grounded SQL queries, detects user intent ambiguity, enforces logical correctness and security firewalls, requires explicit server-backed single-use confirmation tokens for state-modifying queries (`INSERT`, `UPDATE`, `DELETE`), and returns structured results accompanied by factual natural-language explanations and chart visualization metadata.

---

## 🏗️ Project Architecture & Directory Structure

```
backend/
├── api/
│   ├── routes/
│   │   ├── query.py          # POST /api/query & GET /api/query/{request_id}
│   │   ├── voice.py          # POST /api/voice/query
│   │   ├── clarification.py  # POST /api/query/clarify
│   │   ├── confirmation.py   # POST /api/query/confirm
│   │   ├── schema.py         # GET  /api/schema
│   │   └── history.py        # GET  /api/history
│   └── routes.py             # Router aggregator
├── config/
│   └── settings.py           # Pydantic BaseSettings environment manager
├── db/
│   ├── connection.py         # PostgreSQL (psycopg2) & SQLite (sqlite3) adapter
│   ├── schema_inspector.py   # Information schema & PRAGMA schema inspector
│   └── query_runner.py       # SQL execution & EXPLAIN dry-run query plan runner
├── model/
│   ├── requests.py           # Pydantic request models
│   ├── responses.py          # Pydantic response models
│   ├── query_models.py       # Dataclasses for validation results & pending executions
│   ├── clarification_models.py
│   └── schemas.py            # Model re-exports
├── services/
│   ├── speech_to_text_service.py # Local faster-whisper STT with CPU-friendly int8 support & interface abstraction
│   ├── intent_service.py         # Intent understanding & prompt injection defense
│   ├── clarification_service.py  # Schema-driven dynamic clarification options generator
│   ├── schema_service.py         # Relevant schema retrieval & RAG filtering
│   ├── sql_generation_service.py # Gemini/OpenAI LLM generator & rule-based generator fallback
│   ├── sql_security_service.py   # Query firewall & role-based column access control
│   ├── sql_validation_service.py # sqlglot syntax validator & EXPLAIN dry-run validator
│   ├── sql_logic_service.py      # Logical query critique (date ranges, top-N, joins, GROUP BY)
│   ├── sql_repair_service.py     # Bounded automatic SQL repair (max 3 retries)
│   ├── query_execution_service.py# Safe query execution isolation boundary
│   ├── query_service.py          # Core pipeline orchestrator
│   ├── result_service.py         # Factual result explanation
│   ├── visualization_service.py  # Recommended chart metadata generator (bar, line, pie, kpi, table)
│   ├── conversation_service.py   # Context-aware follow-up conversation store
│   └── audit_service.py          # Audit logging service with token redaction
├── tests/
│   └── test_api.py           # Complete 35-item Pytest suite covering all pipeline requirements
├── main.py                   # FastAPI entrypoint, lifespan, CORS, and global error handlers
├── pyproject.toml            # Dependencies and Pytest configuration
├── uv.lock                   # Managed UV package lockfile
└── README.md
```

---

## ⚙️ Environment Configuration

Set the following variables in your `.env` file:

```env
# Database Connection URL (Supports PostgreSQL and SQLite)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
# SQLite example: DATABASE_URL=sqlite:///./assistant.db

# LLM Configuration
LLM_PROVIDER=gemini       # Options: gemini | openai | groq | ollama | mock
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=gemini-2.5-flash
LLM_TIMEOUT_SECONDS=12.0

# Local Speech-To-Text Configuration (CPU-Friendly, No GPU Required)
STT_PROVIDER=local        # Options: local | whisper | openai | mock
WHISPER_MODEL=base        # Options: tiny | base | small | medium | large-v3
WHISPER_DEVICE=cpu        # Options: cpu | cuda
WHISPER_COMPUTE_TYPE=int8 # Options: int8 | float32 | float16
STT_CONFIDENCE_THRESHOLD=0.6

# Security Policies
ALLOW_DDL=false           # Permit destructive DDL operations like DROP/TRUNCATE
MAX_QUERY_ROWS=500
MAX_REPAIR_ATTEMPTS=3
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

---

## 🎙️ Local Voice Setup (faster-whisper)

The STT system is engineered specifically for **16 GB RAM CPU-only laptop environments** without requiring a dedicated GPU or CUDA.

- **Default model**: `base`
- **Default device**: `cpu`
- **Default precision**: `int8` (low memory overhead, fast inference)
- **Unclear Audio / Noise Defense**: When spoken audio is unintelligible or low confidence, the API returns:
  ```json
  {
    "status": "RETRY_REQUIRED",
    "message": "Can't understand, please say again."
  }
  ```

---

## 🚀 Installation & Running the Server

### 1. Install Dependencies using `uv`

```powershell
uv sync --group dev
```

### 2. Launch FastAPI with Uvicorn

```powershell
uv run uvicorn main:app --reload
```

Interactive OpenAPI Swagger docs will be available at: **`http://127.0.0.1:8000/docs`**.

---

## 🔄 Core Query Pipeline Flows

```
VOICE / TEXT INPUT
       ↓
INPUT QUALITY & PROMPT INJECTION DEFENSE
       ↓
AMBIGUITY DETECTION & CLARIFICATION (IF AMBIGUOUS)
       ↓
DYNAMIC RELEVANT SCHEMA RETRIEVAL
       ↓
SQL GENERATION (LLM + DIALECT & GROUNDED SCHEMA)
       ↓
SYNTAX & EXPLAIN PLAN VALIDATION
       ↓
LOGICAL CORRECTNESS CHECK & AUTOMATIC REPAIR LOOP
       ↓
QUERY SECURITY & ROLE PERMISSION FIREWALL
       ↓
IS DATABASE MUTATION (INSERT / UPDATE / DELETE)?
       ├── NO (SELECT) → EXECUTE & RETURN RESULTS + EXPLANATION + VISUALIZATION METADATA
       └── YES → RETURN CONFIRMATION_REQUIRED WITH SERVER TOKEN
                       ↓
                   CLIENT POST /api/query/confirm WITH TOKEN
                       ↓
                   SERVER EXECUTES PREVIOUSLY VALIDATED SQL
```

---

## 📡 Key API Endpoints & Request Examples

### 1. Text Query (`POST /api/query`)

```json
{
  "message": "Show the top 10 customers by total spending",
  "conversation_id": "conv_123",
  "user_role": "user"
}
```

### 2. Voice Query (`POST /api/voice/query`)

Accepts a multipart `audio` file upload (`audio/wav`, `audio/mp3`, `audio/ogg`, etc.).

### 3. Clarification Request & Response (`POST /api/query` & `POST /api/query/clarify`)

When sending `"Show me the best customers"`, the backend returns:

```json
{
  "status": "CLARIFICATION_REQUIRED",
  "request_id": "req_88192a",
  "question": "What do you mean by 'best customers'?",
  "options": [
    "Highest total spending",
    "Most orders",
    "Most recent purchases"
  ]
}
```

To resolve and continue:

```json
POST /api/query/clarify
{
  "request_id": "req_88192a",
  "selection": "Highest total spending"
}
```

### 4. Database Modification Confirmation (`POST /api/query/confirm`)

Sending `"Delete inactive employees"` returns:

```json
{
  "status": "CONFIRMATION_REQUIRED",
  "request_id": "req_9921",
  "confirmation_token": "tok_a3f912b",
  "sql": "DELETE FROM employees WHERE status = 'inactive'",
  "operation": "DELETE",
  "estimated_affected_rows": 1,
  "message": "🚨 DELETE OPERATION: This action will permanently delete records. Please confirm before execution."
}
```

To confirm and execute:

```json
POST /api/query/confirm
{
  "confirmation_token": "tok_a3f912b"
}
```

### 5. Inspect Request Status / Audit Details (`GET /api/query/{request_id}`)

Retrieves logged query audit metadata by `request_id`.

---

## 🧪 Testing

Run the full pytest suite:

```powershell
uv run pytest
```

The test suite validates 35 critical scenarios including:
- Health check
- Text query execution
- Voice query transcription
- Local CPU-friendly faster-whisper service
- Unclear voice rejection ("Can't understand, please say again.")
- Ambiguous query clarification triggers
- Dynamic schema grounding
- Syntax, schema, and logical validation checks
- Automatic SQL repair
- Confirmation token isolation and single-use enforcement
- SQL and prompt injection defenses
- Role-based column access control
- DROP / TRUNCATE blocking
- Grounded result explanations and chart metadata generation

---

## ⚠️ Known Limitations

- High-concurrency production deployments using local CPU Whisper model should scale worker processes using a task queue like Celery or RQ if high audio throughput is needed.
- DDL statements (`DROP`, `TRUNCATE`) are blocked by default for security, but can be enabled via `ALLOW_DDL=true` in `.env` if required by an administrative user.
