# VoiceQL Frontend

## Current Project State

VoiceQL is a voice-first natural-language database assistant for non-technical users. This frontend uses React 19, TypeScript, Tailwind CSS, and Vite. It is deliberately a focused conversational workspace rather than a dashboard or SQL editor.

The frontend is served by Vite and proxies `/api` to `http://localhost:8000` during development. The backend lives in the sibling `../backend` directory and is read-only.

### Implemented frontend capabilities

- Text questions submitted to the backend query pipeline with a generated conversation ID.
- Audio recording uploaded to the verified voice endpoint.
- Clear microphone permission fallback to text input.
- Result tables, factual explanation, generated SQL, empty results, and backend errors.
- Clarification option selection and mutation confirmation.
- On-demand, read-only schema panel and current-conversation history.
- Responsive mobile/desktop layout, keyboard-friendly controls, visible focus states, and reduced-motion support.

### Known limitations

- Conversation history is held in the backend's in-memory store and is unavailable after backend restart.
- Voice queries go through backend speech-to-text. The browser does not perform client-side transcription.
- No authentication, saved queries, exports, charts, or dashboard features are exposed because they are not required by the verified workflow.

## Project Vision

A calm, premium, voice-first assistant that lets people ask about database data without writing SQL. The interaction philosophy is inspired by conversational products and restrained developer tooling, but the design is original and intentionally avoids a generic chatbot or admin-dashboard treatment.

## Design System & UX Decisions

- The UI uses a near-black application canvas with white working components, inspired by the high-contrast clarity of modern coding tools while remaining an original interface.
- The query composer uses a medium neutral gray, rather than pure white, to reduce visual glare against the black workspace.
- The VoiceQL logo is an original compact mark that combines voice waveform bars with a query-style tail; it replaces the earlier plus-shaped mark.
- The empty state centers the actual workflow; results move into an output-first, readable stream once a question has been asked.
- Voice uses a touch-friendly microphone adjacent to a first-class text area. Recording has a subtle pulse; submission uses a compact spinner.
- Generated SQL is progressive disclosure via an accessible `details` control. Tables retain horizontal scrolling on narrow screens.
- Schema and history are secondary, on-demand surfaces because the backend supports them, but they do not distract from querying.

## Backend Capability Map

| Feature | Endpoint | Method | Request | Response/use |
| --- | --- | --- | --- | --- |
| Natural-language query | `/api/query` | `POST` | `{ message, conversation_id?, user_role? }` | `ApiResponse`; supports query generation, validation, execution, clarification, and confirmation states. |
| Voice query | `/api/voice/query` | `POST` | Multipart form field `audio` | `ApiResponse`; backend performs speech-to-text then the query pipeline. |
| Clarification | `/api/query/clarify` | `POST` | `{ request_id, selection }` | `ApiResponse` for the resolved query. |
| Mutation confirmation | `/api/query/confirm` | `POST` | `{ confirmation_token }` | `ApiResponse` after a server-issued one-time confirmation. |
| Schema | `/api/schema` | `GET` | None | `{ tables }`, rendered in the on-demand schema panel. |
| History | `/api/history?conversation_id=...` | `GET` | Conversation ID query parameter | `{ conversation_id, items }`, rendered only for the current session conversation. |

### Important backend behavior

- `SELECT` queries return `SUCCESS` with optional `columns`, `rows`, `row_count`, `sql`, `explanation`, and `visualization` recommendation.
- `INSERT`, `UPDATE`, and `DELETE` return `CONFIRMATION_REQUIRED` before execution.
- Clarification, validation failure, execution failure, security violation, and voice retry states are represented by the `status` field.
- The backend has no authentication implementation in its route contracts.

## Backend Protection Rules

- Backend files are read-only.
- Do not add or alter endpoints, models, schemas, database behavior, authentication, or middleware.
- Do not create UI for unsupported capabilities or fake server data.
- Database credentials and AI/STT configuration remain server-side.

## Feature Matrix

| Feature | Backend Supported | Frontend Implemented | Status |
| --- | --- | --- | --- |
| Natural-language query | Yes | Yes | Complete |
| Voice audio query | Yes | Yes | Complete |
| Text fallback | Yes | Yes | Complete |
| Result table and SQL | Yes | Yes | Complete |
| Clarification | Yes | Yes | Complete |
| Mutation confirmation | Yes | Yes | Complete |
| Schema inspection | Yes | Yes | Complete |
| Current conversation history | Yes | Yes | Complete |
| Server visualization recommendations | Yes | No | Deferred; backend recommendation has no rendered chart contract. |
| Authentication | No verified route | No | Not supported |

## API Contract

The shared TypeScript `ApiResponse` type mirrors the backend response model: `status`, optional `request_id`, `message`, `sql`, `operation`, result rows and columns, clarification options, confirmation token, validation summary, explanation, and visualization recommendation. API calls are centralized in `src/api/client.ts` and time out after 30 seconds for JSON requests.

## Voice Architecture

Browser microphone permission -> `MediaRecorder` -> multipart `audio` upload to `/api/voice/query` -> backend speech-to-text -> backend query pipeline -> `ApiResponse`.

If access cannot be granted or a microphone cannot start, the interface explains that typing remains available. No synthetic voice endpoint or browser transcription is used.

## Dependencies

- React 19 and React DOM 19
- Vite 6 with `@vitejs/plugin-react`
- TypeScript 5.7
- Tailwind CSS 3.4

No additional UI, chart, icon, or speech library was added.

## Environment Configuration

The frontend requires no environment variables. Vite proxies `/api` to `http://localhost:8000` in development. The backend owns database, LLM, STT, CORS, and secret configuration.

## Rejected / Deferred Features

- Saved queries, sharing, dashboards, analytics, exports, user profiles, teams, settings, and database management: not implemented because no verified backend capability requires them.
- Client-side browser speech recognition: deferred because the backend already has a real audio/STT endpoint.
- Chart rendering: deferred because the backend only returns a recommendation object and no dedicated visualization API or required chart dependency exists.

## Current Task

**Objective:** Soften the query composer from white to gray within the black UI.

**Status:** Completed on 2026-09-25.

**Files changed:** `src/App.tsx`, chat/input/result/schema components, `src/index.css`, `vite.config.ts`, and this README.

**Files that must not change:** all backend files.

## Implementation History

### 2026-09-25 - Voice-first frontend implementation

- Replaced the partially wired chat layout with a focused responsive workspace.
- Connected verified text, voice, clarification, confirmation, schema, and history paths.
- Added Vite's `@` alias so existing TypeScript path imports resolve in production builds.
- Verified with `npm.cmd run build`.

### 2026-09-25 - VoiceQL rebrand and dark UI

- Renamed the application header to VoiceQL.
- Replaced the plus mark with an original voice waveform/query logo.
- Reworked the visual system to a near-black canvas with white primary UI components.

### 2026-09-25 - Composer contrast refinement

- Changed the query composer surface from white to medium gray to reduce contrast intensity.

## Prompt History

### Prompt 1 - Build a backend-truthful voice-first product

**Date:** 2026-09-25

**User intent:** Build a premium React frontend for the existing application, deriving every interaction from the read-only backend and preserving persistent project memory in README.

**Changes made:** Inspected backend routes/services and frontend structure, implemented the responsive conversational UI, and documented the verified capabilities and constraints.

**Backend impact:** None.

**Status:** Completed.

### Prompt 3 - Gray query composer

**Date:** 2026-09-25

**User intent:** Make the overly white search/query input gray.

**Changes made:** Updated the composer background, border, and placeholder tones to a neutral gray palette.

**Backend impact:** None.

**Status:** Completed.

### Prompt 2 - VoiceQL identity and black UI

**Date:** 2026-09-25

**User intent:** Rename the application to VoiceQL, replace the plus logo with a creative mark, and make the UI primarily black with white components.

**Changes made:** Updated the header identity, created a custom VoiceQL SVG mark, and rebuilt the frontend color system around a high-contrast black-and-white interface.

**Backend impact:** None.

**Status:** Completed.

## Roadmap

### Now

- Keep API contracts and README aligned with backend changes.

### Next

- Run browser-level integration testing with a configured backend and database.

### Blocked

- Any capability that would require backend changes.
