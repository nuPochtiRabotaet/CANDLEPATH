"""Standalone real-Chromium regression for Forecast Overlay v0.9.

Requires Playwright and /usr/bin/chromium. Uses SYNTHETIC local candles only.
Run: python scripts/verify_v09_forecast_browser.py
Not a Bybit, Streamlit, macOS/Safari or financial-profitability test.
"""
import json
import os
import shutil
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
COMP=ROOT/'moex_intelligence'/'components'


def fixture():
    step=900
    latest=int(time.time()//step)*step-step
    candles=[]
    for i in range(120):
        price=100+i*.1
        candles.append(dict(time=latest-(119-i)*step,open=price,high=price+.5,
                            low=price-.4,close=price+.2,volume=10,closed=True))
    last=candles[-1]
    forecast={'status':'EXPERIMENTAL','points':[
        dict(target_time=last['time']+step*(1+j),
             lower=str(last['close']-j*.4),median=str(last['close']),
             upper=str(last['close']+j*.4)) for j in (1,2,4,8)]}
    return dict(context='BTCUSDT:15',symbol='BTCUSDT',interval='15',
        mode='Market Data',fresh=True,status='Live',age=1,error='',version=1,
        candles=candles,quote=dict(price=last['close'],bid=last['close']-.01,
        ask=last['close']+.01,change=1,ts=latest+step),
        rules=dict(step='0.00001',tick='0.01',minimum='5'),
        analysis=dict(regime='Bullish',overlay=[]),intelligence=dict(forecast=forecast),
        overlay_settings=dict(version=1,ribbon=True,glow=True,markers=True,
            ema=True,st=False,volume=True,entry=True,sl=True,tp=True,
            intensity=85,width=1,line_opacity=85,
            fast_color='#31f3a2',slow_color='#e2c36f'),
        signals=[],lifecycle=dict(active=dict(state='NO_SIGNAL',reason='none'),
            notifications=[],records=[]),protection=dict(message='test'),
        state=dict(positions={}),orders=[],journal=[],events=[],
        account=dict(equity='10000',cash='10000',unrealized='0',realized='0',
            risk='0',drawdown=0,missing_quotes=[],liquidation_equity='10000'),
        inputs=dict(seq=0,quantity='0.001',stop=last['close']-1,
            target=last['close']+2,risk_pct=.75,budget='25',input_mode='amount'),
        quality_assessment=dict(quality='Wait',attention='Wait',reasons=[]),
        preview=None,notice='',inventory={},protection_preview=None,
        cost_model={},pending=None,quality={})


def verify():
    html=(COMP/'trade.html').read_text()
    css=(COMP/'trade.css').read_text()
    vendor=(COMP/'vendor/lightweight-charts.js').read_text()
    js=(COMP/'trade.js').read_text().replace('export default function(component){',
                                               'function render(component){')
    assert 'export default function(component)' not in js
    script=(vendor+'\n'+js+'\nwindow._render=render;window._data='+
        json.dumps(fixture())+';window._invoke=()=>render({data:window._data,'+
        'parentElement:document,setStateValue(){},setTriggerValue(){}});window._invoke();')
    errors=[]
    with sync_playwright() as pw:
        binary=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if binary: options['executable_path']=binary
        browser=pw.chromium.launch(**options)
        try:
            page=browser.new_page(viewport=dict(width=1400,height=900))
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.set_content('<html><head><style>'+css+'</style></head><body>'+html+'</body></html>')
            page.add_script_tag(content=script)
            page.wait_for_timeout(500)
            state=page.locator('.terminal').evaluate('''e=>({chart:!!e.__runtime.chart,
                line:e.__runtime.forecastLine.data().length,
                canvases:e.querySelectorAll('#chart canvas').length})''')
            assert state['chart'] and state['canvases']>=4 and state['line']==5,state
            assert not errors,errors
            page.locator('#forecastOverlay').uncheck()
            assert not page.locator('.terminal').evaluate(
                'e=>e.__runtime.forecastLine.options().visible')
            page.locator('#forecastOverlay').check()
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.forecastLine.options().visible')
            page.evaluate("""() => {window._savedForecast=window._data.intelligence.forecast;window._savedCandles=window._data.candles;window._data.intelligence.forecast={status:'UNAVAILABLE'};window._invoke()}""")
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.forecastLine.data().length')==0
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.candles.data().length')==120
            # Retained quote with lost candle feed formerly caused timeToCoordinate(undefined).
            page.evaluate("""() => {window._data.candles=[];window._data.version=2;window._invoke()}""")
            page.wait_for_timeout(250)
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.forecastLine.data().length')==0
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.candles.data().length')==0
            # Recover with the same version, as may happen with a reused Streamlit
            # snapshot. The volume/EMA engine must be reinitialized after clearing.
            page.evaluate("""() => {window._data.candles=window._savedCandles;
                 window._data.intelligence.forecast=window._savedForecast;
                 window._invoke()}""")
            page.wait_for_timeout(250)
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.forecastLine.data().length')==5
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.volume.data().length')==120
            assert not errors,errors
            return 'PASS: render, toggle, unavailable, empty feed, same-version recovery, JS errors'
        finally:
            browser.close()


if __name__=='__main__':
    print(verify())
