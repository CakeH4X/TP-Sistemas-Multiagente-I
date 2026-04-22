# Design report — NL Query Agent

**Course:** Multi-Agent Systems (2026 S1) · Individual submission

## Problem framing

Build a production-style prototype that lets a non-technical user query a PostgreSQL database in natural language, with two explicit goals: (1) document the schema collaboratively with the user (HITL), and (2) answer follow-up queries safely. The dataset is fixed (DVD Rental) but the architecture must generalize.

The hardest sub-problems are **grounding** (the LLM needs to know the schema to produce correct SQL), **safety** (no writes can ever reach the DB, even if the LLM is coerced or hallucinates), and **UX** (pausing the graph for human review can't make the happy path painful for simple queries).

## Two-agent decomposition

I separated the problem into two graphs rather than one, because the two flows differ in cadence, input shape, and risk profile:

- **Schema Agent** runs rarely (once per database, or after schema drift). It's write-heavy to its own metadata store and always involves HITL — approved docs become training data for every future query. Its state is schema-shaped.
- **Query Agent** runs often (every user turn). It's read-only against the DVD Rental tables, keeps a per-session context for follow-ups, and needs fast auto-approve for simple queries. Its state is question-shaped.

Merging them would have forced awkward conditional routing on the top-level graph and mixed state fields that have no reason to live together. Keeping them separate lets each have its own prompts, its own node vocabulary, and its own interrupt strategy.

## Choice of HITL strategy

The two agents use different HITL mechanisms, deliberately.

**Schema Agent** uses the older `interrupt_before=["schema_review"]` pattern — the graph *always* pauses before committing descriptions, because documenting a schema is inherently a collaborative act. The user may approve, reject, or type free-form revision feedback; the latter loops back into the analyzer with the feedback embedded in every per-table prompt, capped at 3 cycles.

**Query Agent** uses LangGraph's modern `interrupt()` inside `sql_confirm`, which supports *conditional* HITL. Simple single-table queries with LIMIT auto-approve and complete in one round-trip. Risky queries (4+ joins, missing LIMIT, or the user's `confirm_before_execute=true` preference) pause for approval. This was the key UX insight: unconditional HITL makes every question slow and annoying; conditional HITL preserves oversight exactly where it matters.

## Safety: three layers of defense

Read-only enforcement can't rely on a single check. The system layers three independent mechanisms, each sufficient on its own:

1. **`sql_safety.validate_sql_safety()`** — a pure-Python validator run *before* any SQL touches the DB. Rejects anything not starting with `SELECT` or `WITH`, any write keyword (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/GRANT/REVOKE/COPY), multi-statements, SQL comments (injection vector), references to system schemas (`pg_catalog`, `information_schema`, `agent_metadata`), and dangerous functions (`pg_sleep`, `pg_terminate_backend`).
2. **`SET TRANSACTION READ ONLY`** — issued on the MCP server connection before every execution. The Postgres server itself rejects writes, regardless of what the SQL contains.
3. **`statement_timeout`** — bounds CPU and prevents accidentally expensive queries.

Plus a row cap (`fetchmany(max_rows + 1)`) to detect truncation. This defense-in-depth was motivated by the observation that LLMs can be surprisingly creative when prompted adversarially; relying on "the LLM won't write DELETE" is a contract that breaks the first time someone writes a jailbreak prompt.

## MCP over a separate tool interface

I chose MCP (not plain Python function calls as tools) because the course required it, but the tradeoff is interesting. MCP via stdio adds subprocess spawn overhead and complicates error handling (a dead subprocess manifests as a hang). The benefit is **process isolation** — the MCP server is the *only* component that holds a DB connection, so an agent bug can't accidentally connect with write credentials. It also makes the tool interface language-agnostic: a future Go or TypeScript rewrite of the MCP client would still work with the same Python server.

For in-process node calls (Schema Agent's analyzer, Query Agent's executor), I bypass the stdio pipeline and call the `@mcp.tool` decorated functions directly. This gives up the isolation benefit in exchange for 100× lower latency and simpler error propagation. The stdio path exists and is tested (`test_mcp_client_end_to_end_spawns_server_and_lists_tools`) so an LLM tool-calling agent could plug in later.

## Memory: persistent vs short-term

The split is driven by data lifetime, not by convenience:

- **Persistent** (Postgres, `agent_metadata` schema) — things that should survive restarts: user preferences (language, date format, row caps) and approved schema descriptions. Both cross session boundaries: preferences follow the user forever, descriptions are shared across all users' queries.
- **Short-term** (in-process dict) — things that only matter *within* a conversation: the last SQL, last plan, last result summary. Persisting these would mix "current" with "historical" and break follow-up semantics. They're explicitly trimmed to the last 50 messages to bound memory.

The short-term `SessionContext` is the key to follow-ups. When the planner sees `last_sql` in the session, it adds a "follow-up hint" block to its system prompt. This is why *"What about R-rated?"* produces `WHERE rating = 'R'` instead of a fresh SELECT with no context.

## Critic/Validator as a feedback loop, not a gate

My first design had the critic as a binary gate (passed/failed → execute/reject). This kept failing for semantic reasons: the LLM-based semantic check is advisory and sometimes incorrectly flags a perfectly good query. With a binary gate, a minor semantic concern would loop the generator forever until hitting `max_iterations`.

The final design routes safety and schema failures back to the generator (with the critic's issues + suggestions embedded in the next prompt), but treats semantic concerns as *suggestions* that don't block execution. This matches the spirit of a code reviewer: some comments are blocking, some are nits.

## Trade-offs I consciously accepted

- **No DB connection pooling.** Every MCP tool call opens a fresh psycopg connection. Fine for a single-user demo, wasteful at scale. Fixable with `psycopg_pool`.
- **Graph singletons share in-memory `MemorySaver`.** Checkpoints live in RAM, so restarting the process loses pending HITL threads. For a persistent deployment, swap for `langgraph-checkpoint-postgres`.
- **Sequential per-table LLM calls in the schema analyzer.** 15 tables × 2 s ≈ 30 s for a full analysis. Could be parallelized with `asyncio.gather`, but sequential calls made debugging the HITL flow much simpler during development.
- **Regex-based FROM/JOIN table extraction.** Catches false positives on `EXTRACT(month FROM payment_date)`. Mitigated by the "lenient" critic (only error if NO reference is real). A proper SQL parser (`sqlglot`) would fix this cleanly.

Full list in `CLAUDE.md § Known limitations`, including how to evolve past each.

## What worked well

- **FastMCP + langchain-mcp-adapters** was a very small code footprint for the tool layer. Three tools in ~200 lines, with a stdio pipeline for free.
- **LangGraph's `interrupt_before` + `interrupt()`** gave two different HITL strategies from the same primitives, matching the two agents' needs without custom plumbing.
- **Streamlit's session_state + rerun model** made the UI essentially stateless on the backend — all session state lives in the browser session and gets re-hydrated from `/preferences` + `/schema/descriptions` on each render.
- **Pydantic-settings with `AliasChoices`** gave clean support for both `LLM_BASE_URL` and the spec's `LLM_SERVICE_URL`, without runtime branching.

## What I'd change next

1. Move checkpoints to Postgres so deployments survive restarts.
2. Add a proper SQL parser in the critic (`sqlglot`) to eliminate the regex false-positive class.
3. Stream the graph's progress to the UI (SSE) so the user sees "planning… generating… checking…" instead of a single long spinner.
4. Multi-language schema descriptions, keyed by user preference, so a Spanish user sees Spanish docs in the planner's prompt.

## Verification

- 167 tests (unit + functional + integration), all passing with `uv run pytest tests/`.
- `ruff check` + `ruff format --check` clean.
- Manual demo scenarios documented in [`DEMO.md`](DEMO.md) and executable as curl sequences or via Streamlit.
- All runs use the mandatory DVD Rental dataset (15 tables, 1000 films, 14596 rentals).
