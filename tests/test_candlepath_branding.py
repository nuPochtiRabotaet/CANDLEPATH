"""Guard current user-facing brand without breaking legacy Python imports."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_candlepath_is_package_distribution_name():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["name"] == "candlepath"
    assert project["description"].startswith("CandlePath:")


def test_app_titles_and_launcher_use_current_product_name():
    for relative in (
        "moex_intelligence/workbench.py",
        "moex_intelligence/dashboard.py",
        "moex_intelligence/launcher.py",
    ):
        source = (ROOT / relative).read_text()
        assert "CandlePath" in source, relative
        assert "MOEX Intelligence" not in source, relative


def test_branding_preserves_legacy_storage_compatibility():
    readme = (ROOT / "README.md").read_text()
    assert "# CandlePath" in readme
    assert "nuPochtiRabotaet/CANDLEPATH" in readme
    assert "moex_intelligence" in readme
    assert "MOEX_DATA_DIR" in readme
