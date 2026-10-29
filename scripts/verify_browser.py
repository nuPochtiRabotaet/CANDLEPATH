"""Optional real Chromium smoke for v0.6; requires Playwright and its browser.

This script is not part of the claimed current-environment verification.
Screenshots are opt-in with --screenshots and use an empty temporary account.
"""
import json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright


def main():
 root=Path(__file__).resolve().parents[1];out=root/'artifacts/browser';out.mkdir(parents=True,exist_ok=True)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 with tempfile.TemporaryDirectory() as data_dir,open(out/'server.log','w') as log:
  proc=subprocess.Popen([os.getenv('MOEX_APP_PYTHON',sys.executable),'-m','streamlit','run','app.py','--server.port',str(port),'--server.address','127.0.0.1'],cwd=root,env={**os.environ,'MOEX_DATA_DIR':data_dir},stdout=log,stderr=log)
  errors=[]
  try:
   for _ in range(100):
    try:
     with urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=.2) as response:
      if response.read()==b'ok':break
    except OSError:
     if proc.poll() is not None:raise RuntimeError('Streamlit exited')
     time.sleep(.1)
   else:raise TimeoutError('Startup timeout')
   with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1080})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
    page.get_by_role('heading',name='Мой капитал',exact=True).wait_for()
    side=page.get_by_test_id('stSidebar')
    side.get_by_text('Мой портфель',exact=True).click()
    page.get_by_role('heading',name='Мой портфель',exact=True).wait_for()
    page.get_by_role('tab',name='Операции',exact=True).click()
    page.get_by_role('button',name='Сохранить запись',exact=True).click()
    page.get_by_text('Операция добавлена. Портфель пересчитан.',exact=True).wait_for()
    side.get_by_text('Исследование',exact=True).click()
    page.get_by_role('heading',name='Инвестиционная лаборатория',exact=True).wait_for(timeout=30000)
    page.get_by_text('Финансовая цель',exact=True).click()
    page.get_by_label('Ежемесячное пополнение, ₽',exact=True).fill('10000')
    page.get_by_label('Ежемесячное пополнение, ₽',exact=True).press('Enter')
    page.locator('[data-testid="stPlotlyChart"] .main-svg').first.wait_for()
    if '--screenshots' in sys.argv:page.screenshot(path=str(out/'financial-goal.png'))
    side.get_by_text('История',exact=True).click()
    page.get_by_role('heading',name='История исследований',exact=True).wait_for()
    side.get_by_role('button',name='Настройки профиля и приложения',exact=True).click()
    page.get_by_role('heading',name='Ваши настройки',exact=True).wait_for()
    assert not page.locator('[data-testid="stException"]').count()
    assert not errors,errors
    browser.close()
   (out/'verification.json').write_text(json.dumps({'pages':4,'goal_interaction':'pass','deposit':'pass','page_errors':errors},ensure_ascii=False,indent=2))
   print('PASS Chromium: navigation, deposit, goal interaction, history, settings')
  finally:
   proc.terminate()
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()


if __name__=='__main__':main()
