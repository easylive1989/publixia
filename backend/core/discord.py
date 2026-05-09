"""Tiny Discord webhook helper used by strategy + token services."""
import requests


def send_to_discord(webhook_url: str, payload: dict, timeout: int = 10) -> None:
    """POST a payload as JSON to a Discord webhook URL."""
    resp = requests.post(webhook_url, json=payload, timeout=timeout)
    resp.raise_for_status()
