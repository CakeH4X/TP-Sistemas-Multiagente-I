# CLAUDE.md — project instructions for Claude Code

## Project

Two-agent LangGraph system for natural language querying over the PostgreSQL DVD Rental sample database.

## Stack

Python 3.13, FastAPI, LangGraph, langchain-openai (via LiteLLM proxy), MCP tools, psycopg, Streamlit, pytest, ruff.

## Running

```bash
# Start Postgres
docker compose up postgres -d

# Start FastAPI (host)
PYTHONPATH=src DATABASE_URL=postgresql://dvdrental:dvdrental@localhost:5433/dvdrental uv run uvicorn api.main:get_app --factory --port 8000

# Start Streamlit (host)
PYTHONPATH=src API_BASE_URL=http://localhost:8000 uv run streamlit run src/ui/app.py

# Run tests
uv run pytest tests/

# Lint
uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/
```

## Key conventions

- Tests: `test_u_*` (unit, mocked), `test_f_*` (functional, real DB), `test_in_*` (integration, real DB + LLM)
- Settings: all config via pydantic-settings in `src/config/settings.py`
- Agents never touch DB directly — all DB ops go through MCP tools in `src/tools/mcp_server.py`
- SQL safety: `src/tools/sql_safety.py` validates before execution; only SELECT allowed
- HITL: Schema Agent uses `interrupt_before`; Query Agent uses modern `interrupt()` in `sql_confirm`

## Known limitations

### No database connection pooling

Every DB operation (`PersistentMemory`, `mcp_server` tools) opens a fresh `psycopg.connect()` and closes it when done. This is fine for the educational scope (single user, low concurrency) but would exhaust connections under real traffic. **To improve:** replace `_connect()` in both `memory/persistent.py` and `tools/mcp_server.py` with a `psycopg_pool.ConnectionPool` shared across the process.

### Graph singletons share in-memory checkpointer

Both `get_compiled_schema_graph()` and `get_compiled_query_graph()` are module-level singletons backed by `MemorySaver()`. This means all checkpoints live in RAM and are lost on restart. Thread IDs are unique per request so state doesn't leak between users, but checkpoint data grows unboundedly over the process lifetime. **To improve:** swap `MemorySaver` for a persistent checkpointer (e.g., `langgraph-checkpoint-postgres`) so state survives restarts and memory doesn't grow. For tests, reset the singleton between runs to avoid stale state.

### LLMClient re-instantiated per node

Each node calls `LLMClient().as_model()`, which creates a new `ChatOpenAI` wrapper every time. The underlying `httpx` session is not reused across nodes within a single graph invocation. This is negligible overhead (no TCP reconnection — `httpx` handles pooling internally) but wasteful in principle. **To improve:** make `LLMClient` a singleton via `get_llm_client()`, similar to `get_settings()`.

### PersistentMemory re-instantiated per route

API routes create `PersistentMemory()` on every request, which runs `_ensure_tables()` (idempotent DDL) each time. Safe but redundant after the first call. **To improve:** cache a singleton instance, same pattern as `get_short_term_memory()`.

### FROM/JOIN table extraction is regex-based

The SQL critic uses a regex to find table names after FROM/JOIN. This produces false positives for `EXTRACT(... FROM column_name)` and similar SQL constructs. The current mitigation is lenient: only flag an error when *no* extracted reference matches a real table. **To improve:** use a proper SQL parser like `sqlglot` to extract table references reliably.

### Schema Agent processes tables sequentially

The `schema_analyzer` node calls the LLM once per table, sequentially. For 15 tables this takes ~30s. **To improve:** batch tables into fewer LLM calls (e.g., 5 tables per prompt) or use `asyncio.gather` for concurrent calls.

### Short-term memory is process-local

`ShortTermMemory` stores session context in a Python dict — lost on restart, not shared across workers. Fine for single-process uvicorn but breaks with multiple workers. **To improve:** back session context with Redis or a PostgreSQL table (similar to `PersistentMemory`).

### Spec references `dvdrental.tar` but implementation uses `dvdrental.sql`

The spec (§13.1) describes a `pg_restore` flow from a `.tar` dump. The actual implementation uses a plain `.sql` file from the Neon sample database, which PostgreSQL's Docker init mechanism executes directly. Both achieve the same result (15 DVD Rental tables loaded). The restore shell script (`dvdrental_restore.sh`) was removed as unnecessary.

### Conditional HITL heuristic is simple

The `_needs_confirmation()` function triggers HITL if: no LIMIT clause, 4+ table joins, or user preference. This can be overly aggressive (e.g., `COUNT(*)` without LIMIT is always safe but triggers review) or miss risky queries (e.g., Cartesian joins on 2 tables). **To improve:** analyze the query plan cost via `EXPLAIN` before deciding, or use the LLM to assess risk.

### Logging level mapping is explicit

The `configure_logging()` function maps environment names to log levels via a dict (`development → DEBUG`, `production → WARNING`). Unknown environments default to INFO. This is deliberate but means custom environment names (e.g., `"preview"`) silently fall back to INFO. **To improve:** add a dedicated `LOG_LEVEL` env var for explicit control.

## Future improvements

- **Streaming responses** — use LangGraph's streaming mode + SSE to show the agent's progress in real time (planner thinking, SQL being generated, results arriving) instead of a single spinner
- **Pagination** — add cursor-based pagination to `/chat` responses and `st.dataframe` so users can browse large result sets
- **Query history** — persist executed queries + results in `agent_metadata` so users can revisit past sessions
- **Multi-language schema descriptions** — generate descriptions in the user's preferred language, not just English
- **Auth** — add API key or JWT auth to protect endpoints; currently all routes are open
- **Caching** — cache `inspect_schema()` results (schema rarely changes) to skip repeated DB introspection
- **Write operations** — extend with a safe write agent for INSERT/UPDATE behind strict HITL + approval chains
- **Observability dashboard** — integrate LangSmith tracing with a Grafana panel showing agent latency, LLM token usage, and error rates
