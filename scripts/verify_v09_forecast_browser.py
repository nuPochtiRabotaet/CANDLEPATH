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
    forecast={'status':'EXPERIMENTAL','symbol':'BTCUSDT','timeframe':'15',
              'data_as_of':last['time']+step,'points':[
        dict(target_time=last['time']+step*(1+j),
             lower=str(last['close']-j*.4),median=str(last['close']),
             upper=str(last['close']+j*.4)) for j in (1,2,4,8)]}
    return dict(context='BTCUSDT:15',symbol='BTCUSDT',interval='15',
        mode='Market Data',fresh=True,status='Live',age=1,error='',version=1,
        readiness=dict(forecast_feed_ready=True,candle_data_fresh=True),
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
            # Causal timestamps must land at the CLOSE boundary, not one bar
            # before. Horizontal gaps 1/2/4/8 must also be proportional.
            geometry=page.locator('.terminal').evaluate("""e=>{
                const r=e.__runtime,closed=window._data.candles.at(-1),
                asOf=closed.time+900,steps=[0,1,2,4,8],
                times=steps.map(h=>asOf+h*900),
                line=r.forecastLine.data(),grid=JSON.parse(r.forecastGridKey||'[]'),
                x=times.map(t=>r.chart.timeScale().timeToCoordinate(t));
                return {times,positions:line.map(p=>p.time),grid:grid.map(p=>p.time),
                    values:line.map(p=>p.value),x,fan:r.forecastProfile};
            }""")
            assert geometry['positions']==geometry['times'],geometry
            assert geometry['grid']==[geometry['times'][0]+i*900 for i in range(1,9)],geometry
            assert len(geometry['fan'])==5
            assert [p['time'] for p in geometry['fan']]==geometry['positions']
            assert all(v is not None for v in geometry['x']),geometry
            spacing=[b-a for a,b in zip(geometry['x'],geometry['x'][1:])]
            assert all(abs(delta-spacing[0]*units)<.2 for delta,units in zip(spacing,(1,1,2,4))),geometry
            # All layers must reject a mismatched symbol, a stale candle stream,
            # a time-offset error or malformed interval quantiles together.
            for snippet in (
              "window._data.intelligence.forecast.symbol='ETHUSDT'",
              "window._data.intelligence.forecast.data_as_of+=900",
              "window._data.intelligence.forecast.points[0].lower='-1'",
              "window._data.intelligence.forecast.points[0].upper='NaN'",
              "window._data.intelligence.forecast.points[0].median='9999999'",
              "window._data.readiness.forecast_feed_ready=false",
            ):
                page.evaluate("""code=>{const backup=structuredClone(window._data);
                  new Function(code)();
                  window._invoke();
                  window._data=backup;}""",snippet)
                assert page.locator('.terminal').evaluate(
                    'e=>e.__runtime.forecastLine.data().length')==0,snippet
                assert page.locator('.terminal').evaluate(
                    'e=>e.__runtime.forecastGridKey')=='',snippet
                assert page.locator('.terminal').evaluate(
                    'e=>e.__runtime.forecastProfile') is None,snippet
                page.evaluate("() => window._invoke()")
                assert page.locator('.terminal').evaluate(
                    'e=>e.__runtime.forecastLine.data().length')==5,snippet
            # A current still-forming candle may share the anchor timestamp,
            # but it must not shift the future targets or enter the forecast.
            page.evaluate("""() => {const last=window._data.candles.at(-1);
                window._data.candles.push({time:last.time+900,open:100,high:101,
                    low:99,close:100,volume:3,closed:false});
                window._invoke();}""")
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.forecastLine.data().map(p=>p.time)')==geometry['positions']
            page.evaluate("""() => {window._data.candles.pop();window._invoke()}""")
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
            # Same-version live changes previously updated candle close but
            # left volume stale when the back-end version was unchanged.
            before=page.locator('.terminal').evaluate("""e=>({
                volume:e.__runtime.volume.data().at(-1).value,
                close:e.__runtime.candles.data().at(-1).close})""")
            page.evaluate("""() => {const bar=window._data.candles.at(-1);
                bar.volume+=9;bar.close+=.1;window._invoke()}""")
            after=page.locator('.terminal').evaluate("""e=>({
                volume:e.__runtime.volume.data().at(-1).value,
                close:e.__runtime.candles.data().at(-1).close})""")
            assert after['volume']==before['volume']+9,(before,after)
            assert abs(after['close']-before['close']-.1)<1e-6,(before,after)
            # Historical volume correction must force a full rebuild, not a
            # tail-only update; no old bar may survive as a ghost.
            page.evaluate("""() => {window._data.candles[20].volume=77;
                window._invoke()}""")
            value=page.locator('.terminal').evaluate(
                'e=>e.__runtime.volume.data()[20].value')
            assert value==77,value
            # Append a partial candle, then remove it. Both price and volume
            # must exactly match the incoming snapshot without stale tail bars.
            page.evaluate("""() => {const tail=window._data.candles.at(-1);
                window._data.candles.push({time:tail.time+900,open:100,
                    high:101,low:99,close:100,volume:3,closed:false});
                window._invoke()}""")
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.volume.data().length')==121
            page.evaluate("""() => {window._data.candles.pop();
                window._invoke()}""")
            assert page.locator('.terminal').evaluate(
                'e=>e.__runtime.volume.data().length')==120
            # Same timestamp can carry several signals: all hover details
            # remain indexed and last-on-click order remains unchanged.
            page.evaluate("""() => {
                const t=window._data.candles[60].time;
                window._data.signals=[{timestamp:t,type:'BUY',strategy:'One'},
                    {timestamp:t,type:'EXIT',strategy:'Two'}];
                window._invoke()}""")
            indexed=page.locator('.terminal').evaluate("""e=>{
                const ts=window._data.candles[60].time;
                return e.__runtime.signalsByTime.get(ts).map(s=>s.strategy)}""")
            assert indexed==['One','Two'],indexed
            # Technical EXIT is not a filled SELL, even without a position.
            markers=page.locator('.terminal').evaluate("""e=>
                e.__runtime.markers.markers().map(m=>({time:m.time,text:m.text}))""")
            assert markers==[{'time':window_time,'text':kind} for kind in ('BUY','EXIT')
                             for window_time in [page.evaluate('window._data.candles[60].time')]],markers
            page.evaluate("""() => {
                const e=document.querySelector('.terminal'),r=e.__runtime;
                const c=window._data.candles[60];
                r.chart.setCrosshairPosition(c.close,c.time,r.candles);
            }""")
            tooltip=page.locator('#signalTooltip').inner_text()
            assert 'BUY · One' in tooltip and 'EXIT · Two' in tooltip,tooltip
            assert 'SELL / EXIT' not in tooltip
            assert 'не исполненная сделка' in tooltip
            # Click the actual chart marker; selecting a signal may only
            # describe it, never post a Paper SELL or create a position.
            at=page.locator('.terminal').evaluate("""e=>{
                const r=e.__runtime,c=window._data.candles[60],
                  rect=e.querySelector('#chart').getBoundingClientRect();
                return {x:rect.left+r.chart.timeScale().timeToCoordinate(c.time),
                        y:rect.top+r.candles.priceToCoordinate(c.close)};
            }""")
            assert isinstance(at['x'],(float,int)) and isinstance(at['y'],(float,int)),at
            page.mouse.click(at['x'],at['y'])
            assert 'EXIT · технический сигнал' in page.locator('#signal').inner_text()
            assert 'не является исполненной сделкой' in page.locator('#reasons').inner_text()
            assert page.evaluate("""() => Object.keys(window._data.state.positions).length===0
                && window._data.orders.length===0""")
            # Only the recorded Paper order journal retains SELL semantics.
            page.evaluate("""() => {
                const e=document.querySelector('.terminal');
                e.__runtime.tab='orders';
                window._data.orders=[{time:window._data.candles[60].time,
                    symbol:'BTCUSDT',side:'SELL',quantity:'0.1',
                    fill:100,fee:0.01,status:'Filled'}];
                window._invoke();
            }""")
            assert 'SELL' in page.locator('#journalBody').inner_text()
            assert not errors,errors
            return 'PASS: forecast geometry, same-version volume, historical correction, append/truncate, indexed signals'
        finally:
            browser.close()


if __name__=='__main__':
    print(verify())
