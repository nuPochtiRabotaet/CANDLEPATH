"""Streamlit/Chromium QA on isolated SYNTHETIC candles, never a market test."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]


def main():
    checks=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='candlepath-selective-qa-') as folder:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'MOEX_DATA_DIR':folder,'CANDLEPATH_ENABLE_LEGACY_INVEST':'1'}
        with open(Path(folder)/'server.log','w') as log:
            server=subprocess.Popen([sys.executable,'-m','streamlit','run','tests/crypto_ui_fixture.py',
                '--server.port',str(port),'--server.fileWatcherType','none'],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                for _ in range(150):
                    try:
                        urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1);break
                    except OSError:time.sleep(.1)
                else:raise AssertionError('Streamlit did not become ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or shutil.which('chromium'),
                        headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
                    page=browser.new_page(viewport={'width':1440,'height':1100})
                    page.set_default_timeout(30000)
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{port}')
                    page.get_by_test_id('stSidebar').get_by_text('Trade',exact=True).click()
                    page.locator('.terminal').wait_for()
                    panel=page.get_by_text('Что ограничивает размер Paper-заявки',exact=True)
                    panel.click()
                    expect(page.get_by_text('Расчётное количество:',exact=False)).to_be_visible()
                    assert page.get_by_test_id('stDataFrame').count()>=1
                    checks.append('Backend Decimal sizing limits visible in Streamlit')
                    page.get_by_text('Signal scan · полнота текущего инструмента',exact=True).click()
                    page.get_by_role('button',name='Проверить закрытые свечи',exact=True).click()
                    expect(page.get_by_text('COMPLETE · проверено 1 из 1 · исключено 0',exact=True)).to_be_visible()
                    checks.append('Closed-bar scan completeness with explicit selected-symbol scope')
                    page.evaluate("""()=>{const label=document.createElement('div');label.textContent='SYNTHETIC QA — NOT BYBIT LIVE';label.style.cssText='position:fixed;top:0;left:0;z-index:999999;background:#553300;color:white;padding:4px 12px;font:14px sans-serif';document.body.appendChild(label)}""")
                    for width in (1024,1280,1440,1920):
                        page.set_viewport_size({'width':width,'height':1100});page.wait_for_timeout(200)
                        assert page.locator('.terminal').is_visible()
                        assert page.get_by_test_id('stException').count()==0
                        if os.getenv('DAY_TRADER_SCREENSHOTS'):
                            out=Path(os.environ['DAY_TRADER_SCREENSHOTS']);out.mkdir(parents=True,exist_ok=True)
                            page.screenshot(path=str(out/f'synthetic-{width}.png'),full_page=True)
                    checks.append('Four widths 1024/1280/1440/1920 without Streamlit exceptions')
                    # Existing 25 USDT Preview -> Confirm still requires consent.
                    page.locator('.st-key-crypto_mode').get_by_text('Paper Trading',exact=True).click()
                    expect(page.locator('#buy')).to_be_enabled()
                    assert page.locator('#budget').input_value()=='25'
                    page.locator('#buy').click()
                    expect(page.locator('#confirmDialog')).to_be_visible()
                    expect(page.locator('#confirmOrder')).to_be_disabled()
                    page.locator('#cancelOrder').click()
                    expect(page.locator('#confirmDialog')).not_to_be_visible()
                    checks.append('25 USDT preview requires consent; cancel sends no fill')
                    assert page.locator('.terminal').evaluate('e=>e.__runtime.data.orders.length')==0
                    assert not errors,errors
                    browser.close()
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()
    print(json.dumps({'status':'PASS','data':'SYNTHETIC_QA','checks':checks,'javascript_errors':errors},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
