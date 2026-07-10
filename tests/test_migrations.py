import os
import subprocess

from sqlalchemy import create_engine, inspect

TEST_DATABASE_URL = "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test"

EXPECTED_TABLES = {
    "source_families",
    "sources",
    "runs",
    "run_sources",
    "run_errors",
    "documents",
    "api_keys",
}


def test_alembic_upgrade_head_creates_all_tables():
    # Note: inherit the full parent environment (not just DATABASE_URL/PATH) --
    # on Windows, a minimal env dict breaks asyncio/socket initialization
    # (WinError 10106) because SystemRoot and friends are missing.
    env = dict(os.environ, DATABASE_URL=TEST_DATABASE_URL)
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env=env,
        check=True,
    )
    engine = create_engine(TEST_DATABASE_URL, future=True)
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
    engine.dispose()
