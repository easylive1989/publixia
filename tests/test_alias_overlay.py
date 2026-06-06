"""apply_alias_overlays pushes code-defined aliases onto existing roster rows,
making nicknames resolve without a full sync."""
from repositories.stock_reference import upsert_reference_batch
from services.normalization import normalize
from services.stock_reference_sync import apply_alias_overlays


def test_overlay_makes_english_name_resolve():
    # roster row exists (as the SEC sync would create it) but with no aliases
    upsert_reference_batch([
        {"ticker": "NVDA", "market": "US", "canonical_name": "NVIDIA CORP"},
    ], source="sec")
    assert normalize("NVIDIA") == (None, None)  # not resolvable yet

    updated = apply_alias_overlays()

    assert updated >= 1
    assert normalize("NVIDIA") == ("NVDA", "US")  # now resolves via overlay alias


def test_overlay_skips_missing_ticker():
    # PLTR not in roster → overlay update is a no-op for it, doesn't crash
    apply_alias_overlays()
    assert normalize("Palantir") == (None, None)
