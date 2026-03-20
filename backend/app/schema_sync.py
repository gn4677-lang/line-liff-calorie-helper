from __future__ import annotations

from sqlalchemy import inspect, text


def ensure_runtime_schema(engine) -> None:
    inspector = inspect(engine)
    dialect = engine.dialect.name

    def has_table(table_name: str) -> bool:
        return table_name in inspector.get_table_names()

    def column_names(table_name: str) -> set[str]:
        return {column["name"] for column in inspector.get_columns(table_name)} if has_table(table_name) else set()

    def add_column(table_name: str, column_name: str, definition: str) -> None:
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))

    def add_if_missing(table_name: str, column_name: str, sqlite_definition: str, postgres_definition: str | None = None) -> None:
        if column_name in column_names(table_name):
            return
        definition = postgres_definition if dialect == "postgresql" and postgres_definition else sqlite_definition
        add_column(table_name, column_name, definition)

    json_type = "JSON" if dialect == "postgresql" else "TEXT"
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "TIMESTAMP"

    if has_table("users"):
        add_if_missing("users", "onboarding_completed_at", timestamp_type)
        add_if_missing("users", "onboarding_skipped_at", timestamp_type)
        add_if_missing("users", "onboarding_version", "VARCHAR(20) DEFAULT 'v1'")

    if has_table("preferences"):
        add_if_missing("preferences", "hard_dislikes", f"{json_type} DEFAULT '[]'")
        add_if_missing("preferences", "breakfast_habit", "VARCHAR(50) DEFAULT 'unknown'")
        add_if_missing("preferences", "carb_need", "VARCHAR(50) DEFAULT 'flexible'")
        add_if_missing("preferences", "communication_profile", f"{json_type} DEFAULT '{{}}'")

    if has_table("meal_drafts"):
        add_if_missing("meal_drafts", "meal_session_id", "VARCHAR(36)")
        add_if_missing("meal_drafts", "event_at", timestamp_type)

    if has_table("meal_logs"):
        add_if_missing("meal_logs", "meal_session_id", "VARCHAR(36)")
        add_if_missing("meal_logs", "event_at", timestamp_type)
        add_if_missing("meal_logs", "metadata", f"{json_type} DEFAULT '{{}}'")
        with engine.begin() as connection:
            connection.execute(text("UPDATE meal_logs SET event_at = created_at WHERE event_at IS NULL"))

    if has_table("foods"):
        add_if_missing("foods", "store_context", f"{json_type} DEFAULT '{{}}'")

    with engine.begin() as connection:
        if has_table("meal_drafts"):
            connection.execute(text("UPDATE meal_drafts SET meal_session_id = id WHERE meal_session_id IS NULL"))
            connection.execute(text("UPDATE meal_drafts SET event_at = created_at WHERE event_at IS NULL"))
        if has_table("users"):
            connection.execute(text("UPDATE users SET onboarding_version = 'v1' WHERE onboarding_version IS NULL"))
        if has_table("preferences"):
            connection.execute(text("UPDATE preferences SET breakfast_habit = 'unknown' WHERE breakfast_habit IS NULL"))
            connection.execute(text("UPDATE preferences SET carb_need = 'flexible' WHERE carb_need IS NULL"))
