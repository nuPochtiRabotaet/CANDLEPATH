"""One-time SQLite backups before v0.6 creates new research snapshot kinds."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime,timezone


def ensure_v06_backup(data_dir):
    return _backup(data_dir,'0.6')


def ensure_v07_backup(data_dir):
    return _backup(data_dir,'0.7')


def ensure_v08_backup(data_dir):
    return _backup(data_dir,'0.8')


def ensure_v071_backup(data_dir):
    return _backup(data_dir,'0.7.1')


def _backup(data_dir,version):
    root=Path(data_dir);destination=root/'backups'/('before-v'+version)
    marker=destination/'completed.json'
    if marker.exists():return destination
    existing=[root/name for name in ['portfolio.sqlite3','research.sqlite3'] if (root/name).exists()]
    if not existing:return None  # New installs have no earlier user data to back up.
    destination.mkdir(parents=True,exist_ok=True)
    copied=[]
    for source in existing:
        target=destination/source.name
        if not target.exists():
            fd,temp=tempfile.mkstemp(prefix='.backup-',dir=destination);os.close(fd)
            try:
                with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(temp) as dst:src.backup(dst)
                # Keep the first completed snapshot if another session got here first.
                try:os.link(temp,target)
                except FileExistsError:pass
            finally:
                if os.path.exists(temp):os.unlink(temp)
        copied.append(source.name)
    body=json.dumps({'version':'before-v'+version,'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':copied})
    fd,temp=tempfile.mkstemp(prefix='.complete-',dir=destination)
    try:
        with os.fdopen(fd,'w') as f:f.write(body)
        os.replace(temp,marker)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return destination


def ensure_v081_backup(data_dir):
    return _backup(data_dir,'0.8.1')
