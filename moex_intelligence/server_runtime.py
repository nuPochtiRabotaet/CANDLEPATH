"""Start protection before Streamlit accepts browser sessions; no system service."""
import sys
from pathlib import Path
from streamlit.web import bootstrap
from .crypto.runtime import start, shutdown


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
    if not 1024 <= port <= 65535:
        raise ValueError('Invalid server port')
    start()
    try:
        bootstrap.run(str(Path(__file__).resolve().parents[1] / 'app.py'), False, [],
                      {'server.address': '127.0.0.1', 'server.port': port,
                       'server.headless': True})
    finally:
        shutdown()


if __name__ == '__main__':
    main()
