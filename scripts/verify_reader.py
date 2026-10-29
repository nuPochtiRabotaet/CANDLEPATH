"""Run unchanged original Reader smoke against compatibility server (real MOEX)."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def main():
    root=Path(__file__).resolve().parents[1]
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env={**os.environ,'HOST':'127.0.0.1','PORT':str(port),'PUBLIC_HOST':'','NO_PROXY':'localhost,127.0.0.1'}
    with open(root/'docs/reader-server.log','w') as server_log,open(root/'docs/reader-smoke.log','w') as result:
        process=subprocess.Popen([sys.executable,'server.py'],cwd=root,env=env,stdout=server_log,stderr=server_log)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:time.sleep(.1)
            run=subprocess.run([sys.executable,'smoke_test.py',f'http://127.0.0.1:{port}/mcp'],cwd=root,env=env,stdout=result,stderr=result,timeout=240)
            if run.returncode:raise RuntimeError('Reader smoke failed; see docs/reader-smoke.log')
            print('PASS unchanged original Reader smoke: 5 live tools and invalid input')
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
