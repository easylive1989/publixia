"""CLI: issue / list / revoke API tokens.

Tokens are now scoped to a user (from migration 0003). One active
token per user — issuing a new one revokes the previous active row.
Create the user first via:  python -m scripts.manage_users create <name>

Usage (from backend/):
  python -m scripts.issue_token issue --user-name paul --label paul-laptop
  python -m scripts.issue_token issue --user-name paul --label tmp --expires-days 30
  python -m scripts.issue_token issue --user-name paul --label permanent --no-expiry
  python -m scripts.issue_token list
  python -m scripts.issue_token revoke <id>
"""
import argparse
import sys
from datetime import datetime, timezone

from core.logging import setup_logging
from db import init_db
from repositories.api_tokens import list_tokens, revoke_token
from repositories.users import get_user_by_name
from services.token_service import issue_token


def cmd_issue(args: argparse.Namespace) -> int:
    user = get_user_by_name(args.user_name)
    if user is None:
        print(
            f"error: user '{args.user_name}' not found.\n"
            f"  Run: python -m scripts.manage_users create {args.user_name}",
            file=sys.stderr,
        )
        return 1
    expiry = None if args.no_expiry else args.expires_days
    plaintext, token_id = issue_token(
        user_id=user["id"], label=args.label, expiry_days=expiry,
    )
    print(f"Token id:    {token_id}")
    print(f"User:        {user['name']} (id={user['id']})")
    print(f"Label:       {args.label}")
    print(f"Expires:     {'never' if expiry is None else f'in {expiry} days'}")
    print(f"Token (only shown once):")
    print(f"  {plaintext}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    rows = list_tokens()
    if not rows:
        print("(no tokens)")
        return 0
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    print(f"{'ID':>4}  {'USER':>4}  {'PREFIX':<14}  {'LABEL':<30}  "
          f"{'CREATED':<24}  {'LAST_USED':<24}  {'STATUS':<10}")
    for r in rows:
        if r["revoked_at"]:
            status = "revoked"
        elif r["expires_at"] and r["expires_at"] < now_iso:
            status = "expired"
        else:
            status = "active"
        print(
            f"{r['id']:>4}  {r['user_id']:>4}  {r['prefix']:<14}  "
            f"{r['label']:<30}  {r['created_at']:<24}  "
            f"{(r['last_used_at'] or '-'):<24}  {status:<10}"
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    ok = revoke_token(args.id)
    if ok:
        print(f"Revoked token id={args.id}")
        return 0
    print(f"Token id={args.id} not found or already revoked", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    init_db()

    parser = argparse.ArgumentParser(description="Stock Dashboard API token CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="issue a new token (rotates user's existing)")
    p_issue.add_argument("--user-name", required=True,
                         help="user this token belongs to (must exist)")
    p_issue.add_argument("--label", required=True, help="human-readable label")
    p_issue.add_argument("--expires-days", type=int, default=365, help="default 365")
    p_issue.add_argument("--no-expiry", action="store_true", help="never expires")
    p_issue.set_defaults(func=cmd_issue)

    p_list = sub.add_parser("list", help="list all tokens")
    p_list.set_defaults(func=cmd_list)

    p_revoke = sub.add_parser("revoke", help="revoke a token by id")
    p_revoke.add_argument("id", type=int)
    p_revoke.set_defaults(func=cmd_revoke)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
