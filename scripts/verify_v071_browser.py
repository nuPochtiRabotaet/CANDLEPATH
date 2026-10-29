"""v0.7.1 browser regression, responsive screenshots and measured interaction latency.

Uses only tests/ui_fixture.py + an isolated temporary directory. No user records.
"""
from __future__ import annotations
import argparse,json,os,platform,socket,statistics,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect,TimeoutError as BrowserTimeout

ROOT=Path(__file__).resolve().parents[1]
SIZES=[(1440,900),(1280,800),(1024,768),(390,844)]


def percentile95(v):return sorted(v)[max(0,int(.95*(len(v)-1)))]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chromium',required=True);parser.add_argument('--output',default=str(ROOT/'docs/v0.7.1/browser'));parser.add_argument('--baseline');args=parser.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True);checks=[];errors=[];layouts=[];numbers=[]
    with tempfile.TemporaryDirectory(prefix='moex-v071-browser-') as directory:
        env={**os.environ,'MOEX_DATA_DIR':directory}
        if args.baseline:env['MOEX_QA_ROOT']=str(Path(args.baseline).resolve())
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}';log=open(out/'server.log','w')
        process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'tests/ui_fixture.py'),'--server.port',str(port),'--server.fileWatcherType','none'],cwd=args.baseline or ROOT,env=env,stdout=log,stderr=log)
        try:
            for _ in range(150):
                try:urllib.request.urlopen(url+'/_stcore/health',timeout=1);break
                except OSError:time.sleep(.1)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--disable-gpu-sandbox','--no-zygote'])
                page=browser.new_page(viewport={'width':1440,'height':900});page.set_default_timeout(15000)
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('console',lambda m:errors.append(m.text) if m.type=='error' and 'BidiComponent Error' in m.text else None)
                page.goto(url);page.get_by_text('Стоимость портфеля',exact=True).first.wait_for(timeout=30000);page.wait_for_timeout(400)
                def nav(key):
                    page.wait_for_timeout(150)  # allow Streamlit's breakpoint state to follow a viewport resize
                    target=page.locator('.st-key-nav_'+key+' button')
                    if page.get_by_test_id('stSidebar').get_attribute('data-collapsed')=='true':
                        opener=page.get_by_test_id('stExpandSidebarButton')
                        try:opener.click(timeout=1500)
                        except BrowserTimeout:
                            # Resizing to desktop can expand it and remove the opener before the click.
                            if page.get_by_test_id('stSidebar').get_attribute('data-collapsed')!='false':raise
                        expect(page.get_by_test_id('stSidebar')).to_have_attribute('data-collapsed','false')
                    target.click();page.wait_for_timeout(250)
                    if not args.baseline:expect(page.locator('.st-key-workspace_header')).to_have_count(1)
                def settle():
                    expect(page.locator('.lab')).to_have_attribute('data-validation','confirmed',timeout=20000)
                def shock(n):page.locator('#shock').evaluate('(e,n)=>{e.value=n;e.dispatchEvent(new Event("input",{bubbles:true}))}',n)
                def ticker(symbol):
                    field=page.locator('.st-key-lab_picker_query input');field.fill(symbol);field.press('Enter')
                    expect(page.locator('#assetName')).to_contain_text(symbol,timeout=30000)
                if args.baseline:
                    for name,label in [('overview','Обзор'),('portfolio','Портфель'),('laboratory','Лаборатория')]:
                        page.get_by_text(label,exact=True).first.click();page.wait_for_timeout(600)
                        if name=='laboratory':page.get_by_text('Проверить решение',exact=True).wait_for(timeout=30000)
                        page.get_by_test_id('stMain').evaluate('e=>e.scrollTop=0');page.screenshot(path=str(out/(name+'-1440.png')))
                    browser.close();return
                sys.path.insert(0,str(ROOT));from moex_intelligence.portfolio import PortfolioStore
                store=PortfolioStore(Path(directory)/'portfolio.sqlite3');original=store.bundle()
                assert page.get_by_text('УЧЕБНЫЕ ДАННЫЕ · не текущие цены MOEX').count()
                assert '14\u00a0210,00 ₽' in page.locator('.financial-summary').inner_text()
                checks.append('overview: capital, source, incomplete history and actionable structure')
                nav('Portfolio');page.locator('.positions-view').wait_for()
                page.locator('.positions-view [data-sort="value"]').click()
                assert page.locator('.positions-view tbody tr').first.get_attribute('data-symbol')=='SBMX'
                page.locator('.positions-view [data-sort="value"]').click()
                assert page.locator('.positions-view tbody tr').first.get_attribute('data-symbol')=='SBER'
                row=page.locator('.positions-view [data-symbol="SBMX"]');row.click()
                expect(page.locator('.st-key-position_detail')).to_contain_text('SBMX')
                assert '16,00 ₽' in page.locator('.st-key-position_detail').inner_text()
                page.locator('.st-key-position_evaluate button').click();page.locator('.lab').wait_for(timeout=30000)
                expect(page.locator('#assetName')).to_contain_text('SBMX');assert page.locator('.lab').evaluate('e=>e.__state.quantity')==0
                assert '1\u00a0600,00 ₽' in page.locator('#orderTotal').inner_text()
                page.locator('[data-mode="Сценарии"]').click();settle();nav('Portfolio')
                expect(page.locator('.st-key-position_detail')).to_contain_text('SBMX')
                page.locator('.positions-view [data-symbol="SBER"]').click();expect(page.locator('.st-key-position_detail')).to_contain_text('SBER')
                page.locator('.st-key-position_actions').get_by_role('button',name='Изменить позицию',exact=True).click()
                page.get_by_role('button',name='Смоделировать покупку / продажу',exact=True).click();page.locator('.lab').wait_for()
                checks.append('selection and continuous navigation preserve symbol/quantity')
                page.locator('#feeKnown').check();page.locator('#feePct').fill('0.05');settle()
                expect(page.locator('#orderTotal')).to_contain_text('2\u00a0851,43')
                page.locator('[data-action="save_fee"]').click();expect(page.locator('#syncStatus')).to_contain_text('Тариф сохранён')
                page.locator('#quantity').fill('3');expect(page.locator('#calculationStatus')).to_contain_text('Предварительный')
                expect(page.locator('#validation')).to_contain_text('Недостаточно денег')
                page.locator('#funding').select_option('topup');settle()
                assert page.locator('.lab').evaluate('e=>e.__lastResult.qty')==50
                assert abs(page.locator('.lab').evaluate('e=>e.__lastResult.topup')-4554.28)<1e-6
                page.locator('[data-side="sell"]').click();settle();expect(page.locator('#validation')).to_contain_text('Нельзя продать')
                page.locator('#quantity').fill('1');settle()
                assert page.locator('.lab').evaluate('e=>e.__lastResult.qty')==10
                assert abs(page.locator('.lab').evaluate('e=>e.__lastResult.cash')-6848.57)<1e-6
                page.locator('[data-side="buy"]').click();page.locator('#quantity').fill('3');settle()
                checks.append('buy 1 -> 3 lots, partial sale and blocked oversell; commission and cash agree')
                page.locator('[data-mode="Оценить"]').click();page.locator('#profileKnown').check();page.locator('#maxLoss').fill('10');shock(-20);settle()
                expect(page.locator('#verdict')).to_contain_text('Обнаружен конфликт')
                shock(0);page.locator('#concentrationKnown').check();page.locator('#concentrationLimit').fill('40');settle();expect(page.locator('#verdict')).to_contain_text('конфликт')
                page.locator('#concentrationLimit').fill('100');settle();expect(page.locator('#verdict')).to_contain_text('конфликтов не выявлено')
                assert 'не рекомендация' in page.locator('#findingScope').inner_text()
                
                if not page.locator('#fees').evaluate('e=>e.open'):page.locator('#fees summary').click()
                page.locator('#feeKnown').uncheck();settle();expect(page.locator('#verdict')).to_contain_text('Недостаточно данных')
                page.get_by_role('button',name='Указать тариф',exact=True).click();assert page.locator('#feeKnown').evaluate('e=>e.getRootNode().activeElement===e')
                page.locator('#feeKnown').check();settle()
                checks.append('three distinct scenario findings, concentration/loss, working tariff action')
                page.locator('[data-action="pin"]').click();expect(page.locator('#pinnedLabel')).to_contain_text('A: 30')
                page.locator('[data-action="plus"]').click();expect(page.locator('#pinnedComparison')).to_contain_text('Сейчас')
                page.locator('[data-action="reset"]').click();settle()
                state=page.locator('.lab').evaluate('e=>e.__state');assert state['quantity']==10 and state['side']=='buy' and state['shock']==0 and state['horizon']==21 and state['funding']=='cash'
                assert not page.locator('#clearPin').is_visible()
                page.locator('#unit').select_option('shares');page.locator('#quantity').fill('7');settle();expect(page.locator('#validation')).to_contain_text('не кратны')
                assert page.locator('#quantityRange').is_disabled() and page.locator('#quantityRange').input_value()=='7'
                page.locator('#quantity').fill('-1');expect(page.locator('.lab')).to_have_attribute('data-validation','rejected');seq=page.locator('.lab').evaluate('e=>e.__state.seq');page.wait_for_timeout(700);assert page.locator('.lab').evaluate('e=>e.__state.seq')==seq
                page.locator('[data-action="reset"]').click();settle()
                page.locator('#funding').select_option('topup');settle()
                # Fifty sequential clicks in one burst must preserve the last number and eventual confirmation.
                page.locator('[data-action="plus"]').evaluate('e=>{for(let i=0;i<50;i++)e.click()}');settle()
                assert page.locator('.lab').evaluate('e=>e.__state.quantity')==510
                assert page.locator('#quantity').input_value()=='51' and page.locator('#quantityRange').input_value()=='510'
                assert page.locator('.lab').evaluate('e=>e.__lastResult.qty')==530
                checks.append('rapid input, zero/invalid lots, rejected-input stability, full reset, pinned A')
                # Honest input-to-next-animation-frame measurements; chart RAF runs before sample RAF.
                quantities=[];stresses=[]
                for i in range(35):
                    value=(i%20+1)*10
                    sample=page.locator('#quantityRange').evaluate('(e,q)=>{let t=performance.now();e.value=q;e.dispatchEvent(new Event("input",{bubbles:true}));return new Promise(r=>requestAnimationFrame(()=>r(performance.now()-t)))}',value)
                    if i>=5:quantities.append(sample)
                for i in range(35):
                    sample=page.locator('#shock').evaluate('(e,n)=>{let t=performance.now();e.value=n;e.dispatchEvent(new Event("input",{bubbles:true}));return new Promise(r=>requestAnimationFrame(()=>r(performance.now()-t)))}',i-20)
                    if i>=5:stresses.append(sample)
                settle();assert not (Path(directory)/'history-calls.txt').exists()
                page.locator('[data-action="reset"]').click();settle()
                page.locator('#modelDetails summary').click();page.locator('[data-action="plus"]').click()
                expect(page.locator('#modelStatus')).to_contain_text('2000',timeout=30000);settle()
                assert page.locator('.lab').evaluate('e=>e.__state.quantity')==20
                assert page.locator('.lab').evaluate('e=>e.__lastResult.qty') is None  # rejected trade: model remains on held position
                model_values=page.locator('#modelCards').inner_text();shock(40);assert page.locator('#modelCards').inner_text()==model_values
                page.locator('#funding').select_option('topup');settle();page.locator('[data-horizon="252"]').click();settle()
                assert (Path(directory)/'history-calls.txt').read_text()=='1'
                page.locator('[data-action="save_model"]').click();expect(page.locator('#syncStatus')).to_contain_text('сохранено',timeout=20000)
                checks.append('late model response never overwrites latest input; history cached once; stress separate')
                # Bridge to detailed research: same asset, amount and confirmed conditions, no permanent profile write.
                page.locator('[data-mode="Оценить"]').click();page.locator('#profileKnown').check();page.locator('#maxLoss').fill('12');page.locator('#months').fill('18');settle()
                if not page.locator('#fees').evaluate('e=>e.open'):page.locator('#fees summary').click()
                page.locator('#feeMin').fill('10');settle();page.locator('[data-action="deep_advisor"]').click()
                expect(page.locator('#syncStatus')).to_contain_text('минимальную комиссию')
                page.locator('#feeMin').fill('0');page.locator('#feePct').fill('5');settle();page.locator('[data-action="deep_advisor"]').click()
                expect(page.locator('#syncStatus')).to_contain_text('до 3%')
                page.locator('#feePct').fill('0.05');settle()
                page.locator('[data-action="deep_advisor"]').click();page.get_by_text('Подробная оценка вложения',exact=True).wait_for(timeout=30000)
                assert page.get_by_label('На сколько месяцев',exact=True).input_value()=='18'
                assert page.get_by_label('Хочу вложить, ₽',exact=True).input_value()=='5702.85'
                assert page.get_by_label('Допустимое снижение, %',exact=True).input_value()=='12.00'
                assert not page.get_by_label('Это мои условия — оценить соответствие профилю',exact=True).is_checked()
                checks.append('compatible detailed Advisor context without changing permanent profile')
                nav('Portfolio');expect(page.locator('.st-key-position_detail')).to_contain_text('SBER')
                # All four sections, all four viewports. Only fixture positions appear in screenshots.
                for width,height in SIZES:
                    for section in ['Overview','Portfolio','Laboratory','Research']:
                        page.set_viewport_size({'width':1440,'height':900});nav(section)
                        if section=='Research':
                            back=page.get_by_role('button',name='К карточке актива',exact=True)
                            if back.count():back.click();page.wait_for_timeout(300)
                        if section=='Laboratory':
                            page.locator('.lab').wait_for();page.locator('#quantity').fill('1');shock(-20);settle()
                            fees=page.locator('#fees');
                            if fees.evaluate('e=>e.open'):page.locator('#fees summary').click()
                            page.locator('[data-mode="Сценарии"]').click();settle()
                        page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(300)
                        if width==390:
                            close=page.get_by_test_id('stSidebarCollapseButton')
                            if close.is_visible():close.click();page.wait_for_timeout(150)
                            if section=='Overview':
                                page.get_by_role('button',name='Настройки',exact=True).click();page.get_by_text('Ваши настройки',exact=True).wait_for()
                                page.get_by_role('button',name='Настройки',exact=True).click();page.locator('.financial-summary').wait_for()
                                page.get_by_role('button',name='Обновить цены',exact=True).click();page.locator('.financial-summary').wait_for()
                                page.get_by_test_id('stExpandSidebarButton').click();page.get_by_role('button',name='Портфель',exact=True).wait_for()
                                page.get_by_test_id('stSidebarCollapseButton').click()
                        page.get_by_test_id('stMain').evaluate('e=>e.scrollTop=0');page.wait_for_timeout(150)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),(section,width)
                        measures=page.locator('.financial-value,.asset-price').evaluate_all('(nodes)=>nodes.map(e=>({text:e.textContent,width:e.clientWidth,scroll:e.scrollWidth}))')
                        assert all(m['scroll']<=m['width']+2 for m in measures),(section,width,measures)
                        if section=='Portfolio':
                            assert page.locator('.positions-view .cell-value').evaluate_all('ns=>ns.every(e=>e.scrollWidth<=e.clientWidth+2)')
                            if width==390:
                                assert page.locator('.positions-view [data-symbol="SBER"] .mobile-actions').is_visible()
                        page.screenshot(path=str(out/f'{section.lower()}-{width}.png'))
                        layouts.append({'section':section,'width':width,'height':height,'page_overflow':False,'numeric_clipping':False})
                        if section=='Laboratory':
                            page.locator('.stress').evaluate('e=>e.scrollIntoView({block:"start"})');page.get_by_test_id('stMain').evaluate('e=>e.scrollTop-=65');page.wait_for_timeout(100)
                            page.screenshot(path=str(out/f'stress-{width}.png'))
                page.set_viewport_size({'width':1440,'height':900});nav('Laboratory');ticker('OFZTEST')
                expect(page.locator('#unitPrice')).to_contain_text('970,00')
                fees=page.locator('#fees');
                if not fees.evaluate('e=>e.open'):page.locator('#fees summary').click()
                page.locator('#feeMin').fill('10');settle();expect(page.locator('#orderTotal')).to_contain_text('980,00');shock(-50);expect(page.locator('#stressPrice')).to_contain_text('495,00')
                page.locator('#modelDetails summary').click();expect(page.locator('#modelStatus')).to_contain_text('облигации',timeout=20000)
                ticker('PENNY');page.locator('#quantity').fill('50')
                if not page.locator('#fees').evaluate('e=>e.open'):page.locator('#fees summary').click()
                page.locator('#feePct').fill('1');page.locator('#feeMin').fill('0');settle();expect(page.locator('#orderTotal')).to_contain_text('14,65')
                checks.append('decimal fee boundary 0.29 × 50 × 1% -> 0.15 fee, same in JS and Python')
                ticker('OLDTEST');expect(page.locator('#provenance')).to_contain_text('01.10.2026');expect(page.locator('#provenance')).to_contain_text('Сохранённая')
                from moex_intelligence.lab_data import QuoteSnapshots
                old=QuoteSnapshots(Path(directory)/'market_snapshots').load('OLDTEST');assert old['mark']['as_of']=='2026-10-01' and old['observed_at']=='2026-10-01'
                checks.append('bond percent+nominal+accrued; original saved quote date under offline failure')
                ticker('NOHISTORY');page.locator('#modelDetails summary').click();expect(page.locator('#modelStatus')).to_contain_text('недостаточно истории',timeout=20000)
                page.locator('.st-key-lab_picker_query input').fill('NOQUOTE');page.locator('.st-key-lab_picker_query input').press('Enter');page.get_by_text('Задать цену вручную',exact=True).wait_for(timeout=20000)
                assert not page.locator('.lab').count()
                assert store.bundle()==original;checks.append('all sandbox interactions leave actual journal unchanged')
                # A write in another window invalidates the old sandbox revision; it cannot commit anything.
                ticker('SBER');settle()
                from moex_intelligence.data import market_today
                store.append_many([{'date':str(market_today()),'kind':'deposit','amount':17,'currency':'RUB'}],expected_revision=original['revision'])
                external=store.bundle();page.locator('[data-action="plus"]').click()
                page.get_by_text('Портфель изменился в другом окне.',exact=False).wait_for()
                assert store.bundle()==external
                page.get_by_role('button',name='Обновить снимок',exact=True).click();settle()
                assert store.bundle()==external
                checks.append('external journal revision invalidates sandbox, explicit snapshot refresh recovers')
                # Explicitly confirmed import is a separate write; repeat must remain idempotent.
                nav('Portfolio');page.get_by_role('tab',name='Импорт',exact=True).click();page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files({'name':'qa.csv','mimeType':'text/csv','buffer':f'date,kind,amount,currency\n{__import__('moex_intelligence.data',fromlist=['market_today']).market_today()},deposit,100,RUB\n'.encode()})
                page.get_by_role('button',name='Подготовить предпросмотр',exact=True).click()
                ack=page.get_by_label('Проверены все операции, валюты, единицы цены и денежный остаток',exact=True)
                ack.focus();ack.press('Space');expect(ack).to_be_checked()
                page.get_by_role('button',name='Сохранить импорт',exact=True).click()
                page.wait_for_timeout(500);after=store.bundle();assert len(after['records'])==len(external['records'])+1
                page.get_by_role('button',name='Подготовить предпросмотр',exact=True).click();expect(page.get_by_text('Новых операций нет:',exact=False)).to_be_visible();assert page.get_by_role('button',name='Сохранить импорт',exact=True).is_disabled();assert store.bundle()==after
                checks.append('explicit CSV import + repeat has no duplicate, empty save disabled')
                assert not errors,errors
                cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),platform.processor()) if Path('/proc/cpuinfo').exists() else platform.processor()
                report={'browser':browser.version,'platform':platform.platform(),'processor':platform.machine(),'cpu_model':cpu,'cpu_count':os.cpu_count(),'rendering':'headless Chromium, software SwiftShader; not physical Mac hardware','fixture':'controlled synthetic data only','checks':checks,'layouts':layouts,'js_errors':errors,'journal_unchanged_through_sandbox':True,'history_loads':1,
                        'performance':{'method':'input -> next animation frame; chart RAF runs before sample RAF; 5 warmups excluded, 30 samples each, no model open','quantity':{'median_ms':statistics.median(quantities),'p95_ms':percentile95(quantities),'samples_ms':quantities},'stress':{'median_ms':statistics.median(stresses),'p95_ms':percentile95(stresses),'samples_ms':stresses}}}
                (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['layouts','performance']},ensure_ascii=False,indent=2));print('quantity median/p95',statistics.median(quantities),percentile95(quantities),'stress median/p95',statistics.median(stresses),percentile95(stresses))
                browser.close()
        finally:process.terminate();process.wait(timeout=10);log.close()


if __name__=='__main__':main()
