## 1. Project Overview

### 1.1 Goal

Build a **two-agent LangGraph system** that enables natural language querying over the PostgreSQL **DVD Rental** sample database. The system consists of:

1. **Schema Agent** -- Inspects, documents, and enriches the database schema with human-readable descriptions. Uses Human-in-the-Loop (HITL) for review and approval of generated descriptions.
2. **Query Agent** -- Translates natural language questions into SQL, validates them, optionally confirms with the user, executes read-only queries, and presents results in natural language.

Each agent is its own **independent `StateGraph`**. Since the database schema rarely changes, the Schema Agent runs infrequently while the Query Agent is invoked repeatedly. The FastAPI layer selects which graph to invoke based on the endpoint (e.g., `/schema/analyze` vs `/chat`).

Both agents share a common MCP (Model Context Protocol) tool server that wraps all PostgreSQL operations (schema inspection and read-only SQL execution). The system demonstrates persistent memory (user preferences across sessions), short-term memory (session context), and multiple agent patterns (Planner/Executor, HITL, Critic/Validator).

### 1.2 What This Project Demonstrates

- Multi-agent orchestration with LangGraph (two distinct, independently invocable `StateGraph`s)
- MCP tools for database operations (schema introspection, SQL execution)
- Human-in-the-Loop review checkpoints using LangGraph `interrupt`
- Persistent memory in PostgreSQL (user preferences, approved schema descriptions)
- Short-term memory (session context with message history)
- Agent patterns: Planner/Executor, Critic/Validator, HITL
- Safe read-only SQL execution with guardrails
- Structured observability and logging
- Interactive web UI (Streamlit) with chat interface and HITL review panels

### 1.3 Out of Scope

- No OpenAI SDK usage directly (all LLM calls via LangChain `ChatOpenAI` through LiteLLM proxy)
- No schema migration tool (tables created via init scripts)
- No write operations on the DVD Rental database (strictly read-only)

---

## 2. Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------| 
| **Language** | Python `3.13+` (`>=3.13,<3.14`) | Runtime |
| **Package manager** | `uv` (`pyproject.toml` + `uv sync`) | Dependency management |
| **HTTP API** | `FastAPI` | REST endpoints |
| **Agent orchestration** | `langgraph` (`StateGraph`) | Multi-agent graphs |
| **LLM abstraction** | `langchain-openai` (`ChatOpenAI`) | LLM client via LiteLLM proxy |
| **MCP tools** | `mcp` Python SDK + `langchain-mcp-adapters` | Tool server for PostgreSQL operations |
| **Database** | PostgreSQL 16 (DVD Rental sample) | Target query database + metadata storage |
| **DB driver** | `psycopg[binary]>=3.1.0` | PostgreSQL connectivity |
| **Observability** | `langsmith` (via LangChain env vars) + Python `logging` | Tracing and structured logging |
| **Testing** | `pytest` (plain functions, Given/When/Then) | Unit + functional + integration tests |
| **Web UI** | `streamlit>=1.38.0` | Interactive chat interface + HITL review |
| **Lint/format** | `ruff` | Code quality |

---

## 3. Configuration

All configuration is centralized in `src/config/settings.py` using `pydantic-settings`.

### 3.1 Environment Variables (`.env.example`)

```env
# LLM (LiteLLM proxy)
LLM_SERVICE_URL=https://sa-llmproxy.it.itba.edu.ar
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4.1-mini

# LangSmith tracing
LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=nl-query-agent

# Graph execution
GRAPH_MAX_ITERATIONS=15

# Database - DVD Rental (read-only target)
DATABASE_URL=postgresql://dvdrental:dvdrental@postgres:5432/dvdrental

# Database - Metadata store (same PostgreSQL instance, separate schema)
METADATA_SCHEMA=agent_metadata

# Application
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# SQL Safety
SQL_MAX_ROWS=100
SQL_TIMEOUT_SECONDS=30

# Streamlit UI
STREAMLIT_PORT=8501
API_BASE_URL=http://nl-query-agent:8000
```

### 3.2 Settings Module Requirements (`src/config/settings.py`)

Implement the following settings classes following the pattern from the EJ02-ReAct-LangGraph project at `/Users/saints/Desktop/ITBA/Multiagente/demos-estudiantes/EJ02-ReAct-LangGraph-resuelto/src/config/settings.py`:

- **`LLMSettings`** with `env_prefix="LLM_"` and aliases:
  - accept `LLM_BASE_URL` or `LLM_SERVICE_URL` for `base_url` via `AliasChoices`
  - `api_key: str` (default `""`)
  - `model: str` (default `"gpt-4.1-mini"`)
- **`LangSmithSettings`** with `env_prefix="LANGSMITH_"`
  - `tracing: bool` (default `False`), `endpoint`, `api_key`, `project`
- **`GraphSettings`** with `env_prefix="GRAPH_"`
  - `max_iterations: int` (default `15`)
- **`DatabaseSettings`** with no prefix, explicit fields:
  - `database_url: str` with `validation_alias="DATABASE_URL"`
  - `metadata_schema: str` with `validation_alias="METADATA_SCHEMA"` (default `"agent_metadata"`)
- **`ApplicationSettings`** with no prefix:
  - `api_host`, `api_port`, `environment`
- **`SQLSafetySettings`** with `env_prefix="SQL_"`
  - `max_rows: int` (default `100`), `timeout_seconds: int` (default `30`)
- **`StreamlitSettings`** with no prefix:
  - `streamlit_port: int` with `validation_alias="STREAMLIT_PORT"` (default `8501`)
  - `api_base_url: str` with `validation_alias="API_BASE_URL"` (default `"http://localhost:8000"`)
- **`Settings`** top-level class composing all sub-settings
- **`get_settings()`** module-level singleton accessor that caches in a global

---

## 4. Project Layout

```
TP/
  pyproject.toml
  uv.lock
  README.md
  CLAUDE.md
  .env.example
  .python-version
  .dockerignore
  docker-compose.yml
  containers/
    Dockerfile
    Dockerfile.testing
  data/
    dvdrental_restore.sh
    dvdrental.tar
    init_metadata_schema.sql
  docs/
    specs/
      00-project-structure.md
      01-nl-query-system.md
    README.md
  scripts/
    README.md
  src/
    __init__.py
    config/
      __init__.py
      settings.py
    llm/
      __init__.py
      client.py
    agent/
      __init__.py
      state.py
      schema_agent/
        __init__.py
        graph.py
        nodes.py
        edges.py
        prompts.py
      query_agent/
        __init__.py
        graph.py
        nodes.py
        edges.py
        prompts.py
    tools/
      __init__.py
      mcp_server.py
      mcp_client.py
      sql_safety.py
    memory/
      __init__.py
      persistent.py
      short_term.py
    api/
      __init__.py
      main.py
      routes/
        __init__.py
        chat.py
        schema.py
        preferences.py
    app_logging/
      __init__.py
      logger.py
      langsmith.py
    ui/
      __init__.py
      app.py
      components/
        __init__.py
        chat.py
        schema_review.py
        sidebar.py
      api_client.py
  tests/
    __init__.py
    conftest.py
    unit/
      __init__.py
      test_u_state.py
      test_u_schema_nodes.py
      test_u_query_nodes.py
      test_u_sql_safety.py
      test_u_memory_persistent.py
      test_u_memory_short_term.py
      test_u_settings.py
      test_u_llm_client.py
    functional/
      __init__.py
      test_f_mcp_tools.py
      test_f_health.py
      test_f_schema_agent.py
      test_f_query_agent.py
    integration/
      __init__.py
      conftest.py
      test_in_full_scenario.py
      test_in_schema_documentation.py
      test_in_nl_queries.py
```

---

## 5. Architecture

### 5.1 Component Diagram

```
+----------------------------------------------+
|          Streamlit Web UI (:8501)             |
|  +----------------------------------------+  |
|  | Chat Tab | Schema Tab | Preferences    |  |
|  | (query   | (analyze + | Sidebar        |  |
|  |  agent)  |  HITL      |                |  |
|  |          |  review)   |                |  |
|  +-----+----------+-----+----------------+  |
+--------|----------|---------------------------+
         | HTTP     | HTTP
+--------v----------v--------------------------+
|                FastAPI Server (:8000)          |
|  +------------------------------------------+ |
|  | POST /chat  POST /schema/analyze         | |
|  | GET /schema/descriptions  GET /prefs     | |
|  +-------+--------------------+-------------+ |
|          |                    |                |
|  +-------v-----------+ +-----v-----------+   |
|  | Query Agent Graph  | | Schema Agent    |   |
|  | (StateGraph)       | | Graph           |   |
|  |                    | | (StateGraph)    |   |
|  | Planner->Generator | | Planner->       |   |
|  |  ->Critic/Validator| |  Analyzer->     |   |
|  |  ->HITL Confirm    | |  HITL Review->  |   |
|  |  ->Executor        | |  Persister      |   |
|  |  ->Presenter       | |                 |   |
|  +--------+-----------+ +-------+---------+   |
|           |                     |              |
|  +--------v---------------------v----------+  |
|  |           MCP Tool Client                |  |
|  +-------------------+---------------------+  |
|                      | stdio                   |
|  +-------------------v---------------------+  |
|  |           MCP Tool Server                |  |
|  | inspect_schema | execute_sql |           |  |
|  | get_table_sample                         |  |
|  +-------------------+---------------------+  |
+----------------------|-------------------------+
                       |
    +------------------v--------------------+
    |         PostgreSQL 16                  |
    |  +------------+ +------------------+  |
    |  | dvdrental  | | agent_metadata   |  |
    |  | (15 tables)| | (preferences,    |  |
    |  |            | |  descriptions)   |  |
    |  +------------+ +------------------+  |
    +---------------------------------------+
```

### 5.2 Data Flow — Query Agent

1. User types a natural language question in the Streamlit chat interface
2. Streamlit sends the message to the FastAPI backend via `POST /chat` with `session_id` and `user_id`
2. Short-term memory loads session context; persistent memory loads user preferences
3. Query Agent graph executes: planner -> generator -> critic -> (optional HITL) -> executor -> presenter
4. MCP tools handle all database operations
5. Results flow back through the presenter node, formatted according to user preferences
6. Session context is updated in short-term memory
7. Streamlit displays the response in the chat, optionally with SQL code block and data table

### 5.3 Data Flow — Schema Agent

1. User clicks "Analyze Schema" in the Streamlit Schema tab
2. Streamlit sends a request to `POST /schema/analyze`
3. Schema Agent **automatically discovers** all tables in the `public` schema via MCP `inspect_schema()`
4. Agent drafts natural language descriptions for every table and column
5. Graph hits HITL interrupt — Streamlit renders descriptions in a review panel with Approve/Revise controls
6. User reviews, approves (or requests revisions); Streamlit resumes the graph via `POST /schema/analyze` with `thread_id`
7. Approved descriptions are persisted to `agent_metadata.schema_descriptions` for reuse by the Query Agent

---

## 6. LangGraph Graph Design

### 6.1 Shared State Base (`src/agent/state.py`)

Define a shared `TypedDict` base that both graphs extend, following the pattern from `/Users/saints/Desktop/ITBA/Multiagente/demos-estudiantes/EJ02-ReAct-LangGraph-resuelto/src/agent/state.py`:

```python
class BaseAgentState(TypedDict, total=False):
    # Core message history
    messages: Annotated[list[AnyMessage], add_messages]

    # Session metadata
    session_id: str
    user_id: str

    # Memory
    user_preferences: dict
    session_context: dict

    # Control flow
    iteration: int
    max_iterations: int
    error: str | None


class SchemaAgentState(BaseAgentState, total=False):
    # Schema Agent fields
    target_tables: list[str]
    schema_info: dict
    generated_descriptions: dict
    approved_descriptions: dict
    schema_review_status: str  # "pending" | "approved" | "rejected" | "revised"


class QueryAgentState(BaseAgentState, total=False):
    # Query Agent fields
    query_plan: str
    generated_sql: str
    sql_validation: dict
    sql_approved: bool
    query_result: dict
    formatted_response: str
```

Define `initial_schema_state()` and `initial_query_state()` factory functions that create state from a user message, session_id, user_id, and loaded preferences, setting `iteration=0`.

### 6.2 Schema Agent Graph (`src/agent/schema_agent/graph.py`)

Implements the **Planner/Executor** pattern with **HITL**.

**Nodes:**

1. **`schema_planner`** -- Automatically discovers all tables via MCP `inspect_schema()` (no argument). Orders them by FK dependency. Sets `target_tables` to the full list.
2. **`schema_analyzer`** -- For each table in `target_tables`, calls MCP `inspect_schema(table_name)` and `get_table_sample(table_name, limit=5)`. Uses LLM to generate human-readable descriptions. Sets `generated_descriptions`.
3. **`schema_review`** -- **HITL checkpoint**. Uses `interrupt` to pause and present descriptions to user. User responds with approve, reject, or revision instructions.
4. **`schema_persister`** -- Writes approved descriptions to `agent_metadata.schema_descriptions` via persistent memory module. Uses upsert for idempotency.

**Edges (`src/agent/schema_agent/edges.py`):**

`route_after_schema_review(state)`:
- If `schema_review_status == "approved"`: return `"approved"` (routes to schema_persister)
- If `schema_review_status == "revised"` and `iteration < 3`: return `"revise"` (routes back to schema_analyzer)
- Otherwise: return `"end"` (abandon after 3 revision cycles)

**Graph wiring:**

```python
def build_schema_graph() -> StateGraph:
    graph = StateGraph(SchemaAgentState)

    graph.add_node("schema_planner", schema_planner)
    graph.add_node("schema_analyzer", schema_analyzer)
    graph.add_node("schema_review", schema_review)
    graph.add_node("schema_persister", schema_persister)

    graph.set_entry_point("schema_planner")

    graph.add_edge("schema_planner", "schema_analyzer")
    graph.add_edge("schema_analyzer", "schema_review")
    graph.add_conditional_edges("schema_review", route_after_schema_review, {
        "approved": "schema_persister",
        "revise": "schema_analyzer",
        "end": END,
    })
    graph.add_edge("schema_persister", END)

    return graph


def get_compiled_schema_graph():
    graph = build_schema_graph()
    return graph.compile(
        interrupt_before=["schema_review"],
        checkpointer=MemorySaver(),
    )
```

### 6.3 Query Agent Graph (`src/agent/query_agent/graph.py`)

Implements **Planner/Executor** with **Critic/Validator**.

**Nodes:**

1. **`query_planner`** -- Analyzes the NL question. Loads schema descriptions from persistent memory. Checks session context for follow-up detection. Creates a query plan.
2. **`sql_generator`** -- Generates SQL from the plan using LLM. Schema descriptions, sample data (via MCP), and user preferences inform generation.
3. **`sql_critic`** -- Validates generated SQL:
   - Code-based safety check via `sql_safety.validate_sql_safety()`
   - Schema validation via MCP `inspect_schema` (verify tables/columns exist)
   - LLM-based semantic check (does the SQL answer the question?)
   - Returns `sql_validation` with `status` ("passed"/"failed"), `issues`, `suggestions`
4. **`sql_confirm`** -- Conditional HITL. Only interrupts if the query involves 4+ table joins, has no LIMIT, or user preference `confirm_before_execute` is `true`. Otherwise auto-approves.
5. **`sql_executor`** -- Calls MCP `execute_sql(sql, max_rows, timeout)`. On error sets `error`.
6. **`result_presenter`** -- Formats results in natural language. Stores executed SQL and result summary in session context for follow-up queries.

**Edges (`src/agent/query_agent/edges.py`):**

`route_after_critic(state)`:
- If `sql_validation.status == "passed"`: return `"passed"` (routes to sql_confirm)
- If `sql_validation.status == "failed"` and `iteration < max_iterations`: return `"failed"` (routes back to sql_generator with feedback)
- If `sql_validation.status == "failed"` and `iteration >= max_iterations`: return `"error"` (routes to error_response)

`route_after_confirm(state)`:
- If `sql_approved == True`: return `"confirmed"` (routes to sql_executor)
- If `sql_approved == False`: return `"rejected"` (routes to END)

**Graph wiring:**

```python
def build_query_graph() -> StateGraph:
    graph = StateGraph(QueryAgentState)

    graph.add_node("query_planner", query_planner)
    graph.add_node("sql_generator", sql_generator)
    graph.add_node("sql_critic", sql_critic)
    graph.add_node("sql_confirm", sql_confirm)
    graph.add_node("sql_executor", sql_executor)
    graph.add_node("result_presenter", result_presenter)
    graph.add_node("error_response", error_response)

    graph.set_entry_point("query_planner")

    graph.add_edge("query_planner", "sql_generator")
    graph.add_edge("sql_generator", "sql_critic")
    graph.add_conditional_edges("sql_critic", route_after_critic, {
        "passed": "sql_confirm",
        "failed": "sql_generator",
        "error": "error_response",
    })
    graph.add_conditional_edges("sql_confirm", route_after_confirm, {
        "confirmed": "sql_executor",
        "rejected": END,
    })
    graph.add_edge("sql_executor", "result_presenter")
    graph.add_edge("result_presenter", END)
    graph.add_edge("error_response", END)

    return graph


def get_compiled_query_graph():
    graph = build_query_graph()
    return graph.compile(
        interrupt_before=["sql_confirm"],
        checkpointer=MemorySaver(),
    )
```

---

## 7. Schema Agent Specification

### 7.1 Purpose

Inspects the DVD Rental database schema and generates human-readable documentation for tables and columns. Uses HITL so the user can review, approve, or request revisions.

### 7.2 Schema Planner Node

**System prompt** (`src/agent/schema_agent/prompts.py`):
```
You are a database schema documentation planner. Your job is to discover
and document the complete schema of the DVD Rental database.
Call inspect_schema() to discover all tables, then plan the documentation
order (respecting FK dependencies so referenced tables are described first).
```

**Behavior:**
- Calls MCP `inspect_schema()` (no args) to **automatically discover all tables** in the `public` schema
- Orders tables by FK dependency (leaf tables first, so descriptions can reference already-documented parents)
- Sets `target_tables` to the full ordered list — the user does not select tables

### 7.3 Schema Analyzer Node

**Behavior:**
- For each table in `target_tables`:
  - Calls MCP `inspect_schema(table_name)` for columns, types, constraints, FKs
  - Calls MCP `get_table_sample(table_name, limit=5)` for example data
- Uses the LLM to generate:
  - Table-level description (purpose, typical use)
  - Column-level descriptions (what each column represents, data format notes)
  - Relationship descriptions (how FKs connect tables)
- Sets `generated_descriptions` in state

### 7.4 Schema Review Node (HITL)

- Uses LangGraph `interrupt` to pause execution
- The API returns the generated descriptions to the user for review
- User responds with: `approve`, `reject`, or revision instructions
- On resume: sets `schema_review_status` accordingly and includes feedback for the analyzer to retry if revised
- After 3 revision cycles: force end

### 7.5 Schema Persister Node

- Writes approved descriptions to `agent_metadata.schema_descriptions` table
- Uses `INSERT ... ON CONFLICT UPDATE` for idempotency
- Emits a confirmation message

---

## 8. Query Agent Specification

### 8.1 Purpose

Translates natural language questions into SQL, validates, executes, and presents results.

### 8.2 Query Planner Node

**System prompt** (`src/agent/query_agent/prompts.py`):
```
You are a SQL query planner for the DVD Rental database. Given a natural
language question, create a step-by-step plan for the SQL query.

Available schema context:
{schema_descriptions}

Consider:
- Which tables are needed
- What JOINs are required
- What WHERE conditions apply
- Whether aggregation (GROUP BY, COUNT, SUM, AVG) is needed
- What ORDER BY and LIMIT to apply

User preferences:
- Language: {preferred_language}
- Date format: {preferred_date_format}
```

**Behavior:**
- Loads schema descriptions from persistent memory
- Checks session context for recent queries (follow-up detection)
- If the question references a previous query ("show me more", "filter by..."), incorporates the prior SQL as context
- Produces a structured query plan in `query_plan`

### 8.3 SQL Generator Node

**System prompt:**
```
You are a SQL generator for PostgreSQL. Convert the query plan into a
single SELECT statement.

Rules:
- Only SELECT statements. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE.
- Always include LIMIT {max_rows} unless the user explicitly asks for all results.
- Use explicit column names (no SELECT *).
- Use table aliases for readability.
- Format dates according to user preference: {date_format}.
- All table names refer to the public schema of the dvdrental database.
```

### 8.4 SQL Critic Node (Critic/Validator Pattern)

**Code-based validation** (`src/tools/sql_safety.py`):

```python
def validate_sql_safety(sql: str) -> tuple[bool, list[str]]:
    """Returns (is_safe, list_of_issues)."""
```

Checks:
- Must start with SELECT (after stripping whitespace)
- Rejects write keywords: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, COPY
- Rejects system schemas: pg_catalog, information_schema, agent_metadata
- Rejects semicolons (multi-statement)
- Rejects `--` or `/*` comments (injection vector)
- Rejects dangerous functions: `pg_sleep`, `pg_terminate_backend`

**Schema validation**: Verifies referenced tables/columns exist via MCP `inspect_schema`.

**LLM-based semantic validation**: Asks the LLM to confirm the SQL answers the original question.

Returns `sql_validation` dict with `status` ("passed"/"failed"), `issues` list, and `suggestions`.

### 8.5 SQL Confirm Node (Conditional HITL)

Only triggers `interrupt` if:
- The query involves 4+ table joins, OR
- The query has no LIMIT clause, OR
- User preference `confirm_before_execute` is `true`

Otherwise: auto-approves (sets `sql_approved = True`).

### 8.6 SQL Executor Node

- Calls MCP `execute_sql(sql, max_rows, timeout)` tool
- On success: sets `query_result` with columns and rows
- On error: sets `error` with the database error message, routes to error_response

### 8.7 Result Presenter Node

**System prompt:**
```
You are a data analyst presenting SQL query results to a non-technical user.
Present in {preferred_language}. Format dates as {preferred_date_format}.
If many rows, summarize key findings. If empty, explain possible reasons.
Include the SQL executed (in a code block) for transparency.
```

Stores the executed SQL and result summary in session context for follow-up queries.

---

## 9. MCP Tools Specification

### 9.1 MCP Server (`src/tools/mcp_server.py`)

Implement a standalone MCP server using the `mcp` Python SDK. Runs as a subprocess spawned by the main application (stdio transport).

**Tools exposed:**

#### `inspect_schema`

- **Args:** `table_name: str | None = None`
- **Returns (when table_name is None):** `{"tables": ["actor", "address", ...]}`
- **Returns (when table_name given):** `{"table_name": str, "columns": [...], "primary_key": [...], "foreign_keys": [...], "indexes": [...], "row_count": int}`
- **Implementation:** Queries `information_schema.tables`, `information_schema.columns`, constraint and FK metadata from `information_schema`, `pg_stats` for row count. Only returns tables in `public` schema.

#### `execute_sql`

- **Args:** `sql: str, max_rows: int = 100, timeout_seconds: int = 30`
- **Returns:** `{"columns": [...], "rows": [...], "row_count": int, "truncated": bool, "execution_time_ms": float}`
- **Implementation:** Sets `SET TRANSACTION READ ONLY` before executing. Applies `statement_timeout`. Rejects non-SELECT statements. Wraps with LIMIT enforcement if missing.

#### `get_table_sample`

- **Args:** `table_name: str, limit: int = 5`
- **Returns:** `{"table_name": str, "columns": [...], "rows": [...], "total_rows": int}`
- **Implementation:** Validates `table_name` against `information_schema.tables` before use. Executes in read-only transaction.

### 9.2 MCP Client (`src/tools/mcp_client.py`)

Uses `langchain-mcp-adapters` to connect to the MCP server and expose tools as LangChain-compatible tools:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

async def get_mcp_tools():
    client = MultiServerMCPClient({
        "dvdrental": {
            "command": "python",
            "args": ["-m", "tools.mcp_server"],
            "transport": "stdio",
        }
    })
    return await client.get_tools()
```

### 9.3 SQL Safety Module (`src/tools/sql_safety.py`)

Standalone module (no LLM dependency). Validates SQL with regex/token scanning:

```python
def validate_sql_safety(sql: str) -> tuple[bool, list[str]]:
    """Returns (is_safe, list_of_issues)."""
```

---

## 10. Memory Implementation

### 10.1 Persistent Memory (`src/memory/persistent.py`)

Backed by PostgreSQL in the `agent_metadata` schema. Following the pattern from `/Users/saints/Desktop/ITBA/Multiagente/demos-estudiantes/DEMO02-memory/src/memory/episodic.py`.

#### User Preferences Table

```sql
CREATE TABLE IF NOT EXISTS agent_metadata.user_preferences (
    user_id VARCHAR(255) NOT NULL,
    preference_key VARCHAR(255) NOT NULL,
    preference_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, preference_key)
);
```

Default preferences (set on first interaction):
- `language`: `"en"`
- `date_format`: `"YYYY-MM-DD"`
- `max_results`: `50`
- `confirm_before_execute`: `false`
- `show_sql`: `true`

#### Schema Descriptions Table

```sql
CREATE TABLE IF NOT EXISTS agent_metadata.schema_descriptions (
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255) NOT NULL DEFAULT '__table__',
    description TEXT NOT NULL,
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (table_name, column_name)
);
```

Convention: `column_name = '__table__'` means table-level description.

**API:**
```python
class PersistentMemory:
    def __init__(self) -> None: ...  # ensures tables exist
    def get_user_preferences(self, user_id: str) -> dict: ...
    def set_user_preference(self, user_id: str, key: str, value: Any) -> None: ...
    def get_schema_descriptions(self, table_name: str | None = None) -> dict: ...
    def save_schema_descriptions(self, descriptions: dict, approved_by: str) -> None: ...
```

Uses `psycopg` with `dict_row` factory, same connection pattern as DEMO02-memory.

### 10.2 Short-Term Memory (`src/memory/short_term.py`)

In-memory session state, scoped by `session_id`. Does not survive process restarts.

```python
class SessionContext:
    messages: list[dict[str, str]]
    last_sql: str | None
    last_query_plan: str | None
    last_result_summary: str | None
    assumptions: list[str]
    recent_tables: set[str]

class ShortTermMemory:
    def __init__(self, max_messages: int = 50): ...
    def get_session(self, session_id: str) -> SessionContext: ...
    def add_message(self, session_id: str, role: str, content: str) -> None: ...
    def get_messages(self, session_id: str) -> list[dict]: ...
    def set_context(self, session_id: str, key: str, value: Any) -> None: ...
    def get_context(self, session_id: str, key: str) -> Any | None: ...
```

Truncates message list to `max_messages` by dropping oldest messages.

---

## 11. Human-in-the-Loop Design

### 11.1 LangGraph Interrupt Mechanism

LangGraph supports HITL via `interrupt_before` on the compiled graph and a `MemorySaver` checkpointer. When the graph reaches an interrupt node:

1. Execution pauses and current state is persisted via the checkpointer
2. The API returns the partial state to the client (generated descriptions or SQL)
3. The client sends a resume request with user feedback
4. The graph resumes from the checkpoint with updated state

### 11.2 API Contract for HITL

**Initial request (Schema Agent):**
```json
POST /schema/analyze
{
    "session_id": "abc-123",
    "user_id": "student1"
}
```

**Response (HITL pending):**
```json
{
    "status": "pending_review",
    "thread_id": "thread-xyz",
    "review_data": { ... },
    "prompt": "Please review. Reply with 'approve' or provide revisions."
}
```

**Resume request:**
```json
POST /schema/analyze
{
    "session_id": "abc-123",
    "user_id": "student1",
    "thread_id": "thread-xyz",
    "message": "approve"
}
```

**Response (completed):**
```json
{
    "status": "completed",
    "message": "Schema descriptions saved.",
    "thread_id": "thread-xyz"
}
```

**Query Agent HITL** follows the same pattern via `POST /chat` with `thread_id`.

### 11.3 Thread Management

Each HITL interaction uses a LangGraph **thread_id**. The API must:
- Generate a new `thread_id` for each new conversation flow
- Accept `thread_id` in resume requests to continue an interrupted flow
- The `MemorySaver` checkpointer handles state persistence by thread_id

---

## 12. Agent Patterns Used

### 12.1 Planner/Executor

Both agents use a planner node that creates a structured plan before execution:
- Schema Agent: Plans which tables to document, then executes documentation
- Query Agent: Plans the SQL strategy, then generates and executes SQL

### 12.2 Critic/Validator

The Query Agent's `sql_critic` node validates generated SQL before execution:
- Code-based safety validation (no writes, no dangerous functions)
- Schema-based validation (tables and columns exist)
- LLM-based semantic validation (SQL matches the question)
- Feedback loop: if validation fails, critic feedback is sent back to the generator

### 12.3 Human-in-the-Loop

Two HITL checkpoints:
- Schema review: Always triggered for schema documentation
- SQL confirmation: Conditionally triggered for complex or expensive queries

---

## 13. Docker Compose Setup

### 13.1 PostgreSQL with DVD Rental Data Pre-loaded

**`data/dvdrental_restore.sh`:**
```bash
#!/bin/bash
set -e
if [ -f /docker-entrypoint-initdb.d/dvdrental.tar ]; then
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        /docker-entrypoint-initdb.d/dvdrental.tar || true
fi
```

**`data/init_metadata_schema.sql`:**
```sql
CREATE SCHEMA IF NOT EXISTS agent_metadata;

CREATE TABLE IF NOT EXISTS agent_metadata.user_preferences (
    user_id VARCHAR(255) NOT NULL,
    preference_key VARCHAR(255) NOT NULL,
    preference_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, preference_key)
);

CREATE TABLE IF NOT EXISTS agent_metadata.schema_descriptions (
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255) NOT NULL DEFAULT '__table__',
    description TEXT NOT NULL,
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (table_name, column_name)
);
```

### 13.2 docker-compose.yml

```yaml
services:
  nl-query-agent:
    build:
      context: .
      dockerfile: containers/Dockerfile
      target: production
    image: nl-query-agent
    container_name: nl-query-agent
    ports:
      - "8002:8000"
    env_file:
      - .env
    environment:
      - API_HOST=0.0.0.0
      - API_PORT=8000
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://dvdrental:dvdrental@postgres:5432/dvdrental
      - METADATA_SCHEMA=agent_metadata
      - LLM_SERVICE_URL=${LLM_SERVICE_URL:-https://sa-llmproxy.it.itba.edu.ar}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_MODEL=${LLM_MODEL:-gpt-4.1-mini}
      - GRAPH_MAX_ITERATIONS=15
      - SQL_MAX_ROWS=100
      - SQL_TIMEOUT_SECONDS=30
    volumes:
      - ./src:/app/src:ro
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - test-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  streamlit-ui:
    build:
      context: .
      dockerfile: containers/Dockerfile
      target: production
    image: nl-query-agent-ui
    container_name: nl-query-ui
    ports:
      - "8501:8501"
    environment:
      - API_BASE_URL=http://nl-query-agent:8000
      - STREAMLIT_PORT=8501
    command: ["streamlit", "run", "src/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
    depends_on:
      nl-query-agent:
        condition: service_healthy
    networks:
      - test-network
    restart: unless-stopped

  testing:
    build:
      context: .
      dockerfile: containers/Dockerfile.testing
      target: testing
    image: nl-query-agent-testing
    volumes:
      - ./src:/app/src:ro
      - ./tests:/app/tests:ro
      - ./data:/app/data:ro
    environment:
      - PYTHONPATH=/app/src
      - DATABASE_URL=postgresql://dvdrental:dvdrental@postgres:5432/dvdrental
      - METADATA_SCHEMA=agent_metadata
      - LLM_SERVICE_URL=${LLM_SERVICE_URL:-https://sa-llmproxy.it.itba.edu.ar}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_MODEL=${LLM_MODEL:-gpt-4.1-mini}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - test-network
    command: ["sleep", "infinity"]

  postgres:
    image: postgres:16-alpine
    container_name: nl-query-postgres
    ports:
      - "5433:5432"
    environment:
      POSTGRES_USER: dvdrental
      POSTGRES_PASSWORD: dvdrental
      POSTGRES_DB: dvdrental
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./data/dvdrental.tar:/docker-entrypoint-initdb.d/dvdrental.tar:ro
      - ./data/dvdrental_restore.sh:/docker-entrypoint-initdb.d/01-restore.sh:ro
      - ./data/init_metadata_schema.sql:/docker-entrypoint-initdb.d/02-init-metadata.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dvdrental -d dvdrental"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - test-network

volumes:
  postgres_data:

networks:
  test-network:
    driver: bridge
```

**Note:** The `dvdrental.tar` file must be downloaded from the PostgreSQL tutorial site. Document this in README.

---

## 14. API Endpoints (FastAPI)

### 14.1 Application (`src/api/main.py`)

Following the pattern from `/Users/saints/Desktop/ITBA/Multiagente/demos-estudiantes/DEMO02-memory/src/api/main.py`:

```python
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# import routes and lifespan
```

### 14.2 Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check with DB connectivity verification |
| `POST` | `/chat` | Query Agent — NL queries, follow-ups |
| `POST` | `/schema/analyze` | Schema Agent — auto-discover and document full schema with HITL review |
| `GET` | `/schema/descriptions` | Get approved schema descriptions (optional `?table_name=` filter) |
| `GET` | `/preferences/{user_id}` | Get user preferences |
| `PUT` | `/preferences/{user_id}` | Update user preferences |

**`POST /chat` request body:**
```json
{
    "session_id": "string",
    "user_id": "string",
    "message": "string",
    "thread_id": "string | null"
}
```

**`POST /chat` response (normal):**
```json
{
    "status": "completed",
    "message": "string",
    "sql": "string | null",
    "data": "dict | null",
    "thread_id": "string"
}
```

**`POST /schema/analyze` request body:**
```json
{
    "session_id": "string",
    "user_id": "string",
    "thread_id": "string | null",
    "message": "string | null"
}
```

**HITL pending response (both endpoints):**
```json
{
    "status": "pending_review",
    "thread_id": "string",
    "review_data": "dict",
    "prompt": "string"
}
```

---

## 15. Web UI — Streamlit (`src/ui/`)

### 15.1 Overview

A Streamlit application provides the interactive web interface for both agents. It communicates with the FastAPI backend via HTTP — it does **not** import or invoke LangGraph directly.

### 15.2 Application Entry Point (`src/ui/app.py`)

```python
import streamlit as st

st.set_page_config(page_title="DVD Rental NL Query Agent", layout="wide")

# Tabs for the two agents
tab_chat, tab_schema = st.tabs(["Query Agent", "Schema Documentation"])
```

- Initializes `session_state` with `session_id` (UUID), `user_id`, `thread_id`, `messages` list
- Renders sidebar with preferences controls (language, date format, max results, confirm toggle)
- Delegates to page components based on the active tab

### 15.3 API Client (`src/ui/api_client.py`)

Thin wrapper around `httpx` (or `requests`) to call the FastAPI backend:

```python
class AgentAPIClient:
    def __init__(self, base_url: str): ...
    def chat(self, session_id, user_id, message, thread_id=None) -> dict: ...
    def schema_analyze(self, session_id, user_id, thread_id=None, message=None) -> dict: ...
    def get_schema_descriptions(self, table_name=None) -> dict: ...
    def get_preferences(self, user_id) -> dict: ...
    def update_preferences(self, user_id, prefs) -> dict: ...
    def health() -> dict: ...
```

Reads `API_BASE_URL` from environment (default `http://localhost:8000`).

### 15.4 Chat Component (`src/ui/components/chat.py`)

Renders the Query Agent conversation:

- Uses `st.chat_message` for message bubbles (user + assistant)
- Stores full message history in `st.session_state.messages`
- On user submit: calls `api_client.chat()`, appends response
- When response `status == "pending_review"` (SQL confirmation HITL):
  - Displays the generated SQL in a code block
  - Shows **Approve** / **Reject** buttons via `st.button`
  - On click: calls `api_client.chat()` with `thread_id` and `"approve"` / `"reject"`
- When response contains `data`: renders result as `st.dataframe()` + natural language summary
- When response contains `sql`: renders in `st.code(sql, language="sql")`

### 15.5 Schema Review Component (`src/ui/components/schema_review.py`)

Renders the Schema Agent HITL workflow:

- **"Analyze Full Schema"** button triggers `api_client.schema_analyze()` — the agent automatically discovers all tables
- When response `status == "pending_review"`:
  - Renders each table's generated descriptions in expandable `st.expander` sections
  - For each table: table description + column descriptions in a formatted view
  - Three action buttons: **Approve All**, **Request Revisions** (with `st.text_area` for feedback), **Cancel**
  - On approve: resumes graph with `"approve"` message
  - On revise: resumes graph with revision instructions
- After approval: displays success banner with persisted description count

### 15.6 Sidebar Component (`src/ui/components/sidebar.py`)

Persistent sidebar with:

- **User ID** text input (stored in session state)
- **Preferences** section:
  - Language: `st.selectbox` (en, es)
  - Date format: `st.selectbox` (YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY)
  - Max results: `st.number_input` (1-500, default 50)
  - Confirm before execute: `st.toggle` (default off)
  - Show SQL: `st.toggle` (default on)
- **Save Preferences** button: calls `api_client.update_preferences()`
- Preferences are loaded on app start via `api_client.get_preferences()`
- **Connection status** indicator: green/red dot based on `/health` response

### 15.7 Session Management

- `session_id` is generated as a UUID on first page load and stored in `st.session_state`
- `thread_id` is tracked per-interaction for HITL flows. Set when a `pending_review` response arrives; cleared on completion
- Message history persists across reruns via `st.session_state.messages`
- "New Conversation" button resets `session_id`, `thread_id`, and `messages`

---

## 16. LLM Client (`src/llm/client.py`)

Follow the exact pattern from `/Users/saints/Desktop/ITBA/Multiagente/demos-estudiantes/EJ02-ReAct-LangGraph-resuelto/src/llm/client.py`:

```python
from langchain_openai import ChatOpenAI
from config.settings import get_settings

class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._llm = ChatOpenAI(
            base_url=f"{settings.llm.base_url.rstrip('/')}/v1",
            api_key=settings.llm.api_key or "dummy-key",
            model=settings.llm.model,
            temperature=0.0,
        )

    def bind_tools(self, tools):
        return self._llm.bind_tools(tools)

    def as_model(self):
        return self._llm
```

**Critical**: Never import provider-specific SDKs. Only `langchain-openai` with `base_url` pointing to the LiteLLM proxy.

---

## 17. Logging and Observability

### 17.1 Structured Logging (`src/app_logging/logger.py`)

```python
def configure_logging():
    settings = get_settings()
    level = getattr(logging, settings.app.environment.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
```

### 17.2 Agent Trace Logging

Emit structured log lines for key agent decisions:

```
[PLANNER]    -> Query plan: JOIN film, actor via film_actor; filter by last_name
[GENERATOR]  -> SQL generated: SELECT f.title, a.first_name ...
[CRITIC]     -> Validation passed: safety=OK, schema=OK, semantic=OK
[EXECUTOR]   -> Query executed: 15 rows, 42ms
[PRESENTER]  -> Response formatted in en, showing 15 results
[MEMORY]     -> Session context updated: last_sql stored
```

### 17.3 LangSmith (`src/app_logging/langsmith.py`)

Same pattern as EJ02-ReAct-LangGraph: set `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` from settings. Suppress LangSmith warnings when API key is missing.

---

## 18. Testing Requirements

### 18.1 Style

All tests are plain pytest functions. Follow Given/When/Then/Clean pattern. Naming: `test_u_*` (unit), `test_f_*` (functional), `test_in_*` (integration).

### 18.2 Root conftest (`tests/conftest.py`)

```python
import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://dvdrental:dvdrental@localhost:5433/dvdrental")
os.environ.setdefault("LLM_SERVICE_URL", "https://sa-llmproxy.it.itba.edu.ar")
os.environ.setdefault("LLM_MODEL", "gpt-4.1-mini")

import pytest

@pytest.fixture
def test_client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)
```

### 18.3 Unit Tests

| File | Covers |
|------|--------|
| `test_u_state.py` | `BaseAgentState`, `SchemaAgentState`, `QueryAgentState`, factory functions |
| `test_u_schema_nodes.py` | Schema planner, analyzer (mocked MCP), persister (mocked DB) |
| `test_u_query_nodes.py` | Query planner, SQL generator (mocked LLM), critic, executor (mocked MCP), presenter |
| `test_u_sql_safety.py` | `validate_sql_safety` rejects writes, DDL, system schema, multi-statement, comments |
| `test_u_memory_persistent.py` | Preferences CRUD (mocked DB), schema descriptions CRUD |
| `test_u_memory_short_term.py` | Session context add/get/truncation |
| `test_u_settings.py` | Settings load from env vars |
| `test_u_llm_client.py` | LLMClient uses correct base_url and model |

### 18.4 Functional Tests (require running PostgreSQL)

| File | Covers |
|------|--------|
| `test_f_health.py` | `GET /health` returns healthy with DB connected |
| `test_f_mcp_tools.py` | MCP inspect_schema returns DVD Rental tables; execute_sql runs SELECT; get_table_sample returns rows |
| `test_f_schema_agent.py` | Schema agent analyzes a table and produces descriptions |
| `test_f_query_agent.py` | Query agent translates "How many films?" into SQL and returns count |

### 18.5 Integration Tests (require running PostgreSQL + LLM proxy)

| File | Covers |
|------|--------|
| `test_in_full_scenario.py` | Full E2E: set preferences, document schema, query, follow-up |
| `test_in_schema_documentation.py` | Auto-discover full schema, generate descriptions, HITL approve flow |
| `test_in_nl_queries.py` | Execute the 3 demo queries from Section 20 |

---

## 19. Implementation Phases

### Phase 0: Project Foundation

**Goal:** Project structure, Docker setup, PostgreSQL with DVD Rental loaded, settings, health endpoint.

**Steps:**
1. Create project structure per Section 4
2. Create `pyproject.toml` with all dependencies
3. Implement `src/config/settings.py`
4. Implement `src/app_logging/logger.py` and `langsmith.py`
5. Implement `src/llm/client.py`
6. Create `containers/Dockerfile` and `containers/Dockerfile.testing`
7. Create `docker-compose.yml` with PostgreSQL + DVD Rental init scripts
8. Implement `src/api/main.py` with `/health` endpoint
9. Create `.env.example`

**Artifact:** `docker compose up` starts PostgreSQL with DVD Rental data. `GET /health` returns healthy.

**Tests:** `test_u_settings.py`, `test_u_llm_client.py`, `test_f_health.py`

### Phase 1: MCP Tools

**Goal:** MCP server with three tools and SQL safety module.

**Steps:**
1. Implement `src/tools/sql_safety.py`
2. Implement `src/tools/mcp_server.py` with all three tools
3. Implement `src/tools/mcp_client.py`
4. Test against real DVD Rental database

**Artifact:** MCP tools work. `inspect_schema()` returns 15 tables.

**Tests:** `test_u_sql_safety.py`, `test_f_mcp_tools.py`

### Phase 2: Memory Modules

**Goal:** Persistent memory (PostgreSQL) and short-term memory (in-memory).

**Steps:**
1. Implement `src/memory/persistent.py`
2. Implement `src/memory/short_term.py`
3. Create `data/init_metadata_schema.sql`

**Artifact:** Can store and retrieve preferences and schema descriptions.

**Tests:** `test_u_memory_persistent.py`, `test_u_memory_short_term.py`

### Phase 3: LangGraph Foundation

**Goal:** Base state definitions, stub nodes, both graphs compile.

**Steps:**
1. Implement `src/agent/state.py` with `BaseAgentState`, `SchemaAgentState`, `QueryAgentState`
2. Implement stub nodes for both agents
3. Implement `src/agent/schema_agent/graph.py` and `src/agent/query_agent/graph.py`
4. Wire to API endpoints (`POST /chat` and `POST /schema/analyze`)

**Artifact:** Both graphs compile and API routes invoke them (stub responses).

**Tests:** `test_u_state.py`

### Phase 4: Schema Agent

**Goal:** Complete Schema Agent with HITL.

**Steps:**
1. Implement schema agent prompts, nodes, edges
2. Wire HITL interrupt
3. Implement resume handling in schema/analyze endpoint

**Artifact:** Schema Agent auto-discovers all tables and generates descriptions. User reviews via HITL approval flow.

**Tests:** `test_u_schema_nodes.py`, `test_f_schema_agent.py`

### Phase 5: Query Agent

**Goal:** Complete Query Agent with Critic/Validator.

**Steps:**
1. Implement query agent prompts, nodes, edges
2. Implement follow-up detection
3. Wire conditional HITL

**Artifact:** User can ask NL questions and get results.

**Tests:** `test_u_query_nodes.py`, `test_f_query_agent.py`

### Phase 6: Preferences and Polish

**Goal:** Preferences API, preference-aware behavior.

**Steps:**
1. Implement preferences and schema API routes
2. Ensure result_presenter respects preferences

**Artifact:** Preferences persist across sessions; responses respect language/format settings.

### Phase 7: Streamlit Web UI

**Goal:** Interactive web interface for both agents.

**Steps:**
1. Implement `src/ui/api_client.py` (HTTP client wrapper)
2. Implement `src/ui/components/sidebar.py` (preferences, user ID, connection status)
3. Implement `src/ui/components/chat.py` (Query Agent chat with HITL confirm)
4. Implement `src/ui/components/schema_review.py` (Schema Agent with HITL review panel)
5. Implement `src/ui/app.py` (main app with tabs)
6. Add `streamlit-ui` service to `docker-compose.yml`

**Artifact:** `docker compose up` starts Streamlit on `:8501`. User can chat with Query Agent and document schema with HITL review.

### Phase 8: Integration Tests and Demo

**Goal:** Full integration tests and demo scenarios.

**Steps:**
1. Implement all integration tests
2. Run full test suite
3. Run `ruff check --fix && ruff format`

**Artifact:** All tests pass. Demo scenarios work via both API and Streamlit UI.

---

## 20. Demo Scenarios

### Scenario 1: Schema Documentation with HITL

User clicks "Analyze Full Schema". Agent automatically discovers all 15 tables, generates descriptions for every table and column, presents them for review. User approves most but requests a revision on the `film` table description. Agent revises, user approves, all descriptions are persisted and available for query generation.

### Scenario 2: Simple Count Query

User asks "How many films are in the database?" Agent generates `SELECT COUNT(*) FROM film`, validates, executes, presents result.

### Scenario 3: Join Query with Aggregation

User asks "What are the top 5 most rented films?" Agent plans JOIN across film, inventory, rental, generates SQL with GROUP BY and ORDER BY, validates, executes.

### Scenario 4: Follow-up Refinement

User says "Filter those by the Action category only". Agent detects follow-up via session context, modifies previous SQL to add JOIN to film_category/category and WHERE filter.

### Scenario 5: Revenue Aggregation

User asks "What was the total revenue per month in 2005?" Agent generates SQL with EXTRACT, SUM, GROUP BY on payment table.

---

## 21. Success Criteria and Acceptance Checklist

| # | Criterion | Validation |
|---|-----------|-----------|
| 1 | Two independent LangGraph StateGraphs compile and run | `build_schema_graph()` and `build_query_graph()` produce valid graphs |
| 2 | MCP tools work | `inspect_schema()` returns 15 tables; `execute_sql` works; `get_table_sample` works |
| 3 | Schema Agent with HITL | Agent auto-discovers all 15 tables, generates descriptions, user reviews and approves, descriptions persist |
| 4 | Query Agent NL-to-SQL | "How many films?" produces correct count |
| 5 | SQL safety enforced | `DELETE FROM film` rejected by critic |
| 6 | Follow-up queries | "filter by Action" modifies previous SQL using session context |
| 7 | Persistent memory | Preferences and schema descriptions survive across sessions |
| 8 | Short-term memory | Session context enables follow-ups within a session |
| 9 | Agent patterns | Planner/Executor + Critic/Validator + HITL all demonstrated |
| 10 | Tests pass | `pytest` passes (unit + functional + integration) |
| 11 | Code quality | `ruff check --fix && ruff format` passes |
| 12 | Docker works | `docker compose up` starts everything |
| 13 | Health check | `GET /health` returns healthy |
| 14 | Observability | LangSmith tracing + structured agent trace logs |
| 15 | Streamlit UI works | Chat tab sends NL queries and displays results; Schema tab documents tables with HITL review; Preferences sidebar persists settings |
| 16 | HITL via UI | Schema review approve/revise flow works end-to-end in Streamlit; SQL confirmation flow works in chat tab |

---

## 22. Dependencies (`pyproject.toml`)

```toml
[project]
name = "nl-query-agent"
version = "0.1.0"
description = "Multi-agent natural language query system over PostgreSQL"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.104.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "uvicorn[standard]>=0.24.0",
    "langgraph>=0.2.0",
    "langchain-openai>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-mcp-adapters>=0.1.0",
    "mcp>=1.0.0",
    "psycopg[binary]>=3.1.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.25.0",
    "streamlit>=1.38.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = "-v"
```

---

## 23. DVD Rental Database Reference

The DVD Rental database contains **15 tables** in the `public` schema:

| Table | Key Columns |
|-------|-------------|
| `actor` | actor_id, first_name, last_name |
| `address` | address_id, address, city_id |
| `category` | category_id, name |
| `city` | city_id, city, country_id |
| `country` | country_id, country |
| `customer` | customer_id, first_name, last_name, email, store_id |
| `film` | film_id, title, description, release_year, rental_rate |
| `film_actor` | film_id, actor_id |
| `film_category` | film_id, category_id |
| `inventory` | inventory_id, film_id, store_id |
| `language` | language_id, name |
| `payment` | payment_id, customer_id, amount, payment_date |
| `rental` | rental_id, rental_date, inventory_id, customer_id |
| `staff` | staff_id, first_name, last_name, store_id |
| `store` | store_id, manager_staff_id, address_id |

---

## 24. Prompt for the Coding Agent

> You are an expert Python developer specialized in multi-agent AI systems.
>
> Implement the **NL Query Agent** project exactly as described in this specification.
>
> Requirements:
> 1. Use `uv` + `pyproject.toml`. No `requirements.txt`.
> 2. Use LangGraph `StateGraph` — two independent graphs (Schema Agent and Query Agent), not one combined graph.
> 3. Use LangChain `ChatOpenAI` for the model (LiteLLM proxy). Never import provider-specific SDKs.
> 4. Implement MCP tools for all database operations. Agents must not use direct SQL connections.
> 5. Implement HITL using LangGraph `interrupt_before` for schema review and conditional SQL confirmation.
> 6. Implement persistent memory (PostgreSQL) for user preferences and schema descriptions.
> 7. Implement short-term memory for session context (follow-up queries).
> 8. Implement SQL safety validation (reject writes, DDL, system schema access).
> 9. Tests as plain pytest functions following Given/When/Then/Clean.
> 10. Docker must pre-load DVD Rental sample database into PostgreSQL.
> 11. Build a Streamlit web UI with chat and schema review tabs. The UI communicates with FastAPI via HTTP — never imports LangGraph directly.
>
> Implement Phase 0-8 sequentially. Each phase should yield a testable artifact.

---

### Critical Files for Implementation

The following files are the most critical to implement, as they form the backbone of the system:

- `src/agent/schema_agent/graph.py` -- The Schema Agent LangGraph (planner, analyzer, HITL review, persister). Independent StateGraph with interrupt_before for HITL.

- `src/agent/query_agent/graph.py` -- The Query Agent LangGraph (planner, generator, critic, confirm, executor, presenter). Independent StateGraph with conditional HITL and critic/validator loop.

- `src/tools/mcp_server.py` -- The MCP tool server implementing `inspect_schema`, `execute_sql`, and `get_table_sample`. Both agents depend on this for all database operations.

- `src/agent/query_agent/nodes.py` -- The Query Agent's six nodes. This is the most complex agent with the Critic/Validator pattern and follow-up query detection.

- `src/memory/persistent.py` -- Persistent memory for user preferences and schema descriptions. Cross-session state depends on this.

- `src/tools/sql_safety.py` -- SQL safety validation module. This is a critical guardrail ensuring the system never executes write operations.

- `src/ui/app.py` -- Streamlit web UI entry point. Renders chat tab (Query Agent) and schema tab (Schema Agent with HITL review). Communicates with FastAPI backend via HTTP.
