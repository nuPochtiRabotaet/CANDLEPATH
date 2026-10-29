"""Real Chromium integration checks with explicit synthetic fixtures only.

Run: python scripts/verify_v07_browser.py --chromium /path/to/chromium
Requires development-only playwright and an installed Chromium. No production
code contains a QA-data switch. Screenshots contain no personal portfolio data.
"""
from __future__ import annotations
import argparse,os,subprocess,tempfile,time,json,sys,statistics,socket
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--chromium',required=True);p.add_argument('--output',default=str(ROOT/'docs/v0.7/browser'));p.add_argument('--baseline');args=p.parse_args()
    from playwright.sync_api import sync_playwright,expect
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='moex-v07-browser-') as directory:
        env=os.environ.copy();env['MOEX_DATA_DIR']=directory
        if args.baseline:env['MOEX_QA_ROOT']=args.baseline
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        with open(output/'server.log','w') as log:
            server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'tests/ui_fixture.py'),'--server.port',str(port),'--server.fileWatcherType','none'],cwd=args.baseline or ROOT,env=env,stdout=log,stderr=log)
            try:
                for _ in range(150):
                    try:urllib.request.urlopen(url+'/_stcore/health',timeout=1);break
                    except OSError:time.sleep(.1)
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--disable-gpu-sandbox','--no-zygote'])
                    page=browser.new_page(viewport={'width':1440,'height':900});errors=[]
                    page.on('pageerror',lambda err:errors.append(str(err)))
                    page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' and 'BidiComponent Error' in msg.text else None)
                    page.goto(url)
                    page.get_by_text('Стоимость портфеля',exact=True).first.wait_for(timeout=30000)
                    page.wait_for_timeout(600)
                    if args.baseline:
                        page.get_by_text('Исследование',exact=True).first.click()
                        page.get_by_text('Инвестиционная лаборатория',exact=True).wait_for(timeout=30000);page.wait_for_timeout(1000)
                        page.screenshot(path=str(output/'v06-laboratory.png'))
                        browser.close();return
                    page.screenshot(path=str(output/'overview-1440.png'))
                    page.get_by_text('Портфель',exact=True).first.click();page.get_by_role('button',name='Оценить',exact=True).wait_for(timeout=30000);page.wait_for_timeout(300)
                    page.screenshot(path=str(output/'portfolio-1440.png'))
                    page.get_by_role('button',name='Оценить',exact=True).click();lab=page.locator('.lab');lab.wait_for(timeout=60000)
                    assert lab.evaluate('(e)=>e.__state.quantity')==0 and lab.evaluate('(e)=>e.__state.mode')=='Оценить'
                    page.get_by_text('Портфель',exact=True).first.click();page.get_by_role('button',name='Изменить позицию',exact=True).click()
                    page.get_by_role('button',name='Смоделировать покупку / продажу',exact=True).click();lab.wait_for(timeout=30000)
                    assert lab.evaluate('(e)=>e.__state.quantity')==10

                    expect(page.locator('#unitPrice')).to_contain_text('285,00')
                    sys.path.insert(0,str(ROOT));from moex_intelligence.portfolio import PortfolioStore
                    store=PortfolioStore(Path(directory)/'portfolio.sqlite3');original=store.bundle()
                    page.locator('#feeKnown').check();page.locator('#feePct').fill('0.05');expect(page.locator('#orderTotal')).to_contain_text('2\u00a0851,43')
                    page.wait_for_timeout(600)
                    assert lab.evaluate('(e)=>e.__lastResult.after.equity')==14208.57
                    page.locator('#quantity').fill('2');expect(page.locator('#validation')).to_contain_text('Недостаточно денег')
                    page.locator('#funding').select_option('topup');page.wait_for_timeout(600)
                    assert lab.evaluate('(e)=>e.__lastResult.qty')==40
                    page.locator('#shock').evaluate("e=>{e.value=-20;e.dispatchEvent(new Event('input',{bubbles:true}))}")
                    expect(page.locator('#stressPosition')).to_contain_text('9\u00a0120,00')
                    page.locator('[data-side="sell"]').click();page.locator('#quantity').fill('3');expect(page.locator('#validation')).to_contain_text('Нельзя продать')
                    page.locator('#unit').select_option('shares');page.locator('#quantity').fill('7');expect(page.locator('#validation')).to_contain_text('не кратны лоту')
                    page.locator('[data-action="reset"]').click();page.wait_for_timeout(500);assert lab.evaluate('(e)=>e.__state.shock')==0
                    page.locator('#feeKnown').check();page.locator('#feePct').fill('0.05');page.locator('#fees summary').click()
                    # Compare local arithmetic with unchanged Python core across independent inputs.
                    from moex_intelligence.laboratory import manual_asset,preview_trade
                    asset=manual_asset('SBER','equity',285,10,'QA fixture')
                    marks={s:{'price':v,'source':'QA fixture','as_of':asset['mark']['as_of']} for s,v in [('SBER',285),('SBMX',16),('OFZTEST',970)]}
                    events=[r['event'] for r in original['records']];timings=[]
                    for qty in [0,10,20,50,100,200]:
                        page.locator('#funding').select_option('topup')
                        sample=page.locator('#quantityRange').evaluate("(e,q)=>{const t=performance.now();e.value=q;e.dispatchEvent(new Event('input',{bubbles:true}));return new Promise(resolve=>requestAnimationFrame(()=>resolve(performance.now()-t)))}",qty);timings.append(sample)
                        result=lab.evaluate('(e)=>e.__lastResult');expected=preview_trade(events,marks,asset,qty,funding='topup',fee_pct=.05)
                        assert abs(result['total']-expected['order']['buy_total'])<1e-7,(qty,result,expected)
                        assert abs(result['after']['equity']-expected['after']['equity'])<1e-7
                    page.locator('[data-action="reset"]').click();page.wait_for_timeout(600)
                    page.locator('#feeKnown').check();page.locator('#feePct').fill('0.05');page.locator('#fees summary').click()
                    page.locator('#modelDetails summary').click();expect(page.locator('#modelStatus')).to_contain_text('2000',timeout=30000)
                    initial=page.locator('#modelCards').inner_text();page.locator('#shock').evaluate("e=>{e.value=40;e.dispatchEvent(new Event('input',{bubbles:true}))}");assert page.locator('#modelCards').inner_text()==initial
                    page.locator('[data-horizon="252"]').click();expect(page.locator('#modelStatus')).to_contain_text('252 торговых')
                    page.wait_for_timeout(600);assert (Path(directory)/'history-calls.txt').read_text()=='1'
                    page.locator('[data-action="save_model"]').click();expect(page.locator('#syncStatus')).to_contain_text('сохранено',timeout=10000)
                    page.locator('#modelDetails summary').click();page.locator('[data-mode="Оценить"]').click();page.locator('#profileKnown').check()
                    page.locator('#maxLoss').fill('10');page.locator('#shock').evaluate("e=>{e.value=-20;e.dispatchEvent(new Event('input',{bubbles:true}))}");expect(page.locator('#verdict')).to_contain_text('нарушает')
                    page.locator('[data-mode="Сценарии"]').click()
                    # Responsive widths, labels, no page-wide horizontal overflow.
                    layouts=[]
                    for width,height in [(1440,900),(1280,800),(1024,768),(390,844)]:
                        page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(350)
                        if width<600:
                            close=page.get_by_test_id('stSidebarCollapseButton')
                            if close.is_visible():close.click();page.wait_for_timeout(300)
                        metrics=lab.evaluate('(e)=>({width:e.getBoundingClientRect().width,scroll:e.scrollWidth,client:e.clientWidth,columns:getComputedStyle(e.querySelector(".workspace")).gridTemplateColumns})')
                        assert metrics['scroll']<=metrics['client']+2,metrics
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                        lab.evaluate('(e)=>e.scrollIntoView({block:"start"})');page.get_by_test_id('stMain').evaluate('(e)=>e.scrollTop-=70');page.wait_for_timeout(100)
                        page.screenshot(path=str(output/f'laboratory-{width}.png'))
                        page.locator('.stress').evaluate('(e)=>e.scrollIntoView({block:"start"})');page.get_by_test_id('stMain').evaluate('(e)=>e.scrollTop-=70');page.wait_for_timeout(100)
                        page.screenshot(path=str(output/f'stress-{width}.png'));layouts.append({'viewport_width':width,**metrics})
                    page.set_viewport_size({'width':1440,'height':900})
                    # Asset switch invalidates old scenario and model; bond uses clean+accrued.
                    page.get_by_label('Название, тикер или ISIN',exact=True).fill('OFZTEST');page.get_by_label('Название, тикер или ISIN',exact=True).press('Enter')
                    expect(page.locator('#assetName')).to_contain_text('OFZTEST',timeout=30000);expect(page.locator('#unitPrice')).to_contain_text('970,00')
                    assert lab.evaluate('(e)=>e.__state.quantity')==1 and lab.evaluate('(e)=>e.__state.shock')==0
                    page.locator('#feeKnown').check();page.locator('#feeMin').fill('10');expect(page.locator('#orderTotal')).to_contain_text('980,00')
                    page.locator('#shock').evaluate("e=>{e.value=-50;e.dispatchEvent(new Event('input',{bubbles:true}))}");expect(page.locator('#stressPrice')).to_contain_text('495,00')
                    page.locator('#modelDetails summary').click();expect(page.locator('#modelStatus')).to_contain_text('облигации',timeout=10000)
                    assert store.bundle()==original
                    assert not errors,errors
                    report={'browser':browser.version,'fixture':'explicit synthetic; not live MOEX','checks':'buy, sell, invalid lot, fees, topup, bond, scenario reset/switch, model separation/cache/save, constraints, responsive, unchanged journal','layouts':layouts,'input_to_animation_frame_ms':timings,'median_ms':statistics.median(timings),'max_ms':max(timings),'history_loads':1,'journal_unchanged':True,'js_errors':errors}
                    (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
                    browser.close()
            finally:
                server.terminate();server.wait(timeout=10)


if __name__=='__main__':main()
