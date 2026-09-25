# Voice to SQL - Safe Natural-Language Database Assistant

A hackathon-ready end-to-end application integrating a React (TypeScript + Vite + TailwindCSS) frontend with a safe, intelligent FastAPI backend that translates voice and text queries into validated SQL queries with dynamic schema visualization, ambiguity clarification, mutation confirmation safeguards, and real-time execution.

---

## 1. Project Architecture

```
Voice to SQL/
├── backend/
│   ├── api/                # FastAPI routes (/query, /voice/query, /query/clarify, /query/confirm, /schema, /history)
│   ├── config/             # Environment configuration (Pydantic BaseSettings)
│   ├── db/                 # SQLite / PostgreSQL connection runner & seed script
│   ├── model/              # Pydantic request & response schemas
│   ├── services/           # Intent, SQL generation, validation, STT, audit & execution services
│   ├── tests/              # Pytest test suite (35 passing tests)
│   ├── main.py             # FastAPI entry point & CORS configuration
│   └── pyproject.toml      # Backend dependencies (managed via uv)
│
├── frontend/
│   ├── src/
│   │   ├── api/            # Re-exports & legacy client aliases
│   │   ├── services/       # Centralized API client (api.ts) with typed fetch functions
│   │   ├── components/     # UI components (ChatArea, QueryResult, InputArea, MicrophoneButton, SchemaPanel, HistoryPanel)
│   │   ├── hooks/          # React hooks for API state
│   │   ├── types/          # Shared TypeScript interfaces aligned with backend Pydantic models
│   │   ├── App.tsx         # Root component
│   │   └── index.css       # Tailwind CSS & custom visual design tokens
│   ├── .env                # Frontend environment configuration (VITE_API_BASE_URL)
│   ├── package.json        # Frontend dependencies & scripts
│   └── vite.config.ts      # Vite dev server configuration (Port 3000 & API proxy)
```

---

## 2. Prerequisites & Setup

- **Python**: 3.10+ (using `uv` or `pip`)
- **Node.js**: 18+ and `npm`

---

## 3. How to Start the Backend

1. Navigate to `backend/`:
   ```bash
   cd backend
   ```
2. Initialize sample database (SQLite out-of-the-box):
   ```bash
   python db/init_db.py
   ```
3. Run the backend server with `uv`:
   ```bash
   uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *The backend server will run on `http://127.0.0.1:8000`.*

---

## 4. How to Start the Frontend

1. Navigate to `frontend/`:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The frontend application will run on `http://localhost:3000`.*

---

## 5. Required Environment Variables

### Backend (`backend/.env`)

```env
# Database Connection URL (SQLite or PostgreSQL)
DATABASE_URL=sqlite:///D:/Voice to SQL/backend/db/voice_to_sql.db

# LLM Configuration (gemini | openai | groq | ollama | mock)
LLM_PROVIDER=gemini
LLM_API_KEY=your_gemini_api_key
LLM_MODEL=gemini-2.5-flash
LLM_TIMEOUT_SECONDS=12.0

# Speech-To-Text Configuration (local | whisper | openai | mock)
STT_PROVIDER=mock
STT_API_KEY=
STT_CONFIDENCE_THRESHOLD=0.6

# System Policy & CORS
ALLOW_DDL=false
MAX_QUERY_ROWS=500
MAX_REPAIR_ATTEMPTS=3
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### Frontend (`frontend/.env`)

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## 6. Ports & API Endpoints

- **Frontend Port**: `3000` (`http://localhost:3000`)
- **Backend Port**: `8000` (`http://127.0.0.1:8000`)
- **API Base URL**: `http://127.0.0.1:8000/api`

### Endpoints
- `POST /api/query` — Process natural language text queries
- `POST /api/voice/query` — Process audio recordings (Speech-To-Text + Query Pipeline)
- `POST /api/query/clarify` — Resolve ambiguous query intent choices
- `POST /api/query/confirm` — Confirm execution of database mutations (UPDATE / DELETE)
- `GET /api/query/{request_id}` — Retrieve audit query status by ID
- `GET /api/schema` — Get database schema definitions
- `GET /api/history` — Get query conversation history

---

## 7. Voice Setup & Integration

- The frontend utilizes the native browser **MediaRecorder API** to record audio.
- Audio blobs are uploaded via `POST /api/voice/query` as `multipart/form-data` with field name `audio`.
- The backend transcribes audio using `faster-whisper` (or mock / OpenAI STT depending on `STT_PROVIDER`).
- If speech audio is unclear or confidence is low, the backend responds with `status: "RETRY_REQUIRED"` and message `"Can't understand, please say again."`, prompting the user to re-record.

---

## 8. Running Tests & Verifications

### Backend Tests
```bash
cd backend
uv run pytest
```

### Frontend Type-Checking & Build
```bash
cd frontend
npm run build
```
