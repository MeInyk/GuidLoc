"""Integration test ensuring Alembic migrations apply cleanly on a fresh database."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_head_creates_users_table() -> None:
    """Run `alembic upgrade head` in a subprocess against a temp SQLite file
    and verify that the expected schema is produced.

    A subprocess is used to avoid polluting the parent test process with
    Settings/lru_cache state and to fully isolate the database URL.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration_test.db"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        sync_url = f"sqlite:///{db_path}"

        env = os.environ.copy()
        env["DATABASE_URL"] = async_url

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"alembic upgrade head failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert db_path.exists(), "Database file was not created by Alembic"

        engine = create_engine(sync_url)
        try:
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            assert "users" in tables
            columns = {c["name"] for c in inspector.get_columns("users")}
            assert {
                "id",
                "email",
                "password_hash",
                "first_name",
                "last_name",
                "is_superuser",
                "created_at",
                "updated_at",
            }.issubset(columns)

            assert "location_change_requests" in tables
            change_request_columns = {
                c["name"] for c in inspector.get_columns("location_change_requests")
            }
            assert {
                "id",
                "created_by_user_id",
                "location_id",
                "change_type",
                "status",
                "reason",
                "proposed_changes",
                "original_snapshot",
                "original_location_updated_at",
                "merged_location_id",
                "merged_by_user_id",
                "merged_at",
                "created_at",
                "updated_at",
            }.issubset(change_request_columns)
        finally:
            engine.dispose()
