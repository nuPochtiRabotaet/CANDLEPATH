// Lightweight Charts 5.2.1 is vendored above. No exchange credentials enter this component.
const LC=LightweightCharts;

// ForecastPoint.target_time is an epoch-second candle CLOSE boundary, whereas
// actual CandlestickSeries bars are plotted at their OPEN. Converting the
// forecast target to an OPEN incorrectly shifts the outcome one candle early.
// This single pure projection contract feeds BOTH the median and the fan.
function forecastProjection(data){
 const fc=data?.intelligence?.forecast;
 const step=data?.interval==='D'?86400:Number(data?.interval)*60;
 const candles=data?.candles;
 if(fc?.status!=='EXPERIMENTAL'||!Array.isArray(fc.points)||fc.points.length<1||
    fc.points.length>32||!Array.isArray(candles)||!candles.length||
    fc.symbol!==data.symbol||String(fc.timeframe)!==String(data.interval)||
    data.readiness?.forecast_feed_ready!==true||data.readiness?.candle_data_fresh!==true||
    !Number.isSafeInteger(step)||step<=0)return null;
 let anchor=null;
 for(let i=candles.length-1;i>=0;i--){
  if(candles[i].closed===true){anchor=candles[i];break;}
 }
 if(!anchor||!Number.isSafeInteger(anchor.time))return null;
 const observedTime=anchor.time+step,observedClose=Number(anchor.close);
 if(!Number.isSafeInteger(observedTime)||Number(fc.data_as_of)!==observedTime||
    !Number.isFinite(observedClose)||observedClose<=0)return null;
 const numeric=value=>(typeof value==='number'||(typeof value==='string'&&value.trim()!==''))
   ?Number(value):NaN;
 const profile=[{time:observedTime,lower:observedClose,median:observedClose,upper:observedClose}];
 let prev=observedTime;
 for(const point of fc.points){
  const time=point?.target_time,lower=numeric(point?.lower),
        median=numeric(point?.median),upper=numeric(point?.upper);
  if(!Number.isSafeInteger(time)||time<=prev||time%step!==0||
     (time-observedTime)/step>64||!Number.isFinite(lower)||
     !Number.isFinite(median)||!Number.isFinite(upper)||
     lower<=0||lower>median||median>upper)return null;
  profile.push({time,lower,median,upper});
  prev=time;
 }
 // Whitespace time points keep +1/+2/+4/+8 at proportional positions on
 // Lightweight Charts' ordinal time scale (no invented price observations).
 const steps=(prev-observedTime)/step;
 const grid=Array.from({length:steps},(_,i)=>({time:observedTime+(i+1)*step}));
 return {profile,grid,line:profile.map(p=>({time:p.time,value:p.median}))};
}
// Read-only summary of the validated projection: a movement *range*, not
// a directional signal or a calibrated probability of a profitable trade.
function forecastRange(projection){
 const points=projection?.profile;
 if(!Array.isArray(points)||points.length<2)return null;
 const first=points[0],last=points.at(-1);
 const minutes=(last.time-first.time)/60,reference=first.median;
 if(!Number.isFinite(minutes)||minutes<=0||!Number.isFinite(reference)||reference<=0)return null;
 return {minutes,lower:last.lower,median:last.median,upper:last.upper,
  lowerPct:(last.lower/reference-1)*100,upperPct:(last.upper/reference-1)*100};
}
// Keep a faithful fallback for historical corrections while live ticks use
// update() rather than repeatedly rebuilding entire chart series.
function candleChangePlan(previous,current){
 if(!current.length)return {mode:'empty',from:0};
 if(!previous.length||current.length<previous.length||
    previous[0].time!==current[0].time)return {mode:'reset',from:0};
 const equal=(a,b)=>a.time===b.time&&a.open===b.open&&a.high===b.high&&
   a.low===b.low&&a.close===b.close&&a.volume===b.volume&&a.closed===b.closed;
 for(let i=0;i<previous.length-1;i++){
  if(!equal(previous[i],current[i]))return {mode:'reset',from:0};
 }
 const last=previous.length-1;
 if(previous[last].time!==current[last].time)return {mode:'reset',from:0};
 for(let i=previous.length;i<current.length;i++){
  if(!Number.isSafeInteger(current[i].time)||
     current[i].time<=current[i-1].time)return {mode:'reset',from:0};
 }
 const from=equal(previous[last],current[last])?previous.length:last;
 return {mode:from<current.length?'tail':'same',from};
}
class OverlayPrimitive {
 constructor(runtime){this.r=runtime;this.view={zOrder:()=> 'bottom',renderer:()=>({draw:target=>target.useMediaCoordinateSpace(scope=>this.draw(scope))})};}
 attached({chart,series,requestUpdate}){this.chart=chart;this.series=series;this.requestUpdate=requestUpdate;}
 detached(){this.requestUpdate=null;}
 paneViews(){return [this.view];}
 update(){this.requestUpdate?.();}
 draw({context:ctx,mediaSize}){
  const r=this.r,ts=this.chart.timeScale(),py=p=>this.series.priceToCoordinate(p),tx=t=>ts.timeToCoordinate(t);
  ctx.save();ctx.beginPath();ctx.rect(0,0,mediaSize.width,mediaSize.height);ctx.clip();
  if(r.layers.ribbon){
   const points=r.data?.analysis.overlay||[];let segment=[];let dir=0;
   const paint=()=>{if(segment.length<2)return;ctx.beginPath();segment.forEach((p,i)=>{const x=tx(p.time),y=py(p.upper);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});[...segment].reverse().forEach(p=>ctx.lineTo(tx(p.time),py(p.lower)));ctx.closePath();const alpha=.38*r.opacity;ctx.fillStyle=dir>0?`rgba(49,243,162,${alpha})`:`rgba(255,84,116,${alpha})`;ctx.shadowBlur=r.layers.glow?12*r.opacity:0;ctx.shadowColor=dir>0?'#26FF99':'#FF426B';ctx.fill();ctx.shadowBlur=0;};
   for(const p of points){if(p.direction!==dir){paint();segment=[];dir=p.direction;}if(dir&&tx(p.time)!=null&&py(p.upper)!=null)segment.push(p);}paint();
  }
  const data=r.data,price=data?.quote?.price;
  if(price&&r.layers.entry&&data.candles?.length){
   const times=data.candles;const start=tx(times[Math.max(0,times.length-24)]?.time);const end=tx(times.at(-1)?.time);const y=py(price);
   if(start!=null&&end!=null&&y!=null){
    for(const [k,level,color] of [['sl',r.inputs.stop,'rgba(239,91,128,.12)'],['tp',r.inputs.target,'rgba(55,205,151,.10)']]){
     const yy=py(+level);if(r.layers[k]&&yy!=null){ctx.fillStyle=color;ctx.fillRect(start,Math.min(y,yy),end-start,Math.abs(yy-y));}
    }
   }
  }
  // Median line and uncertainty fan share the SAME validated candle-close
  // timestamps. A malformed/stale forecast cannot render either layer.
  if(r.forecastVisible&&r.forecastProfile?.length){
   const plot=r.forecastProfile.map(p=>({x:tx(p.time),low:py(p.lower),high:py(p.upper)}));
   if(plot.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.low)&&Number.isFinite(p.high))){
    ctx.beginPath();plot.forEach((p,i)=>i?ctx.lineTo(p.x,p.high):ctx.moveTo(p.x,p.high));
    [...plot].reverse().forEach(p=>ctx.lineTo(p.x,p.low));ctx.closePath();
    ctx.fillStyle='rgba(103,170,255,.16)';ctx.fill();
   }
  }
  ctx.restore();
 }
}
export default function(component){
 const {data:d,parentElement,setStateValue,setTriggerValue}=component;
 const root=parentElement.querySelector('.terminal');if(!root)return;
 root.__abort?.abort();const abort=new AbortController();root.__abort=abort;const ev={signal:abort.signal};
 const $=id=>root.querySelector('#'+id),all=q=>root.querySelectorAll(q),text=(id,t)=>{$(id).textContent=t;};
 const num=(x,digits=2)=>Number.isFinite(+x)?new Intl.NumberFormat('ru-RU',{maximumFractionDigits:digits,minimumFractionDigits:Math.min(2,digits)}).format(+x):'—';
 const money=x=>num(x)+' USDT';const local=t=>new Date(t*1000).toLocaleString();
 let r=root.__runtime;
 if(!r){
  r=root.__runtime={layers:{ribbon:true,glow:true,markers:true,ema:true,st:false,volume:true,entry:true,sl:true,tp:true},forecastVisible:true,opacity:.85,tab:'positions',context:'',inputs:{},seq:0,priceLines:{},renderCount:0};
  r.chart=LC.createChart($('chart'),{autoSize:true,layout:{background:{type:'solid',color:'#0D1519'},textColor:'#839B9C',fontSize:11,attributionLogo:true},grid:{vertLines:{color:'#33444C'},horzLines:{color:'#33444C'}},crosshair:{mode:LC.CrosshairMode.Normal},rightPriceScale:{borderColor:'#2b3747',scaleMargins:{top:.12,bottom:.20}},timeScale:{borderColor:'#2b3747',timeVisible:true,secondsVisible:false,rightOffset:8},localization:{locale:'ru-RU',timeFormatter:t=>new Date(t*1000).toLocaleString()}});
  r.candles=r.chart.addSeries(LC.CandlestickSeries,{upColor:'#26B985',downColor:'#D85168',borderVisible:false,wickUpColor:'#26B985',wickDownColor:'#D85168',priceLineVisible:true});
  r.volume=r.chart.addSeries(LC.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});r.volume.priceScale().applyOptions({scaleMargins:{top:.84,bottom:0}});
  const opts={lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false};
  r.fast=r.chart.addSeries(LC.LineSeries,{...opts,color:'#45d3a7'});r.slow=r.chart.addSeries(LC.LineSeries,{...opts,color:'#e2c36f'});r.st=r.chart.addSeries(LC.LineSeries,{...opts,color:'#ac9eea',lineStyle:LC.LineStyle.Dashed,visible:false});
  r.forecastLine=r.chart.addSeries(LC.LineSeries,{...opts,color:'#79B5FF',lineStyle:LC.LineStyle.Dashed,lineWidth:2,visible:true});
  r.forecastGrid=r.chart.addSeries(LC.LineSeries,{...opts,visible:false});
  r.markers=LC.createSeriesMarkers(r.candles,[]);r.primitive=new OverlayPrimitive(r);r.candles.attachPrimitive(r.primitive);
  r.observer=new MutationObserver(()=>{if(!root.isConnected){clearTimeout(r.timer);clearTimeout(r.prefTimer);r.observer.disconnect();r.chart.remove();root.__runtime=null;}});r.observer.observe(document.body,{childList:true,subtree:true});
  r.chart.subscribeCrosshairMove(p=>{const bar=p.seriesData?.get(r.candles);if(bar)text('crosshair',`${local(p.time)}  O ${num(bar.open)}  H ${num(bar.high)}  L ${num(bar.low)}  C ${num(bar.close)}`);const sig=r.signalsByTime?.get(p.time);$('signalTooltip').hidden=!sig?.length;if(sig?.length)$('signalTooltip').textContent=sig.map(s=>`${s.type==='BUY'?'BUY':'SELL / EXIT'} · ${s.strategy}\nГраница закрытия ${local(s.timestamp)} · ${num(s.reference_price)} USDT\nФактически обнаружен ${local(s.detected_at)}\nИсторическая отметка условия, не исполненная сделка\n${(Array.isArray(s.explanation)?s.explanation:[]).join('\n')}\n${s.regime} · ${s.status}\n${JSON.stringify(s.parameters)}\n${s.cost_assumption}`).join('\n\n');});
  r.chart.subscribeClick(p=>{const s=r.signalsByTime?.get(p.time)?.at(-1);if(s)showSignal(s);});
 }
 function readPrefs(){return {version:1,...r.layers,intensity:+$('opacity').value,width:+$('width').value,line_opacity:+$('lineOpacity').value,fast_color:$('fastColor').value,slow_color:$('slowColor').value};}
 function applyPrefs(p){for(const k of Object.keys(r.layers))r.layers[k]=p[k];$('opacity').value=p.intensity;r.opacity=p.intensity/100;$('width').value=p.width;$('lineOpacity').value=p.line_opacity;$('fastColor').value=p.fast_color;$('slowColor').value=p.slow_color;}
 function savePrefs(){r.pendingPrefs=JSON.stringify(readPrefs());clearTimeout(r.prefTimer);r.prefTimer=setTimeout(()=>setStateValue('preferences',JSON.parse(r.pendingPrefs||JSON.stringify(readPrefs()))),250);}
 if(r.pendingPrefs===JSON.stringify(d.overlay_settings))r.pendingPrefs=null;
 if(d.overlay_settings&&!r.pendingPrefs&&r.appliedPrefs!==JSON.stringify(d.overlay_settings)){applyPrefs(d.overlay_settings);r.appliedPrefs=JSON.stringify(d.overlay_settings);}
 r.data=d;r.renderCount++;root.dataset.renders=r.renderCount;
 // Time-indexed signal lookup avoids rescanning the full list per mouse move.
 r.signalsByTime=new Map();
 for(const signal of d.signals){
  const bucket=r.signalsByTime.get(signal.timestamp);
  if(bucket)bucket.push(signal);
  else r.signalsByTime.set(signal.timestamp,[signal]);
 }
 const changed=r.context!==d.context;
 if(changed){for(const key of ['candles','volume','fast','slow','st','forecastLine','forecastGrid'])r[key].setData([]);r.forecastProfile=null;r.forecastGridKey='';r.markers.setMarkers([]);r.version=-1;r.context=d.context;r.inputs={...d.inputs};r.seq=d.inputs.seq||0;r.initializedPrice=!!d.quote.price;r.lastRows=[];r.lastCandleSnapshot=[];r.forecastKey='';r.chart.timeScale().resetTimeScale();}
 else if(!r.initializedPrice&&d.quote.price){r.inputs={...d.inputs};r.initializedPrice=true;}
 else if(d.inputs.seq>r.seq){r.inputs={...d.inputs};r.seq=d.inputs.seq;}
 root.dataset.context=d.context;const s=r.inputs;
 function showSignal(sig){
  text('signal',sig?(sig.type==='BUY'?'Potential Buy':'Potential Exit'):'No Signal');
  text('strategy',sig?sig.strategy+' · '+local(sig.timestamp):'Ожидание подтверждённого сигнала');
  text('reasons',sig?(Array.isArray(sig.explanation)?sig.explanation:[]).join('\n')+'\nСформирован после закрытия свечи.\n'+sig.invalidation:'Условия стратегий ещё не выполнены.');
 }
 text('market',d.symbol.replace('USDT',' / USDT'));text('price',d.quote.price?num(d.quote.price):'—');text('change',d.quote.change!=null?num(d.quote.change)+'% · 24h':'—');$('change').className=d.quote.change>=0?'bull':'bear';text('connection',d.status+(d.quote.ts?' · '+num(d.age,0)+'с':''));text('tradingMode',d.mode==='Paper Trading'?'LOCAL PAPER':d.mode.toUpperCase());root.dataset.fresh=d.fresh?'true':'false';
 $('connectionError').hidden=!d.error&&!(!d.fresh&&d.candles.length);text('connectionError',d.error||'Stale Data · котировки устарели; действия с виртуальными позициями заблокированы.');
 const forecast=d.intelligence?.forecast;
 text('forecastStatus',forecast?.status==='EXPERIMENTAL'?'Forecast · эксперимент: Random Walk + EWMA, модельный 80% диапазон (НЕ проверенная вероятность).':('Forecast: '+(forecast?.status||'UNAVAILABLE')+' · '+(forecast?.reason||'нет доступного прогноза')));
 text('regime',d.analysis.regime);$('regime').className=d.analysis.regime==='Bullish'?'bull':d.analysis.regime==='Bearish'?'bear':'';showSignal(d.signals.at(-1));
 const life=d.lifecycle?.active||{state:'NO_SIGNAL',reason:'Подходящих условий нет'};
 text('lifecycleState',life.state+(life.type?' · '+life.type:'')+' — '+life.reason);
 root.dataset.signalState=life.state;
 text('signal',life.state==='POTENTIAL'?'Potential '+life.type+' — Awaiting Confirmation':life.state==='ACTIONABLE'?'Actionable '+life.type:life.state);
 if(life.strategy){text('strategy',life.strategy);text('reasons',(life.explanation||[]).join('\n')+'\n'+life.reason);}
 text('entryZone',life.maximum_entry_price&&!['EXPIRED','INVALIDATED'].includes(life.state)?'Вход '+num(life.minimum_entry_price)+'–'+num(life.maximum_entry_price)+' · до '+local(life.expiration):'');
 text('quality',life.quality?('Net R/R '+num(life.quality.rr)+(life.quality.rr<1?' · Poor Entry Conditions — неблагоприятное соотношение после издержек':' · техническая оценка, не вероятность прибыли')):'');
 const lastBar=d.candles.at(-1),duration=d.interval==='D'?86400:+d.interval*60;
 const left=lastBar?Math.max(0,Math.ceil(lastBar.time+duration-Date.now()/1000)):0;
 text('candleTimer',lastBar?'До закрытия свечи '+Math.floor(left/60)+':'+String(left%60).padStart(2,'0'):'Ожидание свечей');
 text('protectionStatus',d.protection?.message||'Protective Orders Not Actively Monitored');
 r.notified??=new Set();r.sound??=false;$('sound').checked=r.sound;
 $('sound').addEventListener('change',()=>{r.sound=$('sound').checked;if(r.sound){r.audio??=new AudioContext();r.audio.resume();}},ev);
 $('notifications').addEventListener('click',()=>{if('Notification' in window)Notification.requestPermission().catch(()=>{});},ev);
 for(const n of d.lifecycle?.notifications||[]){
  if(r.notified.has(n.id))continue;r.notified.add(n.id);
  if(n.symbol!==d.symbol||n.timeframe!==d.interval||Date.now()/1000-n.time>5||!r.initialNotifications)continue;
  if(r.sound&&r.audio?.state==='running'){const o=r.audio.createOscillator(),g=r.audio.createGain();g.gain.value=.06;o.connect(g);g.connect(r.audio.destination);o.frequency.value=660;o.start();o.stop(r.audio.currentTime+.12);}
  if('Notification' in window&&Notification.permission==='granted'){try{new Notification('MOEX · '+n.state,{body:n.message,tag:n.id});}catch{}}
 }
 r.initialNotifications=true;
 $('empty').hidden=!!d.candles.length;
 const bars=d.candles.map(c=>({time:c.time,open:c.open,high:c.high,low:c.low,close:c.close}));
 if(bars.length){
  const plan=candleChangePlan(r.lastCandleSnapshot||[],d.candles);
  const volumes=d.candles.map(c=>({time:c.time,value:c.volume,
   color:c.close>=c.open?'#235647':'#653847'}));
  if(plan.mode==='reset'){
   r.candles.setData(bars);
   r.volume.setData(volumes);
   if(!r.lastRows?.length)r.chart.timeScale().setVisibleLogicalRange({
    from:Math.max(0,bars.length-120),to:bars.length+10});
  }else if(plan.mode==='tail'){
   for(let i=plan.from;i<bars.length;i++){
    r.candles.update(bars[i]);
    r.volume.update(volumes[i]);
   }
  }
  // Defensive historical snapshot: same-version mutations must not go stale.
  r.lastCandleSnapshot=d.candles.map(c=>({
   time:c.time,open:c.open,high:c.high,low:c.low,
   close:c.close,volume:c.volume,closed:c.closed}));
  r.lastRows=bars;
  // Never offset a predicted CLOSE time to the beginning of its candle.
  // Validate provenance and quantile ordering before publishing any chart data.
  const projection=forecastProjection(d);
  r.forecastProfile=projection?.profile||null;
  const nextGridKey=projection?JSON.stringify(projection.grid):'';
  if(r.forecastGridKey!==nextGridKey){
   r.forecastGrid.setData(projection?.grid||[]);
   r.forecastGridKey=nextGridKey;
  }
  const nextForecastKey=projection?JSON.stringify(projection.line):'';
  if(r.forecastKey!==nextForecastKey){
   r.forecastLine.setData(projection?.line||[]);
   r.forecastKey=nextForecastKey;
  }
  r.forecastLine.applyOptions({visible:r.forecastVisible&&!!projection});
  const range=forecastRange(projection);
  if(range){
   const horizon=range.minutes%1440===0?range.minutes/1440+' сут.':range.minutes%60===0?range.minutes/60+' ч.':range.minutes+' мин.';
   const signed=value=>(value>=0?'+':'')+num(value)+'%';
   text('forecastStatus','Forecast · эксперимент · '+horizon+': модельный диапазон '+
    num(range.lower)+'–'+num(range.upper)+' USDT ('+signed(range.lowerPct)+' … '+
    signed(range.upperPct)+' от последнего закрытия), медиана '+num(range.median)+
    ' USDT. Random Walk + EWMA: номинальные 80%, независимая вероятность не подтверждена. Направление и доходность сделки не прогнозируются.');
  }else if(d.intelligence?.forecast?.status==='EXPERIMENTAL')
   text('forecastStatus','Forecast скрыт: данные, горизонт или математические границы не соответствуют текущему графику.');
  r.primitive.update();
  if(r.version!==d.version||changed||plan.mode!=='same'){
   for(const [key,field] of [['fast','fast'],['slow','slow'],['st','supertrend']])r[key].setData(d.analysis.overlay.filter(p=>Number.isFinite(p[field])).map(p=>({time:p.time,value:p[field]})));
   r.version=d.version;
  }
 }else{
  // Clear the last visible projection whenever the candle feed becomes empty.
  // Otherwise an old forecast stays painted against an "empty" market warning.
  for(const series of [r.candles,r.volume,r.fast,r.slow,r.st,r.forecastLine,r.forecastGrid])series.setData([]);
  r.lastRows=[];r.lastCandleSnapshot=[];r.forecastKey='';r.forecastGridKey='';r.forecastProfile=null;r.version=-1;r.markers.setMarkers([]);r.primitive.update();
  if(d.intelligence?.forecast?.status==='EXPERIMENTAL')
   text('forecastStatus','Forecast скрыт: нет свечей для привязки прогноза к графику.');
 }
 const rule=d.rules||{step:'0.00001',tick:'.01',minimum:'5'};const step=+rule.step,tick=+rule.tick;
 r.candles.applyOptions({priceFormat:{type:'price',precision:Math.max(0,-Math.floor(Math.log10(tick))),minMove:tick}});
 function syncInputs(){if(s.input_mode==='amount'&&d.inputs.seq===r.seq){s.quantity=d.inputs.quantity;}$('budgetMode').value=s.budget_mode||'notional';$('budget').value=s.budget||'25';$('budgetField').hidden=s.input_mode!=='amount';$('quantity').readOnly=s.input_mode==='amount';text('quantityEstimate',s.input_mode==='amount'?'≈ оценка':'');$('byAmount').classList.toggle('active',s.input_mode==='amount');$('byQuantity').classList.toggle('active',s.input_mode!=='amount');for(const [id,key] of [['quantity','quantity'],['stop','stop'],['target','target'],['risk','risk_pct']])if(root.activeElement!==$(id))$(id).value=s[key];$('quantity').step=rule.step;$('stop').step=$('target').step=rule.tick;$('quantitySlider').step=rule.step;$('quantitySlider').max=d.quote.price?Math.max(step,d.account.cash/d.quote.price*.25):1;$('quantitySlider').value=s.quantity;text('riskText',num(s.risk_pct)+'%');}
 const rounded=(v,step)=>{const decimals=Math.min(12,Math.max(0,Math.ceil(-Math.log10(step))));return (Math.round(v/step)*step).toFixed(decimals);};
 function publish(){clearTimeout(r.timer);r.timer=setTimeout(()=>setStateValue('request',{context:d.context,inputs:{...s,seq:r.seq}}),180);}
 function touch(){r.seq++;s.seq=r.seq;syncInputs();calculate();levels();publish();}
 function calculate(){
  const p=d.inputs.seq===r.seq?d.preview:null,qty=+s.quantity;
  for(const [id,k] of [['amount','amount'],['fee','fee'],['loss','loss'],['gain','gain'],['cashAfter','cash_after']])text(id,p?money(p[k]):'…');
  text('qualityCosts',p?.costs?'Gross R/R '+num(p.costs.gross_rr)+' · Net R/R '+num(p.costs.rr)+'\nRound-trip fee '+money(p.costs.round_trip_fee)+' · совокупные издержки '+money(p.costs.round_trip_cost)+'\nВыход сейчас: комиссия '+money(p.costs.exit_fee)+' · slippage обеих сторон '+money(p.costs.slippage_cost)+'\nPaper assumption · эти издержки уже учтены в Net R/R':'Нет актуального расчёта');
  text('rr',p?num(p.rr):'…');text('costs',p?num(p.spread,4)+' / '+p.slippage_bps+' bps':'…');
  const synced=d.inputs.seq===r.seq;const valid=d.preview?.allowed&&synced&&d.fresh;
  text('validation',!d.fresh?'Stale Data / Connection Lost':!synced?'Проверка риска…':d.input_error||(d.preview?.errors||[]).join(' · ')||(valid?'Риск проверен · '+num(d.preview.risk_pct)+'% капитала':'Введите параметры'));
  $('buy').disabled=d.mode!=='Paper Trading'||!valid;
  const held=+(d.state.positions[d.symbol]?.qty||0),allocation=d.inventory?.[d.symbol],available=+(allocation?.sellable_quantity||0);
  $('closeAll').hidden=!held;$('closeAll').disabled=d.mode!=='Paper Trading'||!d.fresh||available<=0;
  text('closeAll',allocation?.fully_sellable?'Закрыть всю позицию · предпросмотр':'Продать доступное · остаток сохранится');
  $('sell').disabled=d.mode!=='Paper Trading'||!d.fresh||!synced||qty<=0||qty>available;
  text('positionInventory',held?(allocation?'На счёте '+allocation.net_holdings+' · продаваемо '+allocation.sellable_quantity+' · остаток '+allocation.non_sellable_residue:'Нет свежих правил для расчёта доступного количества'):'');
  const edit=synced?d.protection_preview:null;
  text('protectionDraft',held?(edit?'Stop '+num(edit.old_stop)+' → '+num(edit.stop)+' · Target '+num(edit.old_target)+' → '+num(edit.target)+' · риск Δ '+money(edit.risk_delta)+' · Net R/R '+(edit.rr==null?'—':num(edit.rr)):d.protection_error||'Проверка новых уровней…'):'');
  $('applyProtection').hidden=!held;$('applyProtection').disabled=d.mode!=='Paper Trading'||!d.fresh||!edit?.allowed;
  $('recommend').disabled=!d.preview||!d.fresh;text('notice',d.notice);
  const qa=d.quality_assessment;text('entryQuality',qa?.quality||'—');text('attention',qa?.attention||'Wait');text('qualityReason',(qa?.reasons||[]).slice(0,2).join(' · ')+' · Statistical edge not validated');text('signalAge',qa?.confirmed_at?'Подтверждение '+local(qa.confirmed_at)+' · возраст '+Math.floor(qa.age_seconds||0)+' сек.':'Подтверждённый вход отсутствует');
 }
 function line(key,price,color,title,visible,style=LC.LineStyle.Dashed){
  if(!visible||!Number.isFinite(+price)||+price<=0){if(r.priceLines[key])r.candles.removePriceLine(r.priceLines[key]);delete r.priceLines[key];return;}
  const opt={price:+price,color,lineWidth:1,lineStyle:style,axisLabelVisible:true,title};if(r.priceLines[key])r.priceLines[key].applyOptions(opt);else r.priceLines[key]=r.candles.createPriceLine(opt);
 }
 function levels(){
  line('entry',d.quote.ask,'#84a9d0','ENTRY',r.layers.entry&&!d.state.positions[d.symbol]);line('sl',s.stop,'#D85168','STOP ↕',r.layers.sl);line('tp',s.target,'#26B985','TARGET ↕',r.layers.tp);
  const p=d.state.positions[d.symbol];for(const [k,field,color] of [['pos','entry','#eee5bd'],['psl','stop','#b67b90'],['ptp','target','#7ebaa1']])line(k,p?.[field],color,'PAPER '+field.toUpperCase(),!!p&&r.layers[k==='pos'?'entry':k==='psl'?'sl':'tp']&&(k==='pos'||Math.abs(+p[field]-+(field==='stop'?s.stop:s.target))>tick/2),LC.LineStyle.Dotted);
  r.primitive.update();
 }
 function layers(){
  const alpha=hex=>'rgba('+[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)).join(',')+','+(+$('lineOpacity').value/100)+')';
  for(const key of Object.keys(r.layers))$(key).checked=r.layers[key];
  r.fast.applyOptions({visible:r.layers.ema,lineWidth:+$('width').value,color:alpha($('fastColor').value)});r.slow.applyOptions({visible:r.layers.ema,lineWidth:+$('width').value,color:alpha($('slowColor').value)});r.st.applyOptions({visible:r.layers.st,lineWidth:+$('width').value,color:alpha('#ac9eea')});r.volume.applyOptions({visible:r.layers.volume});
  const candleTimes=new Set(d.candles.map(c=>c.time));
   r.markers.setMarkers(r.layers.markers?[...new Map(d.signals.filter(s=>candleTimes.has(s.timestamp)).map(s=>[s.timestamp+':'+s.type,s])).values()].map(s=>({time:s.timestamp,position:s.type==='BUY'?'belowBar':'aboveBar',shape:s.type==='BUY'?'arrowUp':'arrowDown',color:s.type==='BUY'?'#31F3A2':'#FF5474',text:s.type==='BUY'?'BUY':'SELL',size:.7})).sort((a,b)=>a.time-b.time):[]);
  root.dataset.ribbon=String(r.layers.ribbon);root.dataset.markers=String(r.layers.markers);levels();
 }
 function showJournal(){
  const box=$('journalBody');box.replaceChildren();const table=document.createElement('table');
  const row=(values,head=false)=>{const tr=document.createElement('tr');for(const val of values){const td=document.createElement(head?'th':'td');td.textContent=String(val??'—');tr.append(td);}table.append(tr);};
  if(r.tab==='positions'){row(['Инструмент','На счёте','Продаваемо','Остаток','Средний вход','Stop','Target'],true);for(const [sym,p] of Object.entries(d.state.positions))row([sym,p.qty,d.inventory?.[sym]?.sellable_quantity,d.inventory?.[sym]?.non_sellable_residue,num(p.entry),num(p.stop),num(p.target)]);}
  if(r.tab==='orders'){row(['Время','Инструмент','Сторона','Количество','Исполнение','Комиссия','Статус / причина'],true);for(const o of d.orders)row([local(o.time),o.symbol,o.side,o.quantity,num(o.fill),num(o.fee),o.status+(o.error?' · '+o.error:'')]);}
  if(r.tab==='signals'){row(['Свеча UTC','Подтверждён после','Обнаружен','Стратегия','Сигнал','Цена'],true);for(const sig of [...d.signals].reverse().slice(0,100))row([new Date(sig.candle_time*1000).toISOString(),local(sig.timestamp),local(sig.detected_at),sig.strategy,sig.type,num(sig.reference_price)]);}
  if(r.tab==='events'){row(['Время','Событие'],true);for(const e of [...d.events,...d.journal].sort((a,b)=>b.time-a.time))row([local(e.time),e.message]);}
  if(r.tab==='stats'){row(['Стратегия','BUY','EXIT','Оценка прибыльности'],true);for(const name of ['Trend Following','Mean Reversion','Breakout Detection'])row([name,d.signals.filter(s=>s.strategy===name&&s.type==='BUY').length,d.signals.filter(s=>s.strategy===name&&s.type==='EXIT').length,'Не проверялась']);}
  box.append(table);if(table.rows.length===1){const p=document.createElement('p');p.textContent='Записей пока нет';box.append(p);}
 }
 const selected=$('selectedSignal').value,choices=(d.lifecycle?.records||[]).filter(x=>x.type==='BUY');
 $('selectedSignal').replaceChildren(new Option('Ручное решение · без сигнала',''),...choices.map(x=>new Option(x.strategy+' · '+x.state+' · '+local(x.first_seen||x.timestamp),x.id)));
 if(choices.some(x=>x.id===selected))$('selectedSignal').value=selected;
 $('forecastOverlay').checked=r.forecastVisible;
 $('forecastOverlay').addEventListener('change',()=>{r.forecastVisible=$('forecastOverlay').checked;r.forecastLine.applyOptions({visible:r.forecastVisible&&r.forecastKey!==''});r.primitive.update();},ev);
 syncInputs();calculate();layers();showJournal();
 for(const [id,key] of [['equity','equity'],['cash','cash'],['unrealized','unrealized'],['realized','realized'],['openRisk','risk']])text(id,money(d.account[key]));text('valuationStatus',d.account.missing_quotes.length?'Неполная оценка: нет свежих цен '+d.account.missing_quotes.join(', ')+'. Для отсутствующей цены используется цена входа; новые сделки заблокированы.':'Equity по Bid; net-поступление от допустимой продажи с текущими издержками (остаток не включён): '+money(d.account.liquidation_equity)+'. Исторические комиссии не пересчитываются.');text('drawdown',num(d.account.drawdown*100)+'%');text('counts',Object.keys(d.state.positions).length+' поз. · '+d.orders.length+' заявок · '+d.signals.length+' сигналов');
 for(const [id,key] of [['quantity','quantity'],['stop','stop'],['target','target'],['risk','risk_pct'],['quantitySlider','quantity']])$(id).addEventListener('input',()=>{s[key]=$(id).value;if(key==='quantity')s.input_mode='quantity';touch();},ev);
 $('plus').addEventListener('click',()=>{s.input_mode='quantity';s.quantity=rounded(+s.quantity+step,step);touch();},ev);$('minus').addEventListener('click',()=>{s.input_mode='quantity';s.quantity=rounded(Math.max(0,+s.quantity-step),step);touch();},ev);
 $('recommend').addEventListener('click',()=>{if(d.preview){s.input_mode='quantity';s.quantity=d.preview.recommended;touch();}},ev);
 for(const [id,side] of [['buy','BUY'],['sell','SELL']])$(id).addEventListener('click',()=>{if($(id).disabled)return;$(id).disabled=true;setTriggerValue('action',{context:d.context,stage:'prepare',id:crypto.randomUUID(),side,signal_id:$('selectedSignal').value||null,notes:$('tradeNotes').value,inputs:{...s,seq:r.seq}});},ev);

 $('byAmount').addEventListener('click',()=>{s.input_mode='amount';touch();},ev);
 $('byQuantity').addEventListener('click',()=>{s.input_mode='quantity';touch();},ev);
 $('budgetMode').addEventListener('change',()=>{s.budget_mode=$('budgetMode').value;touch();},ev);
 $('budget').addEventListener('input',()=>{s.budget=$('budget').value;s.input_mode='amount';touch();},ev);
 $('closeAll').addEventListener('click',()=>{s.input_mode='quantity';s.quantity=d.inventory[d.symbol].sellable_quantity;r.seq++;s.seq=r.seq;syncInputs();setTriggerValue('action',{context:d.context,stage:'prepare',id:crypto.randomUUID(),side:'SELL',dispose_sellable:true,inputs:{...s,seq:r.seq}});},ev);
 const pending=d.pending,dialog=$('confirmDialog');
 if(pending&&pending.kind!=='protection'&&pending.request.symbol===d.symbol&&d.mode==='Paper Trading'){
  const isBuy=pending.request.side==='BUY',est=pending.estimate;
  if(r.pendingId!==pending.id){r.pendingId=pending.id;$('riskConsent').checked=false;r.confirming=false;r.cancelling=false;}
  if(!dialog.open)dialog.showModal();
  text('confirmTitle',isBuy?'Подтверждение покупки':'Подтверждение продажи');text('confirmSymbol',d.symbol.replace('USDT',' / USDT'));text('confirmSide',isBuy?'Market Buy':'Market Sell');root.querySelector('.paperBadge').textContent=pending.source.includes('QA')?'LOCAL PAPER · QA SYNTHETIC':'LOCAL PAPER · виртуальные средства';
  const rows=[...(pending.input_mode==='amount'?[['Запрошено до округления',money(pending.budget)]]:[]),['Сумма ордера · округлено вниз',money(est.amount)],['Количество · фиксируется',pending.request.quantity+' '+d.symbol.replace('USDT','')],['Примерная цена',money(est.entry)],['Комиссия · '+(est.cost_model?.fees.taker*100)+'% '+(est.fill?.fee_currency||'quote'),est.fill?.fee_currency==='base'?num(est.fill.fee_quantity,10)+' '+d.symbol.replace('USDT','')+' ≈ '+money(est.fee):money(est.fee)],['Bid/Ask spread',num(pending.spread_bps)+' bps'],['Проскальзывание · предположение',est.cost_model?.execution.slippage_bps+' bps'],['Доступный баланс',money(pending.balance)],['Минимум / шаг количества',pending.rules.minimum+' USDT / '+pending.rules.step],['Stop / Take Profit',num(est.stop)+' / '+num(est.target)],['Плановый убыток / риск',est.loss!=null?money(est.loss)+' / '+num(est.risk_pct,4)+'%':'Закрытие существующего long'],['Источник',pending.source],['Котировка на момент подготовки',local(pending.quote.ts)],[isBuy?'Максимальное списание':'Минимальное зачисление',money(isBuy?Math.min(est.total*1.001,+(pending.request.max_spend||Infinity)):est.total*.999)],['Итого ≈ '+(isBuy?'списание':'зачисление'),money(est.total)]];
  $('confirmHeadline').replaceChildren();
  for(const [k,v] of [['Количество заявки',pending.request.quantity],['Нетто получено',isBuy?num(est.fill.net_base,10)+' '+d.symbol.replace('USDT',''):money(est.total)],['Итог ≈ '+(isBuy?'списание':'зачисление'),money(est.total)],...((est.inventory)?[['Доступно для продажи',est.inventory.sellable_quantity],['После продажи останется',isBuy?est.inventory.remaining_after_sale:est.remaining_quantity]]:[]),['Риск до стопа',isBuy&&est.exit_closeable===false?'Частичная / недоступная защита':est.loss!=null?money(est.loss)+' / '+num(est.risk_pct,4)+'%':'Закрытие long']]){const a=document.createElement('span'),b=document.createElement('b');a.textContent=k;b.textContent=v;$('confirmHeadline').append(a,b);}
  $('confirmDetails').replaceChildren();for(let i=0;i<rows.length;i++){const [k,v]=rows[i],label=document.createElement('span'),value=document.createElement('b');label.textContent=k;value.textContent=v;if(i===rows.length-1){label.className=value.className='total';}$('confirmDetails').append(label,value);}
  const remaining=Math.max(0,Math.floor(pending.expires-Date.now()/1000));text('previewExpiry','Предпросмотр действителен ещё '+remaining+' сек. · текущая давность исходной котировки '+Math.max(0,Math.floor(Date.now()/1000-pending.quote.ts))+' сек.');
  const costsChanged=JSON.stringify(pending.estimate.cost_model)!==JSON.stringify(d.cost_model);text('confirmError',pending.error||(costsChanged?'Тариф изменился: отмените и создайте новый preview':'')+(isBuy&&est.exit_closeable===false?' Комиссия/правила могут оставить непродаваемую часть. При закрытии продаётся только допустимое количество, остаток и себестоимость сохраняются. Защита покрывает лишь допустимый объём. Для другой модели комиссии выберите USDT в настройках Paper.':''));
  const gate=()=>{$('confirmOrder').disabled=!$('riskConsent').checked||remaining<=0||!!pending.error||costsChanged||r.confirming||r.cancelling;};gate();
  text('confirmOrder',r.confirming?'Проверяется результат…':isBuy?'Подтвердить покупку':'Подтвердить продажу');
  $('riskConsent').addEventListener('change',gate,ev);
  $('confirmOrder').addEventListener('click',()=>{if($('confirmOrder').disabled)return;r.confirming=true;gate();text('confirmOrder','Проверяется результат…');setTriggerValue('action',{context:d.context,stage:'confirm',id:pending.id,ack:true});},ev);
  const cancel=()=>{if(r.cancelling)return;r.cancelling=true;$('cancelOrder').disabled=true;$('confirmOrder').disabled=true;setTriggerValue('action',{context:d.context,stage:'cancel',id:pending.id});};$('cancelOrder').disabled=!!r.cancelling;
  $('cancelOrder').addEventListener('click',cancel,ev);dialog.addEventListener('cancel',e=>{e.preventDefault();cancel();},ev);
 }else{if(dialog.open)dialog.close();r.pendingId=null;r.confirming=false;r.cancelling=false;}
 $('applyProtection').addEventListener('click',()=>{if(!$('applyProtection').disabled)setTriggerValue('action',{context:d.context,stage:'prepare_protection',id:crypto.randomUUID(),inputs:{...s,seq:r.seq}});},ev);
 const pd=$('protectionDialog');
 if(pending?.kind==='protection'&&pending.request.symbol===d.symbol&&d.mode==='Paper Trading'){
  const ep=pending.estimate;if(pending.error)r.protectionBusy=false;
  if(r.protectionId!==pending.id){r.protectionId=pending.id;r.protectionBusy=false;$('protectionConsent').checked=false;}
  if(!pd.open)pd.showModal();
  const fields=[['Инструмент',d.symbol],['Stop: было → станет',num(ep.old_stop)+' → '+num(ep.stop)],['Target: было → станет',num(ep.old_target)+' → '+num(ep.target)],['Открытый риск: было → станет',money(ep.old_risk)+' → '+money(ep.new_risk)],['Изменение риска',money(ep.risk_delta)],['Net R/R',ep.rr==null?'—':num(ep.rr)],['Расстояние Stop / Target',num(ep.stop_distance)+' / '+num(ep.target_distance)],['Защищаемое количество',ep.inventory.sellable_quantity+' / '+ep.quantity],['Непродаваемый остаток',ep.inventory.non_sellable_residue],['Допущение для остатка','Нулевая стоимость в оценке риска'],['Источник',pending.source]];
  $('protectionDetails').replaceChildren();for(const [k,v] of fields){const a=document.createElement('span'),b=document.createElement('b');a.textContent=k;b.textContent=v;$('protectionDetails').append(a,b);}
  const remaining=Math.max(0,Math.floor(pending.expires-Date.now()/1000));text('protectionExpiry','Действителен ещё '+remaining+' сек.');text('protectionError',pending.error||'');
  const gate=()=>{$('confirmProtection').disabled=!$('protectionConsent').checked||remaining<=0||!!pending.error||r.protectionBusy;$('cancelProtection').disabled=r.protectionBusy;};gate();
  $('protectionConsent').addEventListener('change',gate,ev);
  $('confirmProtection').addEventListener('click',()=>{if($('confirmProtection').disabled)return;r.protectionBusy=true;gate();setTriggerValue('action',{context:d.context,stage:'confirm_protection',id:pending.id,ack:true});},ev);
  const cancel=()=>{if(r.protectionBusy)return;r.protectionBusy=true;gate();setTriggerValue('action',{context:d.context,stage:'cancel',id:pending.id});};
  $('cancelProtection').addEventListener('click',cancel,ev);pd.addEventListener('cancel',e=>{e.preventDefault();cancel();},ev);
 }else{if(pd.open)pd.close();r.protectionId=null;r.protectionBusy=false;}
 for(const key of Object.keys(r.layers))$(key).addEventListener('change',()=>{r.layers[key]=$(key).checked;all('[data-preset]').forEach(b=>b.classList.remove('active'));layers();savePrefs();},ev);
 all('[data-preset]').forEach(b=>b.addEventListener('click',()=>{const p=b.dataset.preset;Object.assign(r.layers,{ribbon:p!=='clean',ema:p!=='clean',markers:p==='signals'||p==='full',st:p==='full',volume:p!=='clean',entry:p==='full',sl:p==='full',tp:p==='full'});all('[data-preset]').forEach(x=>x.classList.toggle('active',x===b));layers();savePrefs();},ev));
 for(const id of ['width','opacity','lineOpacity','fastColor','slowColor'])$(id).addEventListener('input',()=>{r.opacity=+$('opacity').value/100;layers();savePrefs();},ev);
 $('resetOverlay').addEventListener('click',()=>{applyPrefs(d.overlay_defaults);layers();savePrefs();},ev);
 $('toggleAssistant').addEventListener('click',()=>{const closed=root.classList.toggle('assistantCollapsed');$('toggleAssistant').setAttribute('aria-expanded',String(!closed));},ev);
 $('fit').addEventListener('click',()=>r.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,bars.length-120),to:bars.length+10}),ev);
 all('[data-tab]').forEach(b=>b.addEventListener('click',()=>{r.tab=b.dataset.tab;all('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));showJournal();},ev));
 const canvas=$('chart');
 canvas.addEventListener('pointerdown',e=>{const y=e.clientY-canvas.getBoundingClientRect().top;const candidates=[['sl','stop'],['tp','target']].filter(([layer])=>r.layers[layer]).map(([layer,key])=>({key,dist:Math.abs(y-r.candles.priceToCoordinate(+s[key]))})).sort((a,b)=>a.dist-b.dist);if(candidates[0]?.dist<9){r.drag=candidates[0].key;r.chart.applyOptions({handleScroll:false,handleScale:false});canvas.setPointerCapture(e.pointerId);e.preventDefault();e.stopPropagation();}}, {...ev,capture:true});
 canvas.addEventListener('pointermove',e=>{if(!r.drag)return;const p=r.candles.coordinateToPrice(e.clientY-canvas.getBoundingClientRect().top);if(p>0){s[r.drag]=rounded(p,tick);syncInputs();calculate();levels();}},ev);
 const end=e=>{if(!r.drag)return;r.drag=null;r.chart.applyOptions({handleScroll:true,handleScale:true});touch();if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);};canvas.addEventListener('pointerup',end,ev);canvas.addEventListener('pointercancel',end,ev);
 // Retain the chart and its time/price scales across fragment updates.
}
