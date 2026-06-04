"""Social-post scrapers (Scrapling-based).

Separate from ``fetchers/`` (the old market-data modules): scrapers drive a
stealth browser, scroll for pagination, and capture XHR. Today only Threads
is supported; the runner picks a scraper by ``account['platform']``.
"""
