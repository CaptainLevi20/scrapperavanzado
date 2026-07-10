from core.db import repository
from core.manage import create_api_key
from core.security import hash_api_key


def test_create_api_key_returns_raw_key_and_stores_only_its_hash(db_session):
    raw_key = create_api_key(db_session, "integración-tests")

    assert len(raw_key) > 20
    found = repository.get_active_api_key_by_hash(db_session, hash_api_key(raw_key))
    assert found is not None
    assert found.name == "integración-tests"
