"""Local offline research job control; no trading imports, shell or credentials.

Only byte-identical, successfully validated CSVs become runnable experiments.
"""
import hashlib,json,os,subprocess,sys,tempfile,threading
from pathlib import Path

_LOCK=threading.Lock();_CHILDREN={}
ROOT=Path(__file__).resolve().parents[2]
_MAX_CSV_BYTES=25*1024*1024

def research_root():
    return Path(os.environ.get('MOEX_DATA_DIR',str(Path.home()/'.moex-intelligence')))/'coliseum-research'

def _registered_source(folder):
    """Reject stale/invalid uploads, modified bytes, symlinks, and foreign paths."""
    folder=Path(folder).resolve()
    root=research_root().resolve()
    if folder.parent!=root or len(folder.name)!=64 or any(c not in '0123456789abcdef' for c in folder.name):
        raise ValueError('Unknown registered experiment')
    source=folder/'source.csv'
    receipt=folder/'registration.json'
    if (source.is_symlink() or receipt.is_symlink() or
            not source.is_file() or not receipt.is_file()):
        raise ValueError('Unvalidated or missing research source')
    try:
        recorded=json.loads(receipt.read_text())
    except (OSError,ValueError) as exc:
        raise ValueError('Corrupt research registration') from exc
    if not isinstance(recorded,dict) or recorded.get('sha256')!=folder.name or hashlib.sha256(source.read_bytes()).hexdigest()!=folder.name:
        raise ValueError('Research source changed after validation')
    return source

def registered_folders():
    root=research_root()
    if not root.is_dir():return []
    valid=[]
    for folder in sorted(root.iterdir()):
        try:_registered_source(folder)
        except (ValueError,OSError):continue
        valid.append(folder)
    return valid

def register_csv(content):
    if not isinstance(content,bytes) or not 0<len(content)<=_MAX_CSV_BYTES:
        raise ValueError('CSV must be 1 byte–25 MiB')
    identity=hashlib.sha256(content).hexdigest()
    root=research_root().resolve()
    root.mkdir(parents=True,exist_ok=True)
    folder=root/identity
    if folder.is_symlink():raise ValueError('Research folder cannot be a symlink')
    folder.mkdir(exist_ok=True)
    path=folder/'source.csv'
    receipt=folder/'registration.json'
    if path.is_symlink() or receipt.is_symlink():
        raise ValueError('Research source cannot be a symlink')
    from .coliseum_data import load_history
    guard=json.loads((ROOT/'docs/research/original_holdout_guard.json').read_text())
    protected=None if identity==guard['source_sha256'] else guard['sealed_interval']
    pending=None
    try:
        if path.exists():
            if path.read_bytes()!=content:raise ValueError('Immutable source mismatch')
            candidate=path
        else:
            # The canonical source.csv must never contain a file that failed validation.
            with tempfile.NamedTemporaryFile(dir=folder,prefix='.upload-',suffix='.csv',delete=False) as stream:
                pending=Path(stream.name)
                stream.write(content)
            candidate=pending
        try:
            _,quality=load_history(candidate,protected_interval=protected)
        except (KeyError,TypeError,UnicodeError) as exc:
            raise ValueError('Malformed research CSV') from exc
        if pending is not None:
            # Create-only atomic link prevents a concurrent upload from replacing source.csv.
            try:os.link(pending,path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes()!=content:
                    raise ValueError('Immutable source mismatch')
        # A registration receipt is published only after successful verification.
        registered=json.dumps(dict(sha256=identity,quality=quality),sort_keys=True)
        with tempfile.NamedTemporaryFile(dir=folder,prefix='.registration-',suffix='.tmp',
                                         mode='w',encoding='utf-8',delete=False) as stream:
            staged_receipt=Path(stream.name)
            stream.write(registered)
        try:os.replace(staged_receipt,receipt)
        finally:staged_receipt.unlink(missing_ok=True)
    finally:
        if pending is not None:pending.unlink(missing_ok=True)
    return folder,quality

def start(folder):
    folder=Path(folder).resolve()
    source=_registered_source(folder)
    output=folder/'study'
    output.mkdir(exist_ok=True)
    with _LOCK:
        child=_CHILDREN.get(str(folder))
        if child and child.poll() is None:return
        (output/'cancel.requested').unlink(missing_ok=True)
        with (folder/'worker.log').open('ab') as log:
            _CHILDREN[str(folder)]=subprocess.Popen(
                [sys.executable,str(ROOT/'scripts/run_coliseum_v02.py'),str(source),str(output)],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

def pause(folder):
    folder=Path(folder).resolve()
    _registered_source(folder)
    study=folder/'study'
    if not study.is_dir():raise ValueError('Research has not started')
    (study/'cancel.requested').touch()

def status(folder):
    import fcntl
    folder=Path(folder)
    _registered_source(folder)
    out=folder/'study'
    running=False
    if (out/'.writer.lock').exists():
        with (out/'.writer.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
            except BlockingIOError:running=True
    completed=sum(1 for p in out.glob('*.json') if len(p.stem)==64)
    log=(folder/'worker.log').read_text(errors='replace')[-6000:] if (folder/'worker.log').exists() else ''
    return dict(running=running,completed=completed,result=(out/'result.json').exists(),log=log)
