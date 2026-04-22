"""System and user prompts for the Schema Agent."""

PLANNER_SYSTEM_PROMPT = """\
You are a database schema documentation planner. Your job is to discover
and document the complete schema of the DVD Rental database.
Call inspect_schema() to discover all tables, then plan the documentation
order (respecting FK dependencies so referenced tables are described first).
"""

ANALYZER_SYSTEM_PROMPT = """\
You are a database schema documentation assistant for the DVD Rental database.
Given a table's columns, foreign keys, and a small sample of rows, produce
concise, human-readable descriptions.

Return a single JSON object (no markdown fences) where:
- The key "__table__" holds a one- or two-sentence description of the table's purpose.
- Each remaining key is a column name with a short description of what the column
  represents, including format notes when relevant (e.g. "3-letter ISO code").

Do not include any extra keys. Do not invent columns. Only describe the columns
supplied in the input.
"""

REVISION_NOTE_TEMPLATE = """\
The user asked for revisions to your previous descriptions.
Feedback:
{feedback}

Incorporate this feedback into the new descriptions.
"""


def build_analyzer_user_prompt(
    table_name: str,
    columns: list[dict],
    foreign_keys: list[dict],
    sample_rows: list[dict],
    revision_feedback: str | None = None,
) -> str:
    """Build the user-turn prompt for the analyzer LLM call."""
    parts: list[str] = [f"Table: {table_name}", "", "Columns:"]
    for c in columns:
        nullable = "NULL" if str(c.get("is_nullable")).upper() == "YES" else "NOT NULL"
        parts.append(f"- {c['column_name']} ({c['data_type']}, {nullable})")

    if foreign_keys:
        parts.append("")
        parts.append("Foreign keys:")
        for fk in foreign_keys:
            ref = f"{fk['references_table']}.{fk['references_column']}"
            parts.append(f"- {fk['column_name']} -> {ref}")

    parts.append("")
    parts.append("Sample rows (up to 5):")
    if sample_rows:
        for row in sample_rows:
            parts.append(f"- {row}")
    else:
        parts.append("- (no rows)")

    if revision_feedback:
        parts.append("")
        parts.append(REVISION_NOTE_TEMPLATE.format(feedback=revision_feedback))

    return "\n".join(parts)
