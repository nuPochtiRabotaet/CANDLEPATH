"""Actual production app + actual Bybit endpoints. No market fixture."""
import json,os,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/v0.8/production';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='moex-v08-live-') as directory:
 env={**os.environ,'MOEX_DATA_DIR':directory}
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 log=open(OUT/'server.log','w');proc=subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.port',str(port),'--server.fileWatcherType','none'],cwd=ROOT,env=env,stdout=log,stderr=log)
 try:
  for _ in range(150):
   try:urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1);break
   except OSError:time.sleep(.1)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=sys.argv[1],headless=True,args=['--no-sandbox','--disable-dev-shm-usage']);page=browser.new_page(viewport={'width':1440,'height':1100},locale='ru-RU');page.set_default_timeout(30000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{port}');page.locator('.st-key-workspace_mode').get_by_text('Trade',exact=True).click();page.locator('.terminal').wait_for();page.wait_for_function("document.querySelector('.terminal')?.__runtime?.data.error || document.querySelector('.terminal')?.__runtime?.data.fresh",timeout=45000)
   data=page.locator('.terminal').evaluate('e=>({status:e.__runtime.data.status,fresh:e.__runtime.data.fresh,error:e.__runtime.data.error,candle_count:e.__runtime.data.candles.length,source:"production Bybit connector"})')
   if not data['fresh']:expect(page.locator('#buy')).to_be_disabled();expect(page.locator('#sell')).to_be_disabled()
   page.screenshot(path=str(OUT/'bybit-connection.png'),full_page=True);assert not errors,errors;data['browser_errors']=errors;(OUT/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));print(json.dumps(data,ensure_ascii=False,indent=2));browser.close()
 finally:proc.terminate();proc.wait(timeout=15);log.close()
