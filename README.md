# GuidLoc

AI-powered place recommendation backend for Chernivtsi, Ukraine. Users describe what they want in natural language and get a personalised answer — venues, routes, food, gifts, dates, walks.

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.x async |
| Migrations | Alembic (SQLite batch mode) |
| Database | SQLite (aiosqlite) |
| AI | OpenAI Agents SDK (`openai-agents`) |
| Auth | JWT (access 24 h + refresh 30 d) |
| Validation | Pydantic v2 |
| Tooling | `uv` + Taskfile |
| Tests | pytest + pytest-asyncio + httpx |

## Project structure

```
src/guidloc/
├── main.py              # FastAPI app factory, /health endpoint
├── common/              # config, database, logging, base models
├── auth/                # registration, login, JWT, refresh token
├── users/               # user profile
├── chats/               # chats and messages
├── memory/              # user memory (UserProfile + UserMemoryItem)
├── locations/           # Chernivtsi locations
└── agents/
    ├── base.py          # AgentContext, StreamEvent, LLMProvider Protocol
    ├── factory.py       # get_llm_provider() → echo | openai
    ├── runner.py        # send_user_message, stream_user_message
    ├── openai_agent.py  # Orchestrator + PlacesAgent (OpenAI Agents SDK)
    ├── echo.py          # EchoLLMProvider for tests
    ├── common_tools.py  # get_current_datetime, get_weather
    ├── memory_tools.py  # read/save/forget memory, update_user_profile
    └── tools.py         # search_locations
migrations/              # Alembic versions
scripts/
└── seed_locations.py    # idempotent seed: 8 real Chernivtsi locations
tests/                   # pytest, ~100% coverage of implemented modules
```

## Agent architecture

```
User message
     │
     ▼
OrchestratorAgent
  ├─ read_user_memory
  ├─ save_memory_item / forget_memory_item / update_user_profile
  ├─ get_current_datetime, get_weather
  └─ handoff ──► PlacesAgent
                  ├─ search_locations (DB)
                  ├─ WebSearchTool (fallback, SDK built-in)
                  ├─ get_current_datetime, get_weather
                  └─ read_confirmed_memory
```

**Providers:**
- `OpenAIAgentsProvider` — real GPT, `Runner.run_streamed`, `ModelSettings(parallel_tool_calls=False)`
- `EchoLLMProvider` — deterministic, no API key required; used in tests

**Factory** (`get_llm_provider`): returns the OpenAI provider when `LLM_PROVIDER=openai` and `OPENAI_API_KEY` is set, otherwise falls back to Echo.

## SSE streaming

`POST /chats/{id}/send` returns `text/event-stream`.

Event sequence:
```
event: user_message   data: {"message": {...}}
event: agent          data: {"name": "OrchestratorAgent"}
event: tool_call      data: {"name": "read_user_memory", "args": {...}}
event: tool_output    data: {"name": "read_user_memory", "ok": true, "summary": "..."}
event: delta          data: {"text": "Here are a few ideas..."}
event: delta          data: {"text": " in the city centre."}
event: done           data: {"assistant_message": {...}}
```
On error: `event: error  data: {"message": "..."}`. The user message is already persisted; the assistant message is not.

## User memory

**UserProfile** — static fields: `preferred_name`, `date_of_birth`, `phone`, `address_text`.

**UserMemoryItem** — dynamic facts:

| Field | Values |
|---|---|
| `section` | `rule` / `preference` / `user_info` / `note` |
| `status` | `possible` (Orchestrator only) / `confirmed` / `archived` |
| `value` | short fact sentence |

Items are archived (not deleted) when `forget_memory_item` is called.

## Locations

`Location` — places in Chernivtsi: `name`, `description`, `address`, `lat/lng`, `category`, `price_level`, `tags` (JSON), `is_active`.

**Filters for `GET /locations`:** `categories`, `price_levels`, `tags` (AND-match), `query` (substring search on name + description), `limit`, `offset`.

**Seed:** 8 real locations — `task seed`.

## API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | service status + DB check |
| `POST` | `/auth/register` | register |
| `POST` | `/auth/login` | login, returns access + refresh tokens |
| `POST` | `/auth/refresh` | refresh access token |
| `GET` | `/auth/me` | current user |
| `GET/PATCH` | `/users/me` | user profile |
| `POST/GET` | `/chats` | create / list chats |
| `GET/PATCH/DELETE` | `/chats/{id}` | detail, update, delete |
| `GET/POST` | `/chats/{id}/messages` | list / create messages |
| `POST` | `/chats/{id}/send` | **SSE streaming** — send message to agent |
| `GET` | `/locations` | search locations with filters |
| `GET` | `/locations/{id}` | location detail |
| `GET` | `/users/me/memory` | memory snapshot |
| `PATCH` | `/users/me/profile` | update UserProfile |
| `POST` | `/users/me/memory/items` | add memory item |
| `PATCH` | `/users/me/memory/items/{id}` | update item |
| `DELETE` | `/users/me/memory/items/{id}` | archive item |

## Quick start

```bash
cp .env.example .env
uv sync
task migrate
task seed   # optional
task dev
```

API docs: http://localhost:8000/docs  
Health check: http://localhost:8000/health

## Environment variables

```dotenv
APP_ENV=local
APP_DEBUG=true
DATABASE_URL=sqlite+aiosqlite:///./guidloc.db

JWT_SECRET=change-me-in-production

# echo (default, no OpenAI) or openai
LLM_PROVIDER=echo
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
AGENT_MAX_TURNS=40
```

## Tasks

| Command | Action |
|---|---|
| `task dev` | start server with hot-reload |
| `task test` | run test suite |
| `task lint` | ruff linter |
| `task format` | ruff format + auto-fix |
| `task migrate` | apply all pending migrations |
| `task migration -- "message"` | generate a new Alembic revision |
| `task db-reset` | drop DB and re-apply all migrations |
| `task seed` | load starter locations |

## Tests

```bash
task test
```

Tests always use `EchoLLMProvider` (`LLM_PROVIDER=echo`, no `OPENAI_API_KEY`) — OpenAI is never called. The database is an in-memory SQLite instance isolated per test.