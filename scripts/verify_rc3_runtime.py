"""Isolated real-process launcher smoke and shell syntax check (not a physical Mac test)."""
import json
import os
import platform
import subprocess
import tempfile
from datetime import datetime,timezone
from pathlib import Path


def main():
    from moex_intelligence import launcher
    root=Path(__file__).resolve().parents[1]
    for path in root.glob('*.command'):
        subprocess.run(['bash','-n',str(path)],check=True)
    with tempfile.TemporaryDirectory(prefix='moex-runtime-') as folder:
        os.environ['MOEX_DATA_DIR']=str(Path(folder)/'data')
        launcher.STATE=Path(folder)/'runtime'
        launcher.PIDFILE=launcher.STATE/'launcher.json'
        try:
            first=launcher.start(open_browser=False)
            assert launcher.healthy(first['url'])
            second=launcher.start(open_browser=False)
            assert first==second and launcher.process_owned(first)
            launcher.stop()
            assert not launcher.process_owned(first) and not launcher.PIDFILE.exists()
        finally:
            if launcher.PIDFILE.exists():launcher.stop()
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
            'shell_syntax':['setup.command','start.command','stop.command','check_moex.command'],
            'launcher_start_health':'PASS','reuse_own_instance':'PASS','stop_own_instance':'PASS',
            'physical_mac_tested':False,'gatekeeper_finder_safari_tested':False,'data':'isolated temporary directory'}
    output=root/'docs/rc3/runtime.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
