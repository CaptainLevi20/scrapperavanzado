from core.security import hash_password, hash_session_token, verify_password


def test_hash_password_produces_a_verifiable_but_different_string():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash) is True


def test_verify_password_rejects_a_wrong_password():
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("wrong password", password_hash) is False


def test_hash_password_salts_so_the_same_password_hashes_differently():
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second


def test_hash_session_token_is_deterministic():
    assert hash_session_token("abc") == hash_session_token("abc")
    assert hash_session_token("abc") != hash_session_token("xyz")
