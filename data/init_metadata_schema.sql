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
