from hashlib import sha256


def hash_api_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()
