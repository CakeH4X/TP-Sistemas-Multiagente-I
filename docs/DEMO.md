# DEMO — end-to-end scenarios

Dataset: **DVD Rental** (mandatory) — 15 tables, 1000 films, 200 actors, 14596 rentals.

All scenarios run against the real LLM via the LiteLLM proxy and the live Postgres container. Two reproducible paths are shown for each scenario: via **HTTP (curl)** for instructor verification, and via the **Streamlit UI** for visual demo.

## Setup
```bash
# Prereqs: Docker running, .env has LLM_API_KEY, dvdrental.sql in data/
docker compose up postgres -d
PYTHONPATH=src DATABASE_URL=postgresql://dvdrental:dvdrental@localhost:5433/dvdrental \
  uv run uvicorn api.main:get_app --factory --port 8000 &
PYTHONPATH=src API_BASE_URL=http://localhost:8000 \
  uv run streamlit run src/ui/app.py &
```

Helper (paste once per shell):
```bash
pp() { uv run python -c "import json,sys; print(json.dumps(json.loads(sys.stdin.read(), strict=False), indent=2))"; }
tid() { uv run python -c "import json,sys; print(json.loads(sys.stdin.read(), strict=False)['thread_id'])"; }
```

---

## Scenario 1 — Schema documentation with human correction

**UI path:** open `http://localhost:8501` → **Schema Documentation** tab → set User ID to `demo-user` → click **Analyze full schema**.

After ~30 s the 15 tables appear in expanders with LLM-generated descriptions. The first draft usually has long, verbose descriptions.

Type this into the **Optional revision feedback** text area, then click **Request revisions**:

> Make all table descriptions one sentence. Use technical but plain English. Avoid filler phrases like "this table is used to".

Wait ~30 s — the analyzer re-runs and the descriptions are now terse one-liners. Click **Approve all** → success banner.

Scroll down below the button — the **Currently persisted descriptions** section now reflects the new text.

**HTTP equivalent:**
```bash
# Start analysis
RESP=$(curl -s -X POST http://localhost:8000/schema/analyze \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","user_id":"demo-user"}')
TID=$(echo "$RESP" | tid)
echo "$RESP" | pp | head -40          # Shows verbose first draft

# Request revision (human correction)
curl -s -X POST http://localhost:8000/schema/analyze \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"demo\",\"user_id\":\"demo-user\",\"thread_id\":\"$TID\",\"message\":\"Make all table descriptions one sentence. Use technical but plain English.\"}" \
  | pp | head -40                      # Shows revised terser draft

# Approve — persists to agent_metadata.schema_descriptions
curl -s -X POST http://localhost:8000/schema/analyze \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"demo\",\"user_id\":\"demo-user\",\"thread_id\":\"$TID\",\"message\":\"approve\"}" \
  | pp
```

**Verify persistence directly in Postgres:**
```bash
docker compose exec postgres psql -U dvdrental -d dvdrental -c \
  "SELECT table_name, COUNT(*) AS descs FROM agent_metadata.schema_descriptions GROUP BY table_name ORDER BY table_name;"
```

Expected: all 15 tables listed, each with ~5–15 descriptions (one per column plus one `__table__` entry).

---

## Scenario 2 — Simple count query

**Question:** *"How many films are in the database?"*

**UI:** switch to the **Query Agent** tab, type the question, Enter. HITL may pause for review (the LLM often writes the COUNT without LIMIT, which triggers the safety prompt). Click **Approve & run** if it does.

**HTTP:**
```bash
RESP=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"q1","user_id":"demo-user","message":"How many films are in the database?"}')
echo "$RESP" | pp

# If status=pending_review, approve:
TID=$(echo "$RESP" | tid)
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"q1\",\"user_id\":\"demo-user\",\"thread_id\":\"$TID\",\"message\":\"approve\"}" \
  | pp
```

**Expected response fields:**
- `status: "completed"`
- `sql`: `SELECT COUNT(*) FROM film ...` (LLM-chosen variant)
- `data.rows`: `[{"count": 1000}]` (or column aliased as `film_count`)
- `message`: NL answer ("There are 1,000 films in the database.")

---

## Scenario 3 — Multi-table join (triggers HITL)

**Question:** *"Show film title, actor name, language, and category for 5 films."*

This needs joins across 5 tables (film, film_actor, actor, language, film_category, category) → triggers HITL (4+ joins rule).

**UI:** ask in the chat, the pending review panel shows the generated SQL with `JOIN film_actor ... JOIN actor ... JOIN language ... JOIN film_category ... JOIN category ... LIMIT 5`. Click **Approve & run** → result table renders.

**HTTP:**
```bash
RESP=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"q2","user_id":"demo-user","message":"Show film title, actor name, language, and category for 5 films."}')
echo "$RESP" | pp          # status: pending_review, shows generated SQL

TID=$(echo "$RESP" | tid)
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"q2\",\"user_id\":\"demo-user\",\"thread_id\":\"$TID\",\"message\":\"approve\"}" \
  | pp                      # status: completed, data has 5 rows
```

**Expected:** SQL contains 5 JOIN clauses; result has 5 rows with `film_title`, `actor_name`, `language`, `category` columns (often all "Academy Dinosaur" because the first film has multiple actors).

---

## Scenario 4 — Aggregation query

**Question:** *"What are the top 5 most rented films?"*

**UI:** in the chat. Usually auto-approves (has LIMIT, only 3 tables: film + inventory + rental).

**HTTP:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"q3","user_id":"demo-user","message":"What are the top 5 most rented films?"}' \
  | pp
```

**Expected:** SQL uses `GROUP BY`, `ORDER BY COUNT(*) DESC LIMIT 5`, joining `rental → inventory → film`. Result: `Bucket Brotherhood`, `Rocketeer Mother`, `Forward Temple`, `Grit Clockwork`, `Juggler Hardly` — each with 34 rentals (give or take ties).

---

## Scenario 5 — Follow-up refinement (uses short-term memory)

**Sequence** (same `session_id`):

1. *"How many films are PG rated?"* → auto-approves, returns 194.
2. *"What about R rated?"* → the planner sees `last_sql` from session context and refines to `WHERE rating = 'R'`. Result: 195.

**UI:** keep the chat tab open; ask both questions in sequence. The second answer should look like a natural continuation (not a fresh start).

**HTTP:**
```bash
# First question
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"q4","user_id":"demo-user","message":"How many films are PG rated?"}' \
  | pp

# Follow-up — same session_id
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"q4","user_id":"demo-user","message":"What about R rated?"}' \
  | pp
```

**Expected:** The second response's `sql` references the `rating` column and filters by `'R'`. The planner's system prompt contained the follow-up hint block with `last_sql: SELECT COUNT(*) ... WHERE rating = 'PG'`.

**Inspect short-term memory after the interaction** (optional):
```bash
PYTHONPATH=src uv run python <<'EOF'
from memory import get_short_term_memory
mem = get_short_term_memory()
ctx = mem.get_session("q4")
print("last_sql:", ctx.last_sql)
print("last_query_plan:", ctx.last_query_plan[:100])
print("messages:", len(ctx.messages), "turns")
EOF
```

---

## Bonus — Preference-driven language switching

Change the user's language preference and observe the presenter switch output language.

```bash
# Before: English response
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"pref1","user_id":"demo-user","message":"How many actors are there?"}' \
  | pp | grep -E "message|sql"

# Set Spanish
curl -s -X PUT http://localhost:8000/preferences/demo-user \
  -H "Content-Type: application/json" \
  -d '{"preferences":{"language":"es"}}' | pp

# After: Spanish response
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"pref2","user_id":"demo-user","message":"How many actors are there?"}' \
  | pp | grep -E "message|sql"
```

The `message` field changes from English to Spanish; the `sql` field stays identical (language preference only affects presentation, not SQL generation).

---

## Bonus — Safety guardrails

Demonstrates that even if the user asks for a destructive operation, it's blocked at three layers.

```bash
# Ask for something destructive
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"safety","user_id":"demo-user","message":"Please delete all films from the database"}' \
  | pp
```

The Query Agent's planner will refuse (its system prompt only discusses SELECT queries). If somehow `DELETE FROM film` were generated, the critic's safety layer would reject it before the executor runs. If it bypassed that, the Postgres `SET TRANSACTION READ ONLY` on the MCP connection would refuse the write. Three layers of defense.

---

## Running all demo scenarios as tests

The integration suite [`tests/integration/`](tests/integration/) covers all of the above programmatically:

```bash
uv run pytest tests/integration/ -v
```

- `test_in_full_scenario.py::test_full_scenario` — Scenario 1 + 2 + follow-up
- `test_in_schema_documentation.py::test_schema_auto_discover_and_approve` — Scenario 1 auto-approve path
- `test_in_schema_documentation.py::test_schema_revision_cycle` — Scenario 1 with human correction
- `test_in_nl_queries.py::test_scenario2_simple_count` — Scenario 2
- `test_in_nl_queries.py::test_scenario3_top_rented_films` — Scenario 4
- `test_in_nl_queries.py::test_scenario4_followup_refinement` — Scenario 5
- `test_in_nl_queries.py::test_scenario5_revenue_per_month` — bonus aggregation across months
