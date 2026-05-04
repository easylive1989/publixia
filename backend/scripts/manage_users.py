"""CLI: manage users.

Usage (from backend/):
  python -m scripts.manage_users create <name>
  python -m scripts.manage_users list
"""
import argparse
import sqlite3
import sys

from core.logging import setup_logging
from db import init_db
from repositories.users import create_user, list_users


def cmd_create(args: argparse.Namespace) -> int:
    try:
        uid = create_user(args.name)
    except sqlite3.IntegrityError:
        print(f"error: user '{args.name}' already exists", file=sys.stderr)
        return 1
    print(f"Created user id={uid} name={args.name}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    users = list_users()
    if not users:
        print("(no users)")
        return 0
    print(f"{'ID':>4}  {'NAME':<20}  {'CREATED':<24}")
    for u in users:
        print(f"{u['id']:>4}  {u['name']:<20}  {u['created_at']:<24}")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    init_db()

    parser = argparse.ArgumentParser(description="Stock Dashboard user CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="create a new user")
    p_create.add_argument("name")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="list all users")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
