"""Actual Chromium/Streamlit saved-report smoke; no external-market claims."""
import os,json,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

test_dir=tempfile.TemporaryDirectory(prefix='candlepath-coliseum-browser-')
env={**os.environ,'MOEX_DATA_DIR':test_dir.name,'CANDLEPATH_ENABLE_LEGACY_INVEST':'0'}
server=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/coliseum_ui_fixture.py',
    '--server.address=127.0.0.1','--server.port=8521','--server.headless=true'],
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
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
        page.get_by_role('button',name='Strategy Coliseum',exact=True).click(timeout=60000)
        page.get_by_role('heading',name='Strategy Coliseum',exact=True).wait_for(timeout=60000)
        page.get_by_text('Независимо подтверждено',exact=True).wait_for(timeout=30000)
        page.get_by_text('Карточка стратегии',exact=True).wait_for(timeout=30000)
        page.get_by_role('button',name='Экспорт результатов JSON').wait_for(timeout=30000)
        assert page.locator('[data-testid="stException"]').count()==0
        plots=page.locator('[data-testid="stPlotlyChart"]')
        plots.nth(4).wait_for(timeout=30000)
        page.get_by_text('Просадка по дневным отметкам капитала, %',exact=True).wait_for()
        page.get_by_text('Запуск и возобновление офлайн-исследования',exact=True).click()
        uploader=page.locator('input[type=file]')
        uploader.set_input_files({'name':'bad.csv','mimeType':'text/csv','buffer':b'bad\nvalue\n'})
        page.get_by_text('bad.csv',exact=True).wait_for()
        page.get_by_role('button',name='Проверить и зарегистрировать CSV').click()
        page.get_by_text('Malformed research CSV',exact=True).wait_for()
        assert page.get_by_role('button',name='Запустить / возобновить').count()==0
        bars='timestamp_ms,open,high,low,close,volume\n'+''.join(
            f'{1500000000000+i*300000},100,101,99,100,10\n' for i in range(420))
        uploader.set_input_files({'name':'fixture.csv','mimeType':'text/csv','buffer':bars.encode()})
        page.get_by_text('fixture.csv',exact=True).wait_for()
        page.get_by_text('Malformed research CSV',exact=True).wait_for(state='hidden')
        page.get_by_role('button',name='Проверить и зарегистрировать CSV').click()
        try:
            page.get_by_role('button',name='Запустить / возобновить').wait_for(timeout=10000)
        except Exception as exc:
            raise AssertionError(page.locator('[data-testid=stAlert]').all_inner_texts()) from exc
        page.get_by_role('button',name='Приостановить после текущего кандидата').wait_for()

        for width in (1024,1280,1440,1920):
            page.set_viewport_size({'width':width,'height':1000})
            assert page.locator('[data-testid="stPlotlyChart"]').count()>=2
            if os.environ.get('COLISEUM_SCREENSHOTS'):
                target=Path(os.environ['COLISEUM_SCREENSHOTS']);target.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(target/f'coliseum-{width}.png'),full_page=True)
        with page.expect_download() as d:page.get_by_role('button',name='Экспорт результатов JSON').click()
        result=json.loads(Path(d.value.path()).read_text())
        assert result['study']['sealed_final_evaluated'] is False and result['production_integrations']==0
        page.get_by_text('Trade',exact=True).click()
        page.get_by_role('button',name='Strategy Coliseum',exact=True).wait_for()
        assert page.locator('[data-testid="stException"]').count()==0
        browser.close()
finally:
    server.terminate();server.wait(timeout=10)
    test_dir.cleanup()
print('PASS: Streamlit/Chromium Trade ↔ Coliseum, CSV registration, saved charts at 4 widths and export')
