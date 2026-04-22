# NL Query Agent — DVD Rental Database

A LangGraph-based multi-agent system that lets users query the PostgreSQL **DVD Rental** sample database in natural language. The system is built as **two specialized agents** that collaborate:

1. **Schema Agent** — auto-discovers the database schema, generates human-readable table/column descriptions via LLM, and uses **Human-in-the-Loop (HITL)** review before persisting them.
2. **Query Agent** — translates natural language questions into SQL, validates them (safety + schema + semantic), optionally confirms with the user for risky SQL, executes read-only queries, and presents results in natural language.

---

## Architecture diagram

```
                         ┌────────────────────────┐
                         │   Streamlit UI :8501   │
                         │  (chat + schema tabs)  │
                         └───────────┬────────────┘
                                     │ HTTP
                         ┌───────────▼────────────┐
                         │    FastAPI :8000       │
                         │                        │
    POST /chat ──────────┤   Query Agent Graph    │
    POST /schema/analyze ┤   Schema Agent Graph   │
    GET/PUT /preferences │                        │
                         └───────┬────────┬───────┘
                                 │        │
         ┌───────────────────────┘        └────────────────────┐
         │                                                     │
  ┌──────▼──────────────────────────┐         ┌────────────────▼─────────────┐
  │   Schema Agent StateGraph       │         │   Query Agent StateGraph     │
  │                                 │         │                              │
  │  planner ─► analyzer ─► review  │         │  planner ─► generator ─►     │
  │              ▲            │     │         │    critic ─► confirm ─►      │
  │              │   revise   │     │         │    executor ─► presenter     │
  │              └────────────┤     │         │                              │
  │                approved   ▼     │         │  critic fail ─► generator    │
  │              persister ─► END   │         │  reject ─► END               │
  │                                 │         │                              │
  │  [HITL interrupt_before         │         │  [conditional interrupt()    │
  │   on "review"]                  │         │   on "confirm"]              │
  └────────────┬────────────────────┘         └──────────┬───────────────────┘
               │                                         │
               └───────────────────┬─────────────────────┘
                                   │
                     ┌─────────────▼─────────────────┐
                     │     MCP Tools (stdio)         │
                     │                               │
                     │  • inspect_schema             │
                     │  • execute_sql (read-only)    │
                     │  • get_table_sample           │
                     └─────────────┬─────────────────┘
                                   │ psycopg
                  ┌────────────────▼─────────────────┐
                  │      PostgreSQL :5433            │
                  │                                  │
                  │  ┌──────────────┐ ┌───────────┐ │
                  │  │ public       │ │ agent_    │ │
                  │  │ (DVD Rental, │ │ metadata  │ │
                  │  │ 15 tables,   │ │ (prefs,   │ │
                  │  │ read-only)   │ │ schema    │ │
                  │  │              │ │ descs)    │ │
                  │  └──────────────┘ └───────────┘ │
                  └──────────────────────────────────┘
```

---

## Setup and run

### Prerequisites
- Docker Desktop running
- Python 3.13 (for host development; not needed if you use Docker only)
- `uv` package manager — `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 1. DVD Rental data
Download `dvdrental.sql` from the [Neon sample databases](https://neon.com/postgresql/postgresql-getting-started/postgresql-sample-database) page (direct URL: `https://raw.githubusercontent.com/neondatabase/postgres-sample-dbs/main/dvdrental.sql`) and save it to `data/dvdrental.sql`. PostgreSQL's Docker image auto-loads it on first startup.

### 2. Environment
```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY=sk-...  (LiteLLM proxy key)
```

### 3a. Full Docker run (API + UI + Postgres)
```bash
docker compose up -d
# UI:  http://localhost:8501
# API: http://localhost:8002/docs
```

### 3b. Development on host (with Postgres in Docker)
```bash
uv sync                               # install deps

docker compose up postgres -d         # start only Postgres

# Terminal 1 — FastAPI
PYTHONPATH=src \
DATABASE_URL=postgresql://dvdrental:dvdrental@localhost:5433/dvdrental \
uv run uvicorn api.main:get_app --factory --port 8000

# Terminal 2 — Streamlit
PYTHONPATH=src \
API_BASE_URL=http://localhost:8000 \
uv run streamlit run src/ui/app.py

# Tests
uv run pytest tests/

# Lint
uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/
```

### 4. Confirm DVD Rental is loaded
```bash
docker compose exec postgres psql -U dvdrental -d dvdrental -c "\dt"
# Should list the 15 DVD Rental tables (actor, address, category, ..., store)
```

---

## Memory design

The system uses two distinct memory subsystems, each with a different lifetime and purpose.

### Persistent Memory — [`src/memory/persistent.py`](src/memory/persistent.py)

**Backend:** PostgreSQL, `agent_metadata` schema. Survives process restarts and spans sessions.

| Table | Purpose | Used by |
|---|---|---|
| `user_preferences(user_id, preference_key, preference_value JSONB, updated_at)` | Per-user settings: `language`, `date_format`, `max_results`, `confirm_before_execute`, `show_sql` | Query Agent planner + generator + presenter; `/preferences/*` routes; Streamlit sidebar |
| `schema_descriptions(table_name, column_name, description, approved_by, approved_at)` | LLM-generated, human-approved descriptions of every table and column (`column_name='__table__'` marks a table-level description) | Schema Agent persister writes; Query Agent planner reads to ground SQL generation |

**Why persistent:** preferences and schema docs must survive restarts (a user's language setting or an approved description shouldn't disappear after a deploy). They're also shared across sessions of the same user.

### Short-term Memory — [`src/memory/short_term.py`](src/memory/short_term.py)

**Backend:** In-process Python dict keyed by `session_id`. Lost on restart.

`SessionContext` fields:
- `messages` — rolling window of the last `max_messages` (default 50) user/assistant turns
- `last_sql` — the SQL executed for the most recent question
- `last_query_plan` — the planner's step-by-step plan for that question
- `last_result_summary` — one-line description of the result ("5 row(s) returned")
- `assumptions`, `recent_tables`, `extra` — open-ended stash for future features

**Used by** Query Agent's planner (via the "follow-up hint" in its prompt) so questions like *"What about R-rated?"* can see the previous PG-rated SQL and refine it rather than starting from scratch. Result presenter writes into it after every completed query.

**Why short-term:** session context is per-conversation. Persisting it would bloat Postgres with data that's only useful for a few minutes, and mixing up "current session" with "historical sessions" would break follow-up semantics.

---

## MCP tools used

All PostgreSQL operations are wrapped in an **MCP server** ([`src/tools/mcp_server.py`](src/tools/mcp_server.py)) built with `FastMCP`. Agents never touch the database directly — they call named MCP tools with typed arguments. The server enforces `SET TRANSACTION READ ONLY` on every operation, so write queries are impossible even if an agent tries.

| Tool | Arguments | Purpose | Called by |
|---|---|---|---|
| `inspect_schema` | `table_name: str \| None` | Returns either the list of all `public` tables (no arg) or a single table's columns + PK + FKs + indexes + row count. Used for schema discovery, FK ordering, critic schema-existence checks. | Schema planner (list all), Schema analyzer (per-table detail), Query critic (existence check) |
| `execute_sql` | `sql: str, max_rows: int = 100, timeout_seconds: int = 30` | Validates SQL via `validate_sql_safety()`, sets `statement_timeout` + read-only transaction, executes, returns `{columns, rows, row_count, truncated, execution_time_ms}`. | Query executor |
| `get_table_sample` | `table_name: str, limit: int = 5` | Validates `table_name` against `information_schema.tables` (prevents injection), then returns up to `limit` sample rows + total count. | Schema analyzer (shows LLM real data before writing descriptions) |

**Integration with the graph:** Each agent node that needs data calls the corresponding MCP function directly (in-process for performance) or via the stdio pipeline when used as an LLM tool. Tool calls are logged at INFO level with the `[PLANNER]`/`[ANALYZER]`/`[EXECUTOR]` prefix so they appear in the graph trace.

**Safety:** The MCP server is the only component with database write permissions, and it refuses them. Even if the LLM hallucinates `DROP TABLE`, the layers of defense catch it:
1. `sql_safety.validate_sql_safety()` rejects anything not starting with `SELECT`/`WITH`
2. `SET TRANSACTION READ ONLY` on the connection rejects writes at the Postgres level
3. `statement_timeout` prevents runaway queries

---

## Agent patterns used

The system applies the patterns from class, with at least one per category:

### Planner / Executor separation
Both agents split planning from execution.
- **Schema Agent:** `schema_planner` decides *which* tables to document and *in what order* (FK topological sort); `schema_analyzer` then *executes* the plan by introspecting + prompting the LLM for each table.
- **Query Agent:** `query_planner` produces a step-by-step natural-language plan (*"join film with language, count rows..."*); `sql_generator` converts the plan into SQL. The critic/executor/presenter act on the generator's output.

### Human-in-the-Loop (HITL)
- **Schema Agent** *always* pauses at `schema_review` (`interrupt_before=["schema_review"]`). The user can `approve` (persist), `reject` (discard), or type free-form feedback (`revise` → analyzer re-runs with feedback embedded in every per-table prompt). Capped at 3 revision cycles.
- **Query Agent** has a *conditional* HITL at `sql_confirm` using LangGraph's modern `interrupt()`. It only pauses when the SQL is risky: **4+ table joins**, **no LIMIT clause**, or user preference `confirm_before_execute=true`. Otherwise auto-approves. This keeps the UX snappy for simple queries without giving up oversight on dangerous ones.

### Critic / Validator
The `sql_critic` node performs three layers of validation before execution:
1. **Code-based safety** — `validate_sql_safety()` rejects writes, multi-statements, comments, forbidden schemas, dangerous functions. Hard failure → routes to error response.
2. **Schema existence** — every FROM/JOIN target must match a real `public` table. Regex-based with false-positive tolerance (only fails if NO referenced name is a real table).
3. **LLM semantic check** — the LLM decides whether the SQL answers the user's question. This one is *advisory*: it surfaces as a suggestion, not a hard failure, to avoid infinite regen loops.

Failures in the first two layers loop back to `sql_generator` with the critic's feedback embedded in the prompt; after `max_iterations` (default 15) the graph routes to `error_response`.

### Supporting patterns
- **Retry with feedback** — critic failures don't give up; they feed issues + suggestions back into the regenerator.
- **Guardrails** — defense in depth (SQL safety module + read-only transaction + `statement_timeout` + row cap).
- **Structured logging** — every node emits `[PLANNER]`, `[ANALYZER]`, `[CRITIC]`, etc. so the graph's execution trace is visible.

---

## Demo

See [`docs/DEMO.md`](docs/DEMO.md) for a scripted end-to-end run covering:
- Schema documentation with a human revision cycle
- Three different NL queries (simple count, multi-table join, aggregation)
- One follow-up refinement using session context

See [`docs/REPORT.md`](docs/REPORT.md) for the 1–2 page design report, and
[`docs/spec.md`](docs/spec.md) for the original technical specification.

---

## Project layout

```
TP/
├── src/
│   ├── agent/
│   │   ├── schema_agent/    # Schema Agent: nodes, edges, graph, prompts
│   │   ├── query_agent/     # Query Agent: nodes, edges, graph, prompts
│   │   └── state.py         # Shared TypedDict state for both agents
│   ├── tools/
│   │   ├── mcp_server.py    # FastMCP server (inspect_schema, execute_sql, get_table_sample)
│   │   ├── mcp_client.py    # MultiServerMCPClient wrapper (stdio)
│   │   └── sql_safety.py    # Pure-Python SQL validator
│   ├── memory/
│   │   ├── persistent.py    # PostgreSQL-backed prefs + schema descriptions
│   │   └── short_term.py    # In-process SessionContext + ShortTermMemory
│   ├── api/
│   │   ├── main.py          # FastAPI app
│   │   └── routes/          # /chat, /schema/*, /preferences/*
│   ├── ui/
│   │   ├── app.py           # Streamlit entry point
│   │   ├── api_client.py    # httpx wrapper around the backend
│   │   └── components/      # sidebar, chat, schema_review
│   ├── llm/client.py        # ChatOpenAI wrapper for LiteLLM proxy
│   ├── config/settings.py   # pydantic-settings config
│   └── app_logging/         # logger + LangSmith integration
├── tests/
│   ├── unit/                # mocked unit tests (pure logic)
│   ├── functional/          # hit real DB
│   └── integration/         # hit real DB + LLM
├── containers/              # Dockerfile + Dockerfile.testing
├── data/                    # dvdrental.sql + init_metadata_schema.sql
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── README.md                # entry point (this file)
├── CLAUDE.md                # dev notes + known limitations + future improvements
└── docs/
    ├── REPORT.md            # 1–2 page design report
    ├── DEMO.md              # scripted demo scenarios
    └── spec.md              # original technical spec
```

---

## Tests

167 tests total (141 that run without an LLM key, 26 more when `LLM_API_KEY` is set):

```bash
uv run pytest tests/ -v
```

Split:
- **Unit** (no external deps): settings, LLM client, SQL safety, state shapes, schema nodes (mocked), query nodes (mocked), memory modules (mocked/DB), api_client (mocked httpx)
- **Functional** (real Postgres): `/health`, MCP tools (direct + stdio pipeline), preferences API, Schema Agent E2E, Query Agent E2E
- **Integration** (real Postgres + real LLM): full scenario (prefs → schema → query → follow-up), schema documentation with revision cycle, 4 demo NL queries
