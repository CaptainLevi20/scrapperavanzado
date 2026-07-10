import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test",
)
TEST_S3_ENDPOINT_URL = os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000")
TEST_S3_BUCKET = os.environ.get("TEST_S3_BUCKET", "iurisync-test")


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(bind=test_engine, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
