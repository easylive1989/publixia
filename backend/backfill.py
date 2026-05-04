"""CLI entry point. Delegates to services.backfill.

Run from backend/ as: python backfill.py
"""
from services.backfill import main

if __name__ == "__main__":
    from core.logging import setup_logging
    setup_logging()
    main()
