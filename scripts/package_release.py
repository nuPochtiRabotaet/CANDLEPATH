"""Build a source-only ZIP with content manifest; excludes local databases and secrets."""
import hashlib
from pathlib import Path
import zipfile


def main():
    root=Path(__file__).resolve().parents[1]
    excluded={'.git','.venv','__pycache__','.pytest_cache','build','dist','artifacts','logs','.runtime','preview'}
    files=[]
    for path in root.rglob('*'):
        rel=path.relative_to(root)
        if not path.is_file() or any(p in excluded for p in rel.parts):continue
        if '.sqlite' in path.name or path.name.endswith(('.db','.db-wal','.db-shm','.db-journal','.v04-backup')) or path.name=='core' or path.suffix in {'.pyc','.pyo'} or path.name in {'.env','secrets.toml','MANIFEST.sha256'}:continue
        if path.name.startswith('.env.') and path.name!='.env.example':continue
        files.append(path)
    files.sort(key=lambda p:p.relative_to(root).as_posix())
    manifest=root/'MANIFEST.sha256'
    manifest.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n' for p in files))
    target=root.parent/'MOEX_Intelligence_v0.8.2-rc3.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in [*files,manifest]:
            info=zipfile.ZipInfo((Path(root.name)/path.relative_to(root)).as_posix(),date_time=(2026,10,29,0,0,0))
            info.external_attr=(0o100755 if path.suffix == ".command" else 0o100644)<<16
            archive.writestr(info,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        print(f'{target}: {len(archive.namelist())} files, {target.stat().st_size:,} bytes')
    print('SHA256',hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':main()
