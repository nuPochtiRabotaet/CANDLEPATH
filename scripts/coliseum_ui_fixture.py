"""Real workbench navigation with the market feed disabled for browser QA."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from moex_intelligence.crypto import ui
from moex_intelligence.workbench import main

ui.monitor = lambda *_: None
ui.terminal = lambda *_: None
main()
