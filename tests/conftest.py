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


from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family


@register_family("test-dummy")
class DummyFamilyScraper(BaseScrapper):
    """Registered once at test-collection time; used by pipeline tests instead of hitting a real site."""

    docs_to_return: list[RawDocModel] = []

    def __init__(self, **_params):
        pass

    def scrap(self, fini, ffin, **kwargs):
        return DummyFamilyScraper.docs_to_return


@pytest.fixture()
def api_client(db_session):
    from fastapi.testclient import TestClient

    from api.deps import get_db
    from api.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_header(db_session):
    import secrets

    from core.db import repository
    from core.security import hash_password, hash_session_token

    user = repository.create_user(db_session, username="tester", password_hash=hash_password("Password123"))
    raw_token = secrets.token_urlsafe(32)
    repository.create_session(db_session, user_id=user.id, token_hash=hash_session_token(raw_token))
    return {"Authorization": f"Bearer {raw_token}"}
