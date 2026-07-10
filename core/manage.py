import argparse
import secrets

from core.db import repository
from core.db.session import SessionLocal
from core.security import hash_api_key


def create_api_key(db, name: str) -> str:
    raw_key = secrets.token_urlsafe(32)
    repository.create_api_key(db, name=name, key_hash=hash_api_key(raw_key))
    return raw_key


def main():
    parser = argparse.ArgumentParser(prog="manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-api-key")
    create_parser.add_argument("--name", required=True)

    args = parser.parse_args()

    if args.command == "create-api-key":
        db = SessionLocal()
        try:
            raw_key = create_api_key(db, args.name)
        finally:
            db.close()
        print(f"API key creada para '{args.name}': {raw_key}")
        print("Guárdala ahora; no se puede recuperar después (solo se almacena su hash).")


if __name__ == "__main__":
    main()
