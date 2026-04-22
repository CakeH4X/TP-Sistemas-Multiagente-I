"""SQL safety validation — pure Python, no LLM or DB dependencies.

Used as a pre-flight check before any SQL is passed to the MCP ``execute_sql``
tool or to the Query Agent's critic node. Only SELECTs against the ``public``
schema of the DVD Rental database are allowed.
"""

import re

WRITE_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "COPY",
}

FORBIDDEN_SCHEMAS = {"pg_catalog", "information_schema", "agent_metadata"}

DANGEROUS_FUNCTIONS = {"pg_sleep", "pg_terminate_backend"}

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def validate_sql_safety(sql: str) -> tuple[bool, list[str]]:
    """Validate ``sql`` for safe read-only execution.

    Returns ``(is_safe, issues)`` — ``is_safe`` is ``True`` iff ``issues`` is empty.
    """
    issues: list[str] = []

    if not sql or not sql.strip():
        return False, ["SQL is empty"]

    stripped = sql.strip()

    if "--" in stripped:
        issues.append("SQL contains '--' comments (injection vector)")
    if "/*" in stripped:
        issues.append("SQL contains '/*' comments (injection vector)")

    # Allow a single optional trailing semicolon; anything else is multi-statement.
    if ";" in stripped.rstrip(";"):
        issues.append("SQL contains semicolons (multi-statement not allowed)")

    upper = stripped.upper().lstrip().rstrip(";").rstrip()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        issues.append("SQL must start with SELECT (or a WITH/CTE ending in SELECT)")

    tokens = set(re.findall(rf"\b{_IDENT}\b", sql.upper()))
    write_hits = tokens & {kw.upper() for kw in WRITE_KEYWORDS}
    if write_hits:
        issues.append(
            "SQL contains forbidden write keywords: " + ", ".join(sorted(write_hits))
        )

    lower_sql = sql.lower()
    for schema in FORBIDDEN_SCHEMAS:
        if re.search(rf"\b{re.escape(schema)}\b", lower_sql):
            issues.append(f"SQL references forbidden schema: {schema}")

    for fn in DANGEROUS_FUNCTIONS:
        if re.search(rf"\b{re.escape(fn)}\s*\(", lower_sql):
            issues.append(f"SQL calls dangerous function: {fn}")

    return (len(issues) == 0), issues
