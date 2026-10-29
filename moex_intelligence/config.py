"""Small, explicit local configuration. No broker or LLM secrets are required."""
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone


@dataclass(frozen=True)
class Settings:
    host: str = '127.0.0.1'
    port: int = 8000
    cache_ttl: int = 300
    data_dir: Path = Path.home() / '.moex-intelligence'

    @classmethod
    def from_env(cls):
        host = os.getenv('HOST', '127.0.0.1')
        if host not in {'127.0.0.1', 'localhost', '::1'} or os.getenv('PUBLIC_HOST'):
            raise ValueError('Only loopback access is supported. Public hosting requires a separate authenticated deployment.')
        port = int(os.getenv('PORT', '8000'))
        ttl = int(os.getenv('MOEX_CACHE_TTL', '300'))
        if not 1024 <= port <= 65535 or not 0 <= ttl <= 3600:
            raise ValueError('PORT must be 1024–65535; MOEX_CACHE_TTL must be 0–3600 seconds.')
        return cls(host, port, ttl, Path(os.getenv('MOEX_DATA_DIR', str(cls.data_dir))).expanduser())


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(), 'level': record.levelname,
                           'logger': record.name, 'event': record.getMessage()}, ensure_ascii=False)


def configure_logging():
    handler = logging.StreamHandler(sys.stderr)  # stdout belongs to MCP stdio.
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger('moex_intelligence')
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
