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

from . import ops, scheduler_ops
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
    table.add_column("STRATEGY")
    table.add_column("TOP100")
    table.add_column("FFUT")
    table.add_column("WEBHOOK")

    status_color = {
        "active": "[green]active[/green]",
        "expired": "[yellow]expired[/yellow]",
        "none": "[dim]none[/dim]",
    }
    for u in users:
        strategy_cell = (
            "[green]✓[/green]" if u.get("can_use_strategy")
            else "[dim]✗[/dim]"
        )
        top100_cell = (
            "[green]✓[/green]" if u.get("can_view_top100")
            else "[dim]✗[/dim]"
        )
        ffut_cell = (
            "[green]✓[/green]" if u.get("can_view_foreign_futures")
            else "[dim]✗[/dim]"
        )
        webhook_cell = u.get("webhook_display", "—")
        if webhook_cell == "—":
            webhook_cell = "[dim]—[/dim]"
        table.add_row(
            str(u["id"]),
            u["name"],
            u["created_at"] or "-",
            u["token_prefix"] or "-",
            (u["token_expires_at"] or "never") if u["token_id"] else "-",
            status_color.get(u["token_status"], u["token_status"]),
            strategy_cell,
            top100_cell,
            ffut_cell,
            webhook_cell,
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
    choices.append(questionary.Choice("[back]", value="back"))
    picked = questionary.select("Pick a user:", choices=choices).ask()
    if picked in (None, "back"):
        return

    _user_action_menu(picked)


def _user_action_menu(user: dict) -> None:
    while True:
        action = questionary.select(
            f"User '{user['name']}' (id={user['id']}, "
            f"token={user['token_status']}, "
            f"strategy={'on' if user.get('can_use_strategy') else 'off'}, "
            f"top100={'on' if user.get('can_view_top100') else 'off'}, "
            f"ffut={'on' if user.get('can_view_foreign_futures') else 'off'}):",
            choices=[
                questionary.Choice("Refresh token", value="refresh"),
                questionary.Choice(
                    "Revoke active token",
                    value="revoke",
                    disabled=None if user["token_status"] == "active" else "no active token",
                ),
                questionary.Choice("Toggle strategy permission", value="toggle_strategy"),
                questionary.Choice("Toggle top-100 permission", value="toggle_top100"),
                questionary.Choice("Toggle foreign-futures permission", value="toggle_ffut"),
                questionary.Choice("Set Discord webhook URL", value="set_webhook"),
                questionary.Choice(
                    "Clear Discord webhook URL",
                    value="clear_webhook",
                    disabled=None if user.get("discord_webhook_url") else "no webhook set",
                ),
                questionary.Choice("[back]", value="back"),
            ],
        ).ask()

        if action in (None, "back"):
            return
        if action == "refresh":
            _action_refresh_token(user)
        elif action == "revoke":
            if questionary.confirm(
                f"Revoke active token for '{user['name']}'?", default=False,
            ).ask():
                if ops.revoke_active_token(user["id"]):
                    console.print("[green]Token revoked.[/green]")
                else:
                    console.print("[yellow]No active token to revoke.[/yellow]")
        elif action == "toggle_strategy":
            new_state = not bool(user.get("can_use_strategy"))
            ops.set_strategy_permission(user["id"], new_state)
            console.print(
                f"[green]Strategy permission for '{user['name']}' = "
                f"{'ON' if new_state else 'OFF'}[/green]"
            )
        elif action == "toggle_top100":
            new_state = not bool(user.get("can_view_top100"))
            ops.set_top100_permission(user["id"], new_state)
            console.print(
                f"[green]Top-100 permission for '{user['name']}' = "
                f"{'ON' if new_state else 'OFF'}[/green]"
            )
        elif action == "toggle_ffut":
            new_state = not bool(user.get("can_view_foreign_futures"))
            ops.set_foreign_futures_permission(user["id"], new_state)
            console.print(
                f"[green]Foreign-futures permission for '{user['name']}' = "
                f"{'ON' if new_state else 'OFF'}[/green]"
            )
        elif action == "set_webhook":
            _action_set_webhook(user)
        elif action == "clear_webhook":
            affected = ops.clear_discord_webhook_with_cascade(
                user["id"], also_disable_strategies=False,
            )
            if affected:
                console.print(
                    f"[yellow]Warning: {len(affected)} active strategy "
                    f"row(s) will silently fail to send notifications "
                    f"until a new webhook is set.[/yellow]"
                )
                also = questionary.confirm(
                    "Auto-disable those strategies now?", default=False,
                ).ask()
                if also:
                    ops.clear_discord_webhook_with_cascade(
                        user["id"], also_disable_strategies=True,
                    )
                    console.print(
                        f"[green]Webhook cleared and "
                        f"{len(affected)} strategies disabled.[/green]"
                    )
                else:
                    console.print(
                        "[green]Webhook cleared "
                        "(strategies left enabled).[/green]"
                    )
            else:
                console.print("[green]Webhook cleared.[/green]")

        # Refresh the row so subsequent menu iterations see new state.
        users = ops.list_users_with_token()
        latest = next((u for u in users if u["id"] == user["id"]), None)
        if latest is None:
            return
        user = latest


def _action_set_webhook(user: dict) -> None:
    while True:
        url = questionary.text(
            "Discord webhook URL:",
            validate=lambda v: True if v.strip().startswith("https://") else (
                "URL must start with https://"
            ),
        ).ask()
        if not url:
            return
        url = url.strip()
        try:
            result = ops.set_discord_webhook(user["id"], url)
        except ValueError as e:
            console.print(f"[red]Rejected:[/red] {e}")
            if not questionary.confirm("Try again?", default=True).ask():
                return
            continue
        break

    if result.test_ping_sent:
        console.print(
            f"[green]Webhook set for '{user['name']}' "
            f"and test ping delivered.[/green]"
        )
    else:
        console.print(
            f"[yellow]Webhook saved for '{user['name']}' but the test "
            f"ping was skipped (user not found?).[/yellow]"
        )
    console.print(
        "[dim](Strategy notifications will now use this URL.)[/dim]"
    )


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


def _render_scheduler_table(jobs: list[dict]) -> None:
    if not jobs:
        console.print(
            "[yellow]No scheduler rows yet — start the backend once to "
            "seed defaults.[/yellow]"
        )
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("NAME")
    table.add_column("CRON")
    table.add_column("ENABLED")
    table.add_column("LAST RUN")
    table.add_column("STATUS")

    status_color = {
        "ok":    "[green]ok[/green]",
        "error": "[red]error[/red]",
    }
    for j in jobs:
        enabled_cell = (
            "[green]yes[/green]" if j["enabled"] else "[dim]no[/dim]"
        )
        status = j["last_status"] or "-"
        table.add_row(
            j["name"],
            j["cron_expr"],
            enabled_cell,
            j["last_run_at"] or "-",
            status_color.get(status, status),
        )
    console.print(table)


def _action_scheduler_menu() -> None:
    while True:
        jobs = scheduler_ops.list_jobs()
        _render_scheduler_table(jobs)
        if not jobs:
            return
        choices = [
            questionary.Choice(
                f"{j['name']}  [{j['cron_expr']}]"
                f"  ({'on' if j['enabled'] else 'off'})",
                value=j,
            )
            for j in jobs
        ]
        choices.append(questionary.Choice("[back]", value="back"))
        picked = questionary.select("Pick a job:", choices=choices).ask()
        if picked in (None, "back"):
            return
        _job_action_menu(picked)


def _job_action_menu(job: dict) -> None:
    while True:
        action = questionary.select(
            f"Job '{job['name']}' (cron='{job['cron_expr']}', "
            f"enabled={'yes' if job['enabled'] else 'no'}):",
            choices=[
                questionary.Choice("Edit cron expression", value="edit"),
                questionary.Choice(
                    "Disable" if job["enabled"] else "Enable",
                    value="toggle",
                ),
                questionary.Choice("[back]", value="back"),
            ],
        ).ask()

        if action in (None, "back"):
            return
        if action == "edit":
            _action_edit_cron(job)
        elif action == "toggle":
            new_enabled = not bool(job["enabled"])
            scheduler_ops.set_enabled(job["name"], new_enabled)
            console.print(
                f"[green]Set '{job['name']}' enabled = "
                f"{new_enabled}.[/green]"
            )
            console.print(
                "[dim]Restart the backend (top menu → Restart backend "
                "service) for the change to take effect.[/dim]"
            )

        # Refresh the row from DB so subsequent menu choices are accurate.
        latest = next(
            (j for j in scheduler_ops.list_jobs() if j["name"] == job["name"]),
            None,
        )
        if latest is None:
            return
        job = latest


def _action_edit_cron(job: dict) -> None:
    while True:
        new_expr = questionary.text(
            "Cron expression (5 fields: m h dom mon dow):",
            default=job["cron_expr"],
        ).ask()
        if new_expr is None:
            return
        new_expr = new_expr.strip()
        if not new_expr or new_expr == job["cron_expr"]:
            return
        err = scheduler_ops.validate_cron(new_expr)
        if err:
            console.print(f"[red]Invalid cron:[/red] {err}")
            if not questionary.confirm("Try again?", default=True).ask():
                return
            continue
        scheduler_ops.update_cron(job["name"], new_expr)
        console.print(
            f"[green]Updated '{job['name']}' cron → '{new_expr}'.[/green]"
        )
        console.print(
            "[dim]Restart the backend (top menu → Restart backend "
            "service) for the change to take effect.[/dim]"
        )
        return


def _action_restart_backend() -> None:
    if not questionary.confirm(
        "Restart 'stock-dashboard' systemd service now?", default=False,
    ).ask():
        return
    ok, output = scheduler_ops.restart_backend()
    if ok:
        console.print(f"[green]{output}[/green]")
    else:
        console.print(f"[red]Restart failed:[/red] {output}")


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
                questionary.Choice("Manage scheduler", value="scheduler"),
                questionary.Choice("Restart backend service", value="restart"),
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
                    ] + [questionary.Choice("[back]", value="back")],
                ).ask()
                if picked not in (None, "back"):
                    _action_refresh_token(picked)
            elif action == "scheduler":
                _action_scheduler_menu()
            elif action == "restart":
                _action_restart_backend()
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return 1


if __name__ == "__main__":
    sys.exit(main())
