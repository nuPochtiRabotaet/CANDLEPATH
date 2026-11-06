"""Opt-in access to archived Invest UI; no migration or portfolio writes."""
import os


def legacy_invest_enabled() -> bool:
    """Keep v0.9 crypto-first; allow manual recovery of old research UI."""
    return os.environ.get("CANDLEPATH_ENABLE_LEGACY_INVEST") == "1"
