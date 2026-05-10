from __future__ import annotations

from app.repositories.db import get_connection, init_db


def test_governance_columns_are_migrated() -> None:
    init_db()
    with get_connection() as connection:
        columns = {
            row["column_name"]
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'approval_requests'
                """
            ).fetchall()
        }

    assert "workspace_id" in columns
    assert "approval_scope" in columns
    assert "expires_at" in columns
    assert "approved_until" in columns
