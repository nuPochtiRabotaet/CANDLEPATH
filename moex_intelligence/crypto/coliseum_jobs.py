"""Local offline research job control; no trading imports, shell or credentials."""
import hashlib,json,os,subprocess,sys,threading
from pathlib import Path

_LOCK=threading.Lock();_CHILDREN={}
ROOT=Path(__file__).resolve().parents[2]

def research_root():
    return Path(os.environ.get('MOEX_DATA_DIR',str(Path.home()/'.moex-intelligence')))/'coliseum-research'

def register_csv(content):
    if not content or len(content)>25*1024*1024:raise ValueError('CSV must be 1 byte–25 MiB')
    identity=hashlib.sha256(content).hexdigest();folder=research_root()/identity;folder.mkdir(parents=True,exist_ok=True)
    path=folder/'source.csv'
    if path.exists() and path.read_bytes()!=content:raise ValueError('Immutable source mismatch')
    if not path.exists():
        with path.open('xb') as stream:stream.write(content)
    from .coliseum_data import load_history
    guard=json.loads((ROOT/'docs/research/original_holdout_guard.json').read_text())
    rows,quality=load_history(path,protected_interval=None if identity==guard['source_sha256'] else guard['sealed_interval'])
    return folder,quality

def start(folder):
    folder=Path(folder).resolve();root=research_root().resolve()
    if folder.parent!=root or not (folder/'source.csv').is_file():raise ValueError('Unknown registered experiment')
    output=folder/'study';output.mkdir(exist_ok=True)
    with _LOCK:
        child=_CHILDREN.get(str(folder))
        if child and child.poll() is None:return
        (output/'cancel.requested').unlink(missing_ok=True)
        with (folder/'worker.log').open('ab') as log:
            _CHILDREN[str(folder)]=subprocess.Popen([sys.executable,str(ROOT/'scripts/run_coliseum_v02.py'),str(folder/'source.csv'),str(output)],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

def pause(folder):
    folder=Path(folder).resolve()
    if folder.parent!=research_root().resolve():raise ValueError('Unknown experiment')
    (folder/'study').mkdir(exist_ok=True)
    (folder/'study'/'cancel.requested').touch()

def status(folder):
    import fcntl
    folder=Path(folder);out=folder/'study';running=False
    if (out/'.writer.lock').exists():
        with (out/'.writer.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
            except BlockingIOError:running=True
    completed=sum(1 for p in out.glob('*.json') if len(p.stem)==64)
    log=(folder/'worker.log').read_text(errors='replace')[-6000:] if (folder/'worker.log').exists() else ''
    return dict(running=running,completed=completed,result=(out/'result.json').exists(),log=log)
