"""Interactive admin CLI.

Run from repo root:
    python -m admin

Reads DB_PATH from environment (defaults to backend/stock_dashboard.db).
"""
import sqlite3
import sys

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import ops
from .db import db_path


console = Console()


def _render_users_table(users: list[dict]) -> None:
    if not users:
        console.print("[dim](no users)[/dim]")
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", justify="right")
    table.add_column("NAME")
    table.add_column("CREATED")
    table.add_column("TOKEN PREFIX")
    table.add_column("TOKEN EXPIRES")
    table.add_column("STATUS")

    status_color = {
        "active": "[green]active[/green]",
        "expired": "[yellow]expired[/yellow]",
        "none": "[dim]none[/dim]",
    }
    for u in users:
        table.add_row(
            str(u["id"]),
            u["name"],
            u["created_at"] or "-",
            u["token_prefix"] or "-",
            (u["token_expires_at"] or "never") if u["token_id"] else "-",
            status_color.get(u["token_status"], u["token_status"]),
        )
    console.print(table)


def _action_list_users() -> None:
    users = ops.list_users_with_token()
    _render_users_table(users)
    if not users:
        return

    choices = [
        questionary.Choice(
            f"{u['name']} (id={u['id']}, token={u['token_status']})",
            value=u,
        )
        for u in users
    ]
    choices.append(questionary.Choice("[back]", value=None))
    picked = questionary.select("Pick a user:", choices=choices).ask()
    if picked is None:
        return

    _user_action_menu(picked)


def _user_action_menu(user: dict) -> None:
    while True:
        action = questionary.select(
            f"User '{user['name']}' (id={user['id']}, token={user['token_status']}):",
            choices=[
                questionary.Choice("Refresh token", value="refresh"),
                questionary.Choice(
                    "Revoke active token",
                    value="revoke",
                    disabled=None if user["token_status"] == "active" else "no active token",
                ),
                questionary.Choice("[back]", value="back"),
            ],
        ).ask()

        if action in (None, "back"):
            return
        if action == "refresh":
            _action_refresh_token(user)
            users = ops.list_users_with_token()
            user = next((u for u in users if u["id"] == user["id"]), user)
        elif action == "revoke":
            if questionary.confirm(
                f"Revoke active token for '{user['name']}'?",
                default=False,
            ).ask():
                if ops.revoke_active_token(user["id"]):
                    console.print("[green]Token revoked.[/green]")
                else:
                    console.print("[yellow]No active token to revoke.[/yellow]")
            users = ops.list_users_with_token()
            user = next((u for u in users if u["id"] == user["id"]), user)


def _action_create_user() -> None:
    name = questionary.text(
        "User name:",
        validate=lambda v: True if v.strip() else "name cannot be empty",
    ).ask()
    if not name:
        return
    name = name.strip()
    try:
        uid = ops.create_user(name)
    except sqlite3.IntegrityError:
        console.print(f"[red]User '{name}' already exists.[/red]")
        return
    console.print(f"[green]Created user[/green] id={uid} name={name}")

    if questionary.confirm(
        f"Issue a token for '{name}' now?", default=True,
    ).ask():
        _action_refresh_token({"id": uid, "name": name})


def _action_refresh_token(user: dict) -> None:
    label = questionary.text(
        "Token label:",
        default=f"{user['name']}-{_today_label()}",
        validate=lambda v: True if v.strip() else "label cannot be empty",
    ).ask()
    if not label:
        return

    expiry_choice = questionary.select(
        "Expiry:",
        choices=[
            questionary.Choice("365 days (default)", value=365),
            questionary.Choice("30 days", value=30),
            questionary.Choice("Never", value=None),
            questionary.Choice("Custom...", value="custom"),
        ],
    ).ask()
    if expiry_choice == "custom":
        days_str = questionary.text(
            "Days until expiry:",
            validate=lambda v: v.isdigit() and int(v) > 0 or "positive integer required",
        ).ask()
        if not days_str:
            return
        expiry_days = int(days_str)
    else:
        expiry_days = expiry_choice

    if not questionary.confirm(
        f"Issue new token for '{user['name']}' "
        f"(revokes existing active token)?",
        default=True,
    ).ask():
        return

    plaintext, token_id = ops.refresh_token(
        user_id=user["id"], label=label.strip(), expiry_days=expiry_days,
    )
    console.print(
        Panel.fit(
            f"[bold]Token id:[/bold]   {token_id}\n"
            f"[bold]User:[/bold]       {user['name']} (id={user['id']})\n"
            f"[bold]Label:[/bold]      {label}\n"
            f"[bold]Expires:[/bold]    "
            f"{'never' if expiry_days is None else f'in {expiry_days} days'}\n"
            f"\n[bold yellow]Token (only shown once):[/bold yellow]\n"
            f"[bold cyan]{plaintext}[/bold cyan]",
            title="Token issued",
            border_style="green",
        )
    )


def _today_label() -> str:
    from datetime import date
    return date.today().isoformat()


def main() -> int:
    console.print(
        Panel.fit(
            f"[bold]Publixia Admin[/bold]\nDB: [dim]{db_path()}[/dim]",
            border_style="cyan",
        )
    )

    while True:
        action = questionary.select(
            "What do you want to do?",
            choices=[
                questionary.Choice("List users", value="list"),
                questionary.Choice("Create user", value="create"),
                questionary.Choice("Refresh token", value="refresh"),
                questionary.Choice("Quit", value="quit"),
            ],
        ).ask()

        if action in (None, "quit"):
            return 0
        try:
            if action == "list":
                _action_list_users()
            elif action == "create":
                _action_create_user()
            elif action == "refresh":
                users = ops.list_users_with_token()
                if not users:
                    console.print("[yellow]No users yet — create one first.[/yellow]")
                    continue
                picked = questionary.select(
                    "Pick a user to refresh token for:",
                    choices=[
                        questionary.Choice(
                            f"{u['name']} (token={u['token_status']})",
                            value=u,
                        )
                        for u in users
                    ] + [questionary.Choice("[back]", value=None)],
                ).ask()
                if picked is not None:
                    _action_refresh_token(picked)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return 1


if __name__ == "__main__":
    sys.exit(main())
