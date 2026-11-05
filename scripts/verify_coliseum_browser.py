"""Actual Chromium/Streamlit saved-report smoke; no external-market claims."""
import os,json,subprocess,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

server=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/coliseum_ui_fixture.py',
    '--server.address=127.0.0.1','--server.port=8521','--server.headless=true'],
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen('http://127.0.0.1:8521/_stcore/health',timeout=1);break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('Streamlit did not start')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1280,'height':900})
        page.goto('http://127.0.0.1:8521')
        page.get_by_role('heading',name='Strategy Coliseum',exact=True).wait_for(timeout=60000)
        page.get_by_text('Независимо подтверждено',exact=True).wait_for(timeout=30000)
        page.get_by_text('Карточка стратегии',exact=True).wait_for(timeout=30000)
        page.get_by_role('button',name='Экспорт результатов JSON').wait_for(timeout=30000)
        assert page.locator('[data-testid="stException"]').count()==0
        page.locator('[data-testid="stPlotlyChart"]').nth(1).wait_for(timeout=30000)
        for width in (1024,1280,1440,1920):
            page.set_viewport_size({'width':width,'height':1000})
            assert page.locator('[data-testid="stPlotlyChart"]').count()>=2
            if os.environ.get('COLISEUM_SCREENSHOTS'):
                target=Path(os.environ['COLISEUM_SCREENSHOTS']);target.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(target/f'coliseum-{width}.png'),full_page=True)
        with page.expect_download() as d:page.get_by_role('button',name='Экспорт результатов JSON').click()
        result=json.loads(Path(d.value.path()).read_text())
        assert result['study']['sealed_final_evaluated'] is False and result['production_integrations']==0
        browser.close()
finally:
    server.terminate();server.wait(timeout=10)
print('PASS: Streamlit/Chromium saved report, chart presence, 4 widths, export; not Safari or live data')
