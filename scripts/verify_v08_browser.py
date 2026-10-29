"""Run the real browser against a conspicuously labeled synthetic test adapter."""
import json,os,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v0.8/browser';OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[]
with tempfile.TemporaryDirectory(prefix='moex-v08-ui-') as directory:
 env={**os.environ,'MOEX_DATA_DIR':directory}
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 log=open(OUT/'server.log','w');proc=subprocess.Popen([sys.executable,'-m','streamlit','run','tests/crypto_ui_fixture.py','--server.port',str(port),'--server.fileWatcherType','none'],cwd=ROOT,env=env,stdout=log,stderr=log)
 try:
  for _ in range(150):
   try:urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1);break
   except OSError:time.sleep(.1)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=sys.argv[1],headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--disable-gpu-sandbox','--no-zygote']);page=browser.new_page(viewport={'width':1440,'height':1100});page.set_default_timeout(20000);page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{port}');page.get_by_text('Стоимость портфеля',exact=True).first.wait_for(timeout=30000);checks.append('Existing Invest overview loads')
   page.locator('.st-key-workspace_mode').get_by_text('Trade',exact=True).click();page.locator('.terminal').wait_for();page.wait_for_timeout(1800)
   page.screenshot(path=str(OUT/'initial.png'),full_page=True)
   print('ERRORS',errors,flush=True)
   expect(page.locator('#price')).not_to_have_text('—');assert page.locator('#chart canvas').count()>=4;checks.append('Candles and canvas render')
   state=page.locator('.terminal').evaluate('(e)=>({data:e.__runtime.candles.data().length,ribbon:e.__runtime.data.analysis.overlay.filter(x=>x.direction).length,signals:e.__runtime.data.signals.length,range:e.__runtime.chart.timeScale().getVisibleLogicalRange()})');print('STATE',state,flush=True);assert state['data']==280 and state['ribbon']>20 and state['signals']>0
   checks.append('Formula-generated ribbon and confirmed signals present')
   page.locator('.terminal').evaluate('e=>e.__qaChart=e.__runtime.chart');page.wait_for_timeout(2200);assert page.locator('.terminal').evaluate('e=>e.__qaChart===e.__runtime.chart');checks.append('Fragment updates retain chart instance')
   page.get_by_role('button',name='Чистый',exact=True).click();expect(page.locator('.terminal')).to_have_attribute('data-ribbon','false');assert page.locator('.terminal').evaluate('e=>e.__runtime.markers.markers().length')==0;checks.append('Clean preset removes layers')
   page.get_by_role('button',name='Полный',exact=True).click();assert page.locator('.terminal').evaluate('e=>e.__runtime.markers.markers().length')>0
   box=page.locator('#chart').bounding_box();before=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange()');page.mouse.move(box['x']+box['width']/2,box['y']+200);page.mouse.wheel(0,-320);page.wait_for_timeout(400);after=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange()');assert abs((after['to']-after['from'])-(before['to']-before['from']))>1;checks.append('Mouse wheel zoom')
   page.mouse.move(box['x']+box['width']/2,box['y']+80);page.mouse.down();page.mouse.move(box['x']+box['width']/2+90,box['y']+80,steps=8);page.mouse.up();page.wait_for_timeout(300);scrolled=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange()');assert abs(scrolled['from']-after['from'])>1;checks.append('Drag scroll')
   page.locator('#fit').click();page.locator('.st-key-crypto_mode').get_by_text('Paper Trading',exact=True).click();page.wait_for_timeout(700)
   page.locator('#quantity').fill('0.01');page.locator('#quantity').dispatch_event('input');expect(page.locator('#buy')).to_be_enabled();amount=page.locator('#amount').inner_text();page.locator('#plus').click();expect(page.locator('#buy')).to_be_enabled();assert page.locator('#amount').inner_text()!=amount;checks.append('Quantity changes live calculations and server risk gate')
   before=float(page.locator('#stop').input_value());y=page.locator('.terminal').evaluate('e=>e.__runtime.candles.priceToCoordinate(+e.__runtime.inputs.stop)');box=page.locator('#chart').bounding_box();page.mouse.move(box['x']+box['width']*.65,box['y']+y);page.mouse.down();page.mouse.move(box['x']+box['width']*.65,box['y']+y-10,steps=5);page.mouse.up();page.wait_for_timeout(1200);assert float(page.locator('#stop').input_value())!=before;checks.append('Draggable stop synchronizes calculator')
   expect(page.locator('#buy')).to_be_enabled();page.locator('#buy').click();expect(page.locator('#notice')).to_contain_text('Filled');expect(page.locator('#journalBody')).to_contain_text('BTCUSDT');checks.append('Manual paper BUY persists position')
   page.screenshot(path=str(OUT/'terminal-paper-1440.png'),full_page=True)
   page.locator('#quantity').fill('0.005');page.locator('#quantity').dispatch_event('input');expect(page.locator('#sell')).to_be_enabled();page.locator('#sell').click();page.wait_for_timeout(1400);assert page.locator('.terminal').evaluate('e=>+e.__runtime.data.state.positions.BTCUSDT.qty')<.01;checks.append('Partial virtual exit')
   page.locator('.st-key-qa_stale label').click();expect(page.locator('.terminal')).to_have_attribute('data-fresh','false');expect(page.locator('#buy')).to_be_disabled();expect(page.locator('#sell')).to_be_disabled();page.screenshot(path=str(OUT/'stale-data.png'),full_page=True);checks.append('Stale data blocks buy and sell')
   page.locator('.st-key-qa_stale label').click()
   page.locator('.st-key-crypto_symbol').click();page.get_by_role('option',name='ETHUSDT',exact=True).click();expect(page.locator('.terminal')).to_have_attribute('data-context','ETHUSDT:15');checks.append('Instrument switch')
   page.locator('.st-key-crypto_tf').click();page.get_by_role('option',name='1h',exact=True).click();expect(page.locator('.terminal')).to_have_attribute('data-context','ETHUSDT:60');checks.append('Timeframe switch')
   for width in (1280,1024):
    page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(600);assert page.locator('.terminal').evaluate('e=>e.scrollWidth<=e.clientWidth+2');page.screenshot(path=str(OUT/f'terminal-{width}.png'),full_page=True)
   checks.append('Laptop layouts 1440/1280/1024')
   page.locator('.st-key-workspace_mode').get_by_text('Invest',exact=True).click();page.get_by_text('Стоимость портфеля',exact=True).first.wait_for();checks.append('Return to existing Invest')
   browser.close();assert not errors,errors
 finally:
  proc.terminate();proc.wait(timeout=15);log.close();(OUT/'report.json').write_text(json.dumps({'checks':checks,'browser_errors':errors,'data':'Synthetic QA fixture, not Bybit live','count':len(checks)},ensure_ascii=False,indent=2))
print(json.dumps({'checks':checks,'errors':errors},ensure_ascii=False,indent=2))
