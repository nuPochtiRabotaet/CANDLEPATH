"""The legacy Invest UI remains opt-in and defaults to hidden."""
from moex_intelligence.workspace_mode import legacy_invest_enabled


def test_legacy_invest_hidden_by_default(monkeypatch):
    monkeypatch.delenv("CANDLEPATH_ENABLE_LEGACY_INVEST", raising=False)
    assert legacy_invest_enabled() is False


def test_legacy_invest_can_be_reenabled(monkeypatch):
    monkeypatch.setenv("CANDLEPATH_ENABLE_LEGACY_INVEST", "1")
    assert legacy_invest_enabled() is True


def test_legacy_invest_not_enabled_by_arbitrary_truthy_strings(monkeypatch):
    for value in ("true", "yes", "0", "enabled"):
        monkeypatch.setenv("CANDLEPATH_ENABLE_LEGACY_INVEST", value)
        assert legacy_invest_enabled() is False
