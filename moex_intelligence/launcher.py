"""Loopback-only supervisor. A saved PID is never used as authority to kill."""
from __future__ import annotations
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.request import build_opener, ProxyHandler, Request
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.runtime'
PIDFILE = STATE / 'launcher.json'


def control(info, action='status'):
    try:
        port, token = info['control_port'], info['token']
        if type(port) is not int or not 1024 <= port <= 65535 or not isinstance(token, str) or len(token) != 32:
            return None
        request = Request(f'http://127.0.0.1:{port}/__moex_control__', data=json.dumps({'action': action}).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({})).open(request, timeout=.6) as response:
            result = json.loads(response.read(4096))
        if isinstance(result, dict) and result.get('service') == 'moex-local-supervisor' and result.get('instance') == token:
            return result
    except (KeyError, ValueError, TypeError, OSError):
        pass
    return None


def process_owned(info):
    return control(info) is not None


def read_state():
    try:
        result = json.loads(PIDFILE.read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def available_port():
    for port in range(8501, 8511):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError('Порты 8501–8510 заняты. Освободите один порт и повторите запуск.')


def healthy(url):
    try:
        with build_opener(ProxyHandler({})).open(url + '/_stcore/health', timeout=.5) as response:
            return response.read() == b'ok'
    except OSError:
        return False


def start(open_browser=True):
    info = read_state()
    if process_owned(info):
        if not healthy(info['url']):
            raise RuntimeError('Свой процесс запускается или не отвечает. Выполните stop.command и повторите.')
        print('Уже запущено: ' + info['url'])
        if open_browser:
            webbrowser.open(info['url'])
        return info
    port, token = available_port(), uuid.uuid4().hex
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        control_port = sock.getsockname()[1]
    STATE.mkdir(exist_ok=True, mode=0o700)
    logpath = STATE / 'app.log'
    with logpath.open('a') as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', '--token', token,
                                    '--port', str(port), '--control-port', str(control_port)], cwd=ROOT,
                                   stdout=log, stderr=log, start_new_session=True)
    info = {'pid': process.pid, 'token': token, 'control_port': control_port, 'url': f'http://127.0.0.1:{port}'}
    temp = PIDFILE.with_suffix('.tmp')
    temp.write_text(json.dumps(info))
    temp.chmod(0o600)
    temp.replace(PIDFILE)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f'Ошибка запуска. Подробности: {logpath}')
        if process_owned(info) and healthy(info['url']):
            print('MOEX Intelligence: ' + info['url'])
            if open_browser:
                webbrowser.open(info['url'])
            return info
        time.sleep(.15)
    # Only the child object just created here is eligible for this signal.
    process.terminate()
    raise RuntimeError(f'Приложение не ответило вовремя. Подробности: {logpath}')


def stop():
    info = read_state()
    if not info:
        print('Приложение не запущено этим launcher.')
        return
    if control(info, 'stop') is None:
        PIDFILE.unlink(missing_ok=True)
        print('Активный собственный supervisor не найден. Сторонние процессы не остановлены.')
        return
    for _ in range(80):
        if not process_owned(info):
            PIDFILE.unlink(missing_ok=True)
            print('MOEX Intelligence остановлен.')
            return
        time.sleep(.1)
    raise RuntimeError('Остановка ещё не завершена. Повторите stop.command.')


def worker(port, control_port, token):
    done = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            if self.path != '/__moex_control__' or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 1024:
                    raise ValueError('length')
                action = json.loads(self.rfile.read(length)).get('action')
                if action not in ('status', 'stop'):
                    raise ValueError('action')
            except (ValueError, AttributeError):
                self.send_error(400)
                return
            body = json.dumps({'service': 'moex-local-supervisor', 'instance': token}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if action == 'stop':
                done.set()
    server = ThreadingHTTPServer(('127.0.0.1', control_port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    child = None
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    try:
        child = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                                  '--server.address', '127.0.0.1', '--server.port', str(port)], cwd=ROOT)
        while child.poll() is None and not done.wait(.1):
            pass
        return child.returncode or 0
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'worker'])
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--token')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--control-port', type=int)
    args = parser.parse_args()
    try:
        if args.action == 'start':
            start(not args.no_browser)
        elif args.action == 'stop':
            stop()
        elif args.action == 'worker':
            if not args.token or len(args.token) != 32 or not args.control_port:
                raise RuntimeError('Некорректные параметры supervisor.')
            return worker(args.port, args.control_port, args.token)
        else:
            info = read_state()
            print(info.get('url') if process_owned(info) else 'Не запущено')
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
