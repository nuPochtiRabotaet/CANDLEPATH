"""Real browser, explicitly synthetic market fixture. No live API claims."""
import json,os,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/rc3/browser';OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[]
def wait_data(page,predicate):
 for _ in range(100):
  if page.locator('.terminal').evaluate('(e)=>'+predicate):return
  page.wait_for_timeout(100)
 raise AssertionError('Server component state did not settle: '+predicate)

with tempfile.TemporaryDirectory(prefix='moex-v082-ui-') as directory:
 env={**os.environ,'MOEX_DATA_DIR':directory}
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 log=open(OUT/'server.log','w');proc=subprocess.Popen([sys.executable,'-m','streamlit','run','tests/crypto_ui_fixture.py','--server.port',str(port),'--server.fileWatcherType','none'],cwd=ROOT,env=env,stdout=log,stderr=log)
 try:
  for _ in range(150):
   try:urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1);break
   except OSError:time.sleep(.1)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=sys.argv[1],headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--disable-gpu-sandbox','--no-zygote'])
   page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(20000);page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{port}');page.get_by_text('Стоимость портфеля',exact=True).first.wait_for(timeout=30000);checks.append('Invest overview')
   page.locator('.st-key-workspace_mode').get_by_text('Trade',exact=True).click();page.locator('.terminal').wait_for();expect(page.locator('#price')).not_to_have_text('—')
   assert not page.get_by_test_id('stSidebar').is_visible();checks.append('Trade navigation collapsed')
   assert page.locator('#chart canvas').count()>=4
   page.locator('.terminal').evaluate('e=>e.__qaChart=e.__runtime.chart');page.wait_for_timeout(2000)
   assert page.locator('.terminal').evaluate('e=>e.__qaChart===e.__runtime.chart');checks.append('Chart instance preserved')
   page.locator('.st-key-qa_potential label').click();expect(page.locator('.terminal')).to_have_attribute('data-signal-state','POTENTIAL');page.locator('.st-key-qa_potential label').click();expect(page.locator('.terminal')).not_to_have_attribute('data-signal-state','POTENTIAL');checks.append('Intracandle signal lifecycle')
   page.get_by_role('button',name='Полный',exact=True).click();assert page.locator('.terminal').evaluate('e=>e.__runtime.markers.markers().length')>0
   before=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange()')
   page.locator('#ema').uncheck();page.wait_for_timeout(500);after=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange()');assert abs(before['from']-after['from'])<.01;checks.append('Layer toggle preserves viewport')
   box=page.locator('#chart').bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+180);page.mouse.wheel(0,-250);page.wait_for_timeout(400)
   after=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange()');assert after['to']-after['from']<before['to']-before['from'];checks.append('Zoom')
   scroll_before=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange().from')
   box=page.locator('#chart').bounding_box();page.mouse.move(box['x']+box['width']*.5,box['y']+160);page.mouse.down();page.mouse.move(box['x']+box['width']*.5+100,box['y']+160,steps=6);page.mouse.up();page.wait_for_timeout(300)
   scroll_after=page.locator('.terminal').evaluate('e=>e.__runtime.chart.timeScale().getVisibleLogicalRange().from');assert abs(scroll_before-scroll_after)>1;checks.append('Horizontal chart scroll')
   page.locator('#markers').uncheck();assert page.locator('.terminal').evaluate('e=>e.__runtime.markers.markers().length')==0
   page.locator('#markers').check();assert page.locator('.terminal').evaluate('e=>e.__runtime.markers.markers().length')>0;checks.append('BUY EXIT toggle removes and restores actual markers')
   page.locator('#glow').uncheck();page.locator('.layers summary').click()
   page.locator('#opacity').evaluate('e=>{e.value=40;e.dispatchEvent(new Event("input",{bubbles:true}))}')
   wait_data(page,'e.__runtime.data.overlay_settings.intensity===40 && !e.__runtime.data.overlay_settings.glow')
   expect(page.locator('#markers')).to_be_checked();checks.append('Glow and intensity saved independently')
   page.reload();page.get_by_text('Стоимость портфеля',exact=True).first.wait_for(timeout=30000)
   page.locator('.st-key-workspace_mode').get_by_text('Trade',exact=True).click();page.locator('.terminal').wait_for()
   expect(page.locator('#glow')).not_to_be_checked();assert page.locator('#opacity').input_value()=='40';checks.append('Overlay settings survive new browser session')
   for symbol in ['ETHUSDT','SOLUSDT','BTCUSDT']:
    page.locator('.st-key-crypto_symbol').get_by_role('combobox').click();page.get_by_role('option',name=symbol,exact=True).click()
    expect(page.locator('.terminal')).to_have_attribute('data-context',symbol+':15')
    expect(page.locator('#glow')).not_to_be_checked();assert page.locator('#opacity').input_value()=='40'
   for label,interval in [('1m','1'),('5m','5'),('30m','30'),('1h','60'),('4h','240'),('1D','D'),('15m','15')]:
    page.locator('.st-key-crypto_tf').get_by_role('combobox').click();page.get_by_role('option',name=label,exact=True).click()
    expect(page.locator('.terminal')).to_have_attribute('data-context','BTCUSDT:'+interval)
    expect(page.locator('#glow')).not_to_be_checked();assert page.locator('#opacity').input_value()=='40'
   checks.append('BTC ETH SOL and seven timeframes retain overlay preferences')
   page.locator('.layers summary').click();page.locator('#resetOverlay').click()
   wait_data(page,'e.__runtime.data.overlay_settings.intensity===85')
   expect(page.locator('#glow')).to_be_checked();page.locator('.layers summary').click();checks.append('Overlay defaults reset')
   page.locator('#toggleAssistant').click();expect(page.locator('.assistant')).not_to_be_visible()
   assert page.locator('#chart').bounding_box()['width']>1200
   page.locator('#toggleAssistant').click();expect(page.locator('.assistant')).to_be_visible();checks.append('Assistant collapse preserves chart')
   page.locator('.st-key-crypto_mode').get_by_text('Paper Trading',exact=True).click();expect(page.locator('#buy')).to_be_enabled()
   assert page.locator('#budget').input_value()=='25';page.locator('#buy').click();expect(page.locator('#confirmDialog')).to_be_visible();expect(page.locator('#confirmOrder')).to_be_disabled()
   assert page.locator('.terminal').evaluate('e=>Object.keys(e.__runtime.data.state.positions).length')==0
   page.screenshot(path=str(OUT/'manual-buy-confirmation.png'),full_page=True);checks.append('25 USDT preview without execution; consent required')
   expect(page.locator('#entryQuality')).not_to_have_text('—');expect(page.locator('#attention')).to_contain_text('No Trade')
   page.keyboard.press('Escape');expect(page.locator('#confirmDialog')).not_to_be_visible();assert page.locator('.terminal').evaluate('e=>e.__runtime.data.orders.length')==0
   page.locator('#buy').click();expect(page.locator('#confirmDialog')).to_be_visible();checks.append('Escape cancellation waits for server')
   page.locator('#cancelOrder').click();expect(page.locator('#confirmDialog')).not_to_be_visible()
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.orders.length')==0;checks.append('Cancel does not create an order')
   page.locator('#budgetMode').select_option('total');expect(page.locator('#buy')).to_be_enabled();page.locator('#buy').click();expect(page.locator('#confirmDialog')).to_be_visible()
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.pending.request.max_spend')=='25'
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.pending.estimate.total')<=25
   page.locator('#cancelOrder').click();expect(page.locator('#confirmDialog')).not_to_be_visible();checks.append('All-inclusive budget in server preview')
   # Buy enough for meaningful partial exit; quantity input is exact.
   page.locator('#byQuantity').click();page.locator('#quantity').fill('0.01');page.locator('#quantity').dispatch_event('input');expect(page.locator('#buy')).to_be_enabled()
   page.get_by_text('Запись причины входа',exact=True).click();page.locator('#tradeNotes').fill('Browser QA manual decision')
   page.locator('#buy').click();expect(page.locator('#confirmDialog')).to_be_visible();page.locator('#riskConsent').check();page.locator('#confirmOrder').click()
   expect(page.locator('#confirmDialog')).not_to_be_visible();expect(page.locator('#notice')).to_contain_text('Filled');checks.append('Confirmed local BUY')
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.trade_metadata.notes')=='Browser QA manual decision'
   checks.append('Trade note persisted in immutable fill provenance')
   page.locator('#quantity').fill('0.005');page.locator('#quantity').dispatch_event('input');expect(page.locator('#sell')).to_be_enabled();page.locator('#sell').click();expect(page.locator('#confirmTitle')).to_contain_text('продажи');page.locator('#riskConsent').check();page.locator('#confirmOrder').click();expect(page.locator('#confirmDialog')).not_to_be_visible()
   page.wait_for_timeout(1100);assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.qty')=='0.005';checks.append('Confirmed partial SELL')
   page.locator('#fit').click();before=float(page.locator('#stop').input_value());persisted=page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.stop')
   y=page.locator('.terminal').evaluate('e=>e.__runtime.candles.priceToCoordinate(+e.__runtime.inputs.stop)');box=page.locator('#chart').bounding_box()
   page.mouse.move(box['x']+box['width']*.65,box['y']+y);page.mouse.down();page.mouse.move(box['x']+box['width']*.65,box['y']+y-10,steps=5);page.mouse.up();page.wait_for_timeout(1000)
   assert float(page.locator('#stop').input_value())!=before
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.stop')==persisted;checks.append('Drag changes draft only, not active protection')
   expect(page.locator('#applyProtection')).to_be_enabled();page.locator('#applyProtection').click();expect(page.locator('#protectionDialog')).to_be_visible()
   expect(page.locator('#confirmProtection')).to_be_disabled()
   page.screenshot(path=str(OUT/'stop-target-confirmation.png'),full_page=True)
   page.locator('#cancelProtection').click();expect(page.locator('#protectionDialog')).not_to_be_visible()
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.stop')==persisted
   checks.append('Protection cancel preserves active levels')
   page.locator('#applyProtection').click();expect(page.locator('#protectionDialog')).to_be_visible()
   expected_stop=page.locator('.terminal').evaluate('e=>e.__runtime.data.pending.request.stop')
   page.locator('#protectionConsent').check();page.locator('#confirmProtection').click();expect(page.locator('#protectionDialog')).not_to_be_visible()
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.stop')==expected_stop
   checks.append('Protection Preview Confirm commits active Stop/Target')

   page.get_by_text('Security Center Preview · данные и защита',exact=True).click();page.get_by_text('Security Center Preview · данные и защита',exact=True).scroll_into_view_if_needed();page.screenshot(path=str(OUT/'security-center.png'),full_page=True)
   page.get_by_text('Security Center Preview · данные и защита',exact=True).click()
   page.locator('.assistant').evaluate('e=>e.scrollTop=0')
   for width in (1024,1280,1440,1920):
    page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(400)
    assert page.locator('.terminal').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
    assert page.locator('#chart').bounding_box()['width']>width*.5
    page.get_by_test_id('stMain').evaluate('e=>e.scrollTop=0');page.screenshot(path=str(OUT/f'terminal-{width}.png'),full_page=True)
   checks.append('Four laptop/desktop widths: chart >50%, no horizontal overflow')
   page.locator('.st-key-qa_stale label').click();expect(page.locator('#sell')).to_be_disabled();expect(page.locator('#buy')).to_be_disabled();checks.append('Stale market blocks actions')
   page.locator('.st-key-qa_stale label').click();page.locator('#closeAll').click();expect(page.locator('#confirmDialog')).to_be_visible();page.locator('#riskConsent').check();page.locator('#confirmOrder').click();expect(page.locator('#confirmDialog')).not_to_be_visible();page.wait_for_timeout(1100)
   assert page.locator('.terminal').evaluate('e=>Object.keys(e.__runtime.data.state.positions).length')==0;checks.append('Full close uses confirmation')
   page.get_by_text('Paper · комиссии и Quality Policy',exact=True).click()
   page.get_by_label('Taker % · Market',exact=True).fill('0.2')
   page.locator('.st-key-cost_currency').get_by_text('Актив (base)',exact=True).click()
   expect(page.locator('.st-key-cost_currency').get_by_role('radio',name='Актив (base)',exact=True)).to_be_checked()
   page.screenshot(path=str(OUT/'cost-settings.png'),full_page=True)
   page.get_by_role('button',name='Сохранить предположения Paper',exact=True).click()
   page.locator('#byAmount').click();page.locator('#budget').fill('25');page.locator('#budget').dispatch_event('input');expect(page.locator('#buy')).to_be_enabled()
   page.locator('#buy').click();expect(page.locator('#confirmDialog')).to_be_visible()
   pending=page.locator('.terminal').evaluate('e=>e.__runtime.data.pending')
   assert pending['estimate']['fill']['fee_currency']=='base',pending['estimate']['cost_model']
   assert float(pending['estimate']['fill']['net_base'])<float(pending['request']['quantity'])
   page.screenshot(path=str(OUT/'base-fee-preview.png'),full_page=True)
   page.locator('#riskConsent').check();page.locator('#confirmOrder').click();expect(page.locator('#confirmDialog')).not_to_be_visible();page.wait_for_timeout(1100)
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.qty')==pending['estimate']['fill']['net_base'];checks.append('Custom base fee UI agrees with ledger net quantity')
   allocation=page.locator('.terminal').evaluate('e=>e.__runtime.data.inventory.BTCUSDT')
   assert float(allocation['non_sellable_residue'])>0
   page.locator('#closeAll').click();expect(page.locator('#confirmDialog')).to_be_visible()
   expected_residue=page.locator('.terminal').evaluate('e=>e.__runtime.data.pending.estimate.remaining_quantity')
   assert float(expected_residue)>0
   page.screenshot(path=str(OUT/'residue-sale-preview.png'),full_page=True)
   page.locator('#riskConsent').check();page.locator('#confirmOrder').click();expect(page.locator('#confirmDialog')).not_to_be_visible()
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.positions.BTCUSDT.qty')==expected_residue
   checks.append('Sell available preserves net residue and basis')
   cash_before=page.locator('.terminal').evaluate('e=>e.__runtime.data.state.cash')
   page.get_by_text('Полное закрытие / старые остатки',exact=True).click()
   page.get_by_text('Списать весь остаток в убыток без возврата денег',exact=True).click()
   page.get_by_role('button',name='Учётное списание · не продажа',exact=True).click()
   page.wait_for_timeout(1200)
   assert page.locator('.terminal').evaluate('e=>Object.keys(e.__runtime.data.state.positions).length')==0
   assert page.locator('.terminal').evaluate('e=>e.__runtime.data.state.cash')==cash_before
   checks.append('Explicit residue writeoff has zero cash proceeds')

   page.get_by_text('Trading Performance · полный журнал',exact=True).click()
   page.get_by_text('Показать аналитику журнала',exact=True).click()
   page.get_by_text('Закрытые позиции',exact=True).wait_for()
   assert not page.get_by_test_id('stException').count()
   page.get_by_text('Trading Performance · полный журнал',exact=True).scroll_into_view_if_needed()
   page.screenshot(path=str(OUT/'performance.png'),full_page=True)
   page.get_by_test_id('stPlotlyChart').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'equity-curve.png'),full_page=True);checks.append('Full-ledger performance and equity render')
   page.locator('.st-key-performance_period').get_by_text('7 дней',exact=True).click()
   assert not page.get_by_test_id('stException').count();checks.append('Performance UTC period filter')
   page.get_by_role('button',name='← Invest',exact=True).click();page.get_by_text('Стоимость портфеля',exact=True).first.wait_for();page.screenshot(path=str(OUT/'invest.png'),full_page=True);checks.append('Return to preserved Invest')
   assert not errors,errors
   browser.close()
 finally:
  proc.terminate();proc.wait(timeout=15);log.close();(OUT/'report.json').write_text(json.dumps({'checks':checks,'browser_errors':errors,'data':'Synthetic QA; not Bybit live','count':len(checks)},ensure_ascii=False,indent=2))
print(json.dumps({'checks':checks,'errors':errors},ensure_ascii=False,indent=2))
