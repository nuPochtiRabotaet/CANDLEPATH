// Presentation-only arithmetic. Settled inputs are independently validated by Python.
export default function(component) {
 const {data:d,parentElement,setStateValue,setTriggerValue}=component;
 const root=parentElement.querySelector('.lab');if(!root)return;
 // Component v2 may re-invoke the renderer on the same DOM. Bind exactly once.
 root.__cleanupRender?.();root.__controller?.abort();
 const $=id=>root.querySelector('#'+id), all=s=>root.querySelectorAll(s);
 const a=d.asset, before=d.before, held=d.held, lot=a.lot_size,T=d.tokens;
 const alpha=(hex,opacity)=>'rgba('+[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)).join(',')+','+opacity+')';
 const changedContext=root.__context!==d.context;
 if(changedContext){root.__context=d.context;root.__pinned=null;root.__state={...(d.state||d.initial)};}
 let s=root.__state;
 if(d.state&&d.state.seq>s.seq)s=root.__state={...d.state};
 const abort=new AbortController(),events={signal:abort.signal};root.__controller=abort;let timer;
 const money=x=>x==null||!Number.isFinite(x)?'—':new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2,minimumFractionDigits:2}).format(x)+' ₽';
 const pricefmt=x=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:8,minimumFractionDigits:2}).format(x)+' ₽';
 const pct=x=>x==null?'—':new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(x)+'%';
 const signed=x=>(x>0?'+':'')+money(x);
 const text=(id,t)=>{$(id).textContent=t;};
 const mode=()=>{all('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===s.mode);b.setAttribute('aria-pressed',b.dataset.mode===s.mode)});all('[data-side]').forEach(b=>{b.classList.toggle('active',b.dataset.side===s.side);b.setAttribute('aria-pressed',b.dataset.side===s.side)});};
 // Round user-supplied commission with decimal integer arithmetic, HALF_UP.
 function fraction(v){const z=String(v).toLowerCase().split('e');let t=z[0].replace('.',''),n=(z[0].split('.')[1]||'').length-Number(z[1]||0);if(n<0){t+='0'.repeat(-n);n=0}return [BigInt(t),10n**BigInt(n)];}
 function grossDecimal(price,qty){
  if(!Number.isInteger(qty))return NaN;
  const [n,d]=fraction(price),product=n*BigInt(qty),negative=product<0n;
  const places=d.toString().length-1,digits=(negative?-product:product).toString().padStart(places+1,'0');
  return Number((negative?'-':'')+(places?digits.slice(0,-places)+'.'+digits.slice(-places):digits));
 }
 function fee(gross){if(!s.quantity)return 0;if(!s.fee_known)return null;const [gn,gd]=fraction(gross),[rn,rd]=fraction(s.fee_pct),[mn,md]=fraction(s.minimum_fee);let n=gn*rn,den=gd*rd*100n;if(n*md<mn*den){n=mn;den=md}return Number((n*100n*2n+den)/(2n*den))/100;}
 function calc(){
  const errors=[];let gross=grossDecimal(a.unit_price,s.quantity),f=null,topup=0,after=null;
  if(!Number.isInteger(s.quantity)||s.quantity<0||s.quantity>100000000)errors.push('Нужно целое количество от 0 до 100 000 000.');
  if(s.quantity%lot)errors.push(s.quantity+' бумаг не кратны лоту '+lot+'. Количество не округляется.');
  if(!Number.isFinite(s.fee_pct)||s.fee_pct<0||s.fee_pct>10||!Number.isFinite(s.minimum_fee)||s.minimum_fee<0||s.minimum_fee>1e9)errors.push('Проверьте параметры комиссии.');
  if(!errors.length)f=fee(gross);
  if(f==null)errors.push('Комиссия неизвестна: полная сумма и состояние после не рассчитаны.');
  const total=f==null?null:gross+(s.side==='buy'?f:-f);
  if(s.side==='sell'&&s.quantity>held)errors.push('Нельзя продать больше бумаг, чем есть: '+held+'.');
  if(s.side==='buy'&&s.funding==='topup'&&total!=null)topup=Math.max(0,total-d.cash);
  if(s.side==='buy'&&total!=null&&total>d.cash+topup+1e-7)errors.push('Недостаточно денег: доступно '+money(d.cash)+'. Можно выбрать пополнение.');
  if(d.future_ledger)errors.push('Журнал содержит будущие операции; сегодняшняя оценка не подходит.');
  let cash=null,qty=null;
  if(!errors.length){qty=held+(s.side==='buy'?s.quantity:-s.quantity);cash=d.cash+topup+(s.side==='buy'?-total:total);
   if(before){const positions=before.positions.filter(p=>p.symbol!==a.symbol).map(p=>({...p}));if(qty>0)positions.push({symbol:a.symbol,quantity:qty,market_value:qty*a.unit_price});
    const equity=cash+positions.reduce((v,p)=>v+p.market_value,0);positions.forEach(p=>p.weight_pct=equity?p.market_value/equity*100:0);after={equity,cash,positions};}}
  return {gross,fee:f,total,topup,errors,after,cash,qty};
 }
 const qtyOf=snap=>snap?snap.positions.find(p=>p.symbol===a.symbol)?.quantity||0:held;
 const weight=(snap,symbol)=>snap?snap.positions.find(p=>p.symbol===symbol)?.weight_pct||0:null;
 const concentration=snap=>snap?Math.max(0,...snap.positions.map(p=>p.weight_pct)):null;
 function mix(snap){if(!snap)return null;let m={equity:0,fund:0,bond:0,cash:snap.cash};for(const p of snap.positions){const k=(d.classes||{})[p.symbol]||'unknown';m[k]=(m[k]||0)+p.market_value;}return m;}
 const cfg={displayModeBar:false,responsive:false,scrollZoom:false};
 function layout(extra={}){return {paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{family:'system-ui',color:T.muted,size:11},margin:{l:60,r:14,t:38,b:38},hovermode:'x unified',uirevision:d.context,legend:{orientation:'h',x:0,y:1.02,xanchor:'left',yanchor:'bottom'},xaxis:{gridcolor:T.grid,zerolinecolor:T.line,fixedrange:false},yaxis:{gridcolor:T.grid,zerolinecolor:T.line,automargin:true},...extra};}
 function plot(id,traces,opts={}){
  if(!globalThis.__MOEXPlotly)return;
  const e=$(id),key=JSON.stringify([traces,opts]);if(e.data&&e.__figureKey===key)return;
  e.__desired={traces,opts,key};if(e.__scheduled)return;e.__scheduled=true;
  requestAnimationFrame(()=>{
   e.__scheduled=false;if(!root.isConnected)return;
   const {traces,opts,key}=e.__desired;e.__figureKey=key;
   const shape=opts.shapes?.[0],baseKey=JSON.stringify([traces,{...opts,shapes:undefined}]);
   if(e.data&&e.__baseKey===baseKey&&shape)globalThis.__MOEXPlotly.relayout(e,{'shapes[0].x0':shape.x0,'shapes[0].x1':shape.x1});
   else globalThis.__MOEXPlotly.react(e,traces,layout(opts),cfg);
   e.__baseKey=baseKey;
  });
 }
 function focusAction(kind){
  if(kind==='fee'){$('fees').open=true;$('feeKnown').focus();}
  else if(kind==='profile'){$('constraints').open=true;$('profileKnown').focus();}
  else if(kind==='quantity'){$('quantity').focus();$('quantity').select();}
  else if(kind==='stress'){$('shock').focus();$('shock').scrollIntoView({block:'center'});}
  else if(kind==='history'||kind==='horizon'){update('show_model',true,true);$('modelDetails').scrollIntoView({block:'center'});}
  else if(kind==='refresh_price')send('refresh_price');
 }
 function renderAllocation(m1,m2,after){
  const e=$('allocation');e.replaceChildren();
  const classes=['equity','fund','bond','cash','unknown'],labels=['Акции','Фонды','Облигации','Деньги','Класс неизвестен'],colors=[T.accent,T.fund,T.bond,T.cash,T.muted];
  [['Сейчас',m1,before],['После',m2,after]].forEach(([label,m,snap])=>{let row=document.createElement('div'),name=document.createElement('span'),bar=document.createElement('div');row.className='allocation-row';name.textContent=label;bar.className='allocation-track';
   if(m&&snap?.equity){classes.forEach((k,i)=>{let value=100*(m[k]||0)/snap.equity;if(value>0){let segment=document.createElement('span');segment.style.width=value+'%';segment.style.backgroundColor=colors[i];segment.title=labels[i]+': '+pct(value);segment.setAttribute('aria-label',segment.title);bar.append(segment)}});}else{bar.textContent='Оценка недоступна';bar.classList.add('unknown');}row.append(name,bar);e.append(row);
  });
  let legend=document.createElement('div');legend.className='allocation-legend';labels.slice(0,4).forEach((v,i)=>{let label=document.createElement('span');label.textContent='● '+v;label.style.color=colors[i];legend.append(label)});e.append(legend);
 }

 function drawModel(r){
  const model=d.model,qty=r.qty==null?held:r.qty;
  $('modelDetails').open=s.show_model;all('[data-horizon]').forEach(b=>{b.classList.toggle('active',Number(b.dataset.horizon)===s.horizon);b.setAttribute('aria-pressed',Number(b.dataset.horizon)===s.horizon)});
  if(!s.show_model)return;
  if(!model||model.error){text('modelStatus',model?.error||'Подготавливается история и модель…');$('modelCards').replaceChildren();if(globalThis.__MOEXPlotly)globalThis.__MOEXPlotly.purge($('modelChart'));return;}
  if(s.horizon>model.horizon){text('modelStatus','Для этого горизонта недостаточно истории. Выберите меньший срок.');$('modelCards').replaceChildren();if(globalThis.__MOEXPlotly)globalThis.__MOEXPlotly.purge($('modelChart'));return;}
  const n=s.horizon,x=Array.from({length:n+1},(_,i)=>i),base=qty*a.unit_price;
  text('modelStatus',(model.synthetic?'ИСКУССТВЕННАЯ ИСТОРИЯ · учебный результат. ':'')+qty+' бумаг · '+n+' торговых дней · '+model.runs+' траекторий · '+(r.qty==null?'текущая позиция; операция не применена':'после эксперимента'));
  const cards=$('modelCards');cards.replaceChildren();[['lo','Неблагоприятный · 5-й процентиль'],['mid','Центральный · медиана'],['hi','Благоприятный · 95-й процентиль']].forEach(([k,label])=>{let e=document.createElement('div'),sm=document.createElement('small'),b=document.createElement('b');sm.textContent=label;b.textContent=money(model[k][n]*base);e.append(sm,b);cards.append(e)});
  const ys=k=>model[k].slice(0,n+1).map(v=>v*base);
  plot('modelChart',[{x,y:ys('lo'),mode:'lines',line:{width:0},showlegend:false,hoverinfo:'skip'},{x,y:ys('hi'),mode:'lines',line:{width:0},fill:'tonexty',fillcolor:alpha(T.accent,.16),name:'5–95% модели'},{x,y:ys('mid'),mode:'lines',line:{color:T.accent,width:2},name:'Медиана'}],{xaxis:{title:{text:'Торговые дни'},gridcolor:T.grid},yaxis:{title:{text:'Стоимость позиции, ₽'},gridcolor:T.grid}});
  text('modelLimits','История '+model.history_start+' — '+model.history_end+'. '+model.limits.join(' ')+' Остальные активы и деньги не моделируются.');
 }
 function render(){
  let r=calc();
  const confirmed=!!(d.response&&d.state&&d.state.seq===s.seq);
  if(confirmed){const p=d.response;r={gross:p.order.gross,fee:p.order.fee,total:s.side==='buy'?p.order.buy_total:p.order.sell_proceeds,topup:p.topup,errors:p.errors,after:p.after,cash:p.cash_after??null,qty:p.known_after_quantity??null};}
  const start=performance.now(),snap=r.after||before,qty=r.qty==null?held:r.qty;
  mode();$('unit').value=s.unit;$('funding').value=s.funding;$('funding').disabled=s.side==='sell';
  if((parentElement.activeElement||document.activeElement)!==$('quantity'))$('quantity').value=s.unit==='lots'?s.quantity/lot:s.quantity;
  $('quantity').step=s.unit==='lots'?1:lot;$('quantity').max=s.unit==='lots'?Math.floor(100000000/lot):100000000;
  const max=Math.min(100000000,Math.max(lot*20,Math.ceil(held/lot)*lot,Math.ceil(s.quantity/lot)*lot));$('quantityRange').max=max;$('quantityRange').step=s.quantity%lot?1:lot;$('quantityRange').value=s.quantity;$('quantityRange').disabled=!!(s.quantity%lot)||s.quantity<0||s.quantity>100000000;
  text('quantityInfo',s.quantity+' бумаг · '+(s.quantity/lot).toLocaleString('ru-RU')+' лот. · в портфеле '+held);
  const inputs={feeKnown:'fee_known',feePct:'fee_pct',feeMin:'minimum_fee',profileKnown:'profile_known',months:'months',maxLoss:'max_loss',early:'early',concentrationKnown:'concentration_known',concentrationLimit:'concentration_limit',shock:'shock',scope:'scope'};
  for(const [id,k]of Object.entries(inputs)){const e=$(id);if(e.type==='checkbox')e.checked=s[k];else if((parentElement.activeElement||document.activeElement)!==e)e.value=s[k];}
  root.dataset.validation=d.rejected_seq===s.seq?'rejected':confirmed?'confirmed':'preliminary';root.dataset.validatedSeq=d.state?.seq??-1;
  text('calculationStatus',d.rejected_seq===s.seq?'Некорректные параметры · исправьте ввод':confirmed?(r.errors.length?'Проверено Python · требуется уточнение':'Проверенный результат · Python'):'Предварительный результат · локально');
  $('calculationStatus').className='calculation-status '+(confirmed?'confirmed':'preliminary');
  const currentOnly=s.quantity===0&&held>0;
  text('orderLabel',currentOnly?'Текущая стоимость позиции':s.side==='buy'?'Полная стоимость предполагаемой покупки':'Выручка после комиссии');text('orderTotal',currentOnly?money(held*a.unit_price):r.total==null?'Комиссия неизвестна':money(r.total));
  text('arithmetic',currentOnly?held+' × '+pricefmt(a.unit_price)+' · без предполагаемой операции':s.quantity+' × '+pricefmt(a.unit_price)+' = '+money(r.gross)+' · комиссия '+(r.fee==null?'не задана':money(r.fee)));
  $('orderTotal').classList.toggle('unavailable',r.total==null);
  let warns=[...r.errors];if(!before)warns.push('Полная оценка портфеля недоступна: нет подтверждённых цен всех позиций.');if(r.topup)warns.push('Условное пополнение '+money(r.topup)+' — взнос, не прибыль.');
  text('validation',warns[0]||'');
  const m1=mix(before),m2=mix(r.after),cw=(m,snap,k)=>m&&snap&&!m.unknown?pct(snap.equity?m[k]/snap.equity*100:0):'—';
  const deltaText=(x,y,kind)=>x==null||y==null?'—':kind==='pct'?(y-x>0?'+':'')+pct(y-x).replace('%',' п.п.'):kind==='qty'?(y-x>0?'+':'')+(y-x)+' шт.':signed(y-x);
  const rows=[['Стоимость портфеля',money(before?.equity),money(r.after?.equity),deltaText(before?.equity,r.after?.equity)],['Свободные деньги',money(d.cash),money(r.cash),deltaText(d.cash,r.cash)],['Выбранная бумага',held+' шт.',r.qty==null?'—':r.qty+' шт.',deltaText(held,r.qty,'qty')],['Доля '+a.symbol,pct(weight(before,a.symbol)),pct(weight(r.after,a.symbol)),deltaText(weight(before,a.symbol),weight(r.after,a.symbol),'pct')],['Крупнейшая позиция',pct(concentration(before)),pct(concentration(r.after)),deltaText(concentration(before),concentration(r.after),'pct')],['Доля акций',cw(m1,before,'equity'),cw(m2,r.after,'equity'),''],['Доля облигаций',cw(m1,before,'bond'),cw(m2,r.after,'bond'),'']];
  const tbody=$('comparison');tbody.replaceChildren();rows.forEach(row=>{const tr=document.createElement('tr');row.forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===3&&v!=='—'&&v!=='')td.className='changed';tr.append(td)});tbody.append(tr)});
  renderAllocation(m1,m2,r.after);
  const finding=confirmed?d.response.constraints:null;
  text('verdict',finding?.label||'Проверяю выбранные ограничения…');$('reasons').replaceChildren();
  const why=finding?.why||['Локальные суммы обновлены. Окончательный вывод относится только к подтверждённым параметрам.'];
  why.slice(0,2).forEach(v=>{let li=document.createElement('li');li.textContent=v;$('reasons').append(li)});
  $('findingActions').replaceChildren();(finding?.actions||[]).forEach(action=>{let b=document.createElement('button');b.textContent=action.label;b.addEventListener('click',()=>focusAction(action.kind));$('findingActions').append(b)});
  root.dataset.finding=finding?.status||'pending';
  if(finding){root.dataset.finding=finding.status;text('findingScope','Выбранные проверки: '+finding.coverage.passed+' завершено, '+finding.coverage.unknown+' не проверено. Это не рекомендация.');}
  $('findingChecks').replaceChildren();(finding?.checks||[]).forEach(check=>{let li=document.createElement('li');li.textContent=check.label+' — '+({passed:'проверено',failed:'конфликт',unknown:'неизвестно'}[check.status])+'. '+check.detail;$('findingChecks').append(li);});
  const pin=root.__pinned;$('clearPin').hidden=!pin;$('pinnedComparison').hidden=!pin;
  root.querySelector('[data-action="pin"]').disabled=!confirmed||r.errors.length>0||r.qty==null;
  if(pin){text('pinnedLabel','A: '+pin.state.quantity+' шт. · '+(pin.state.shock>0?'+':'')+pin.state.shock+'%');text('pinnedComparison','A: покупка '+money(pin.result.total)+' · деньги '+money(pin.result.cash)+' | Сейчас: '+money(r.total)+' · деньги '+money(r.cash));}else text('pinnedLabel','');
  $('conclusion').hidden=s.mode!=='Оценить';$('constraints').open=s.mode==='Оценить';
  const stressPrice=a.clean_price*(1+s.shock/100)+a.accrued_interest,delta=qty*a.clean_price*s.shock/100;
  text('shockLabel',(s.shock>0?'+':'')+s.shock+'%');text('stressPrice','Условная цена: '+pricefmt(stressPrice)+' · '+(r.qty==null?'текущая позиция; операция не применена':'после эксперимента'));
  text('stressPosition',money(qty*stressPrice));text('positionDelta',signed(delta));text('stressPortfolio',snap?money(snap.equity+delta):'Оценка недоступна');text('portfolioDelta',snap?signed(delta):'Нет цен других бумаг');
  for(const id of ['positionDelta','portfolioDelta'])$(id).style.color=delta<0?T.loss:delta>0?T.gain:T.muted;
  const x=Array.from({length:101},(_,i)=>i-50),bq=held,aq=r.qty;
  const traces=[];if(s.scope==='position'||before)traces.push({x,y:x.map(v=>bq*a.clean_price*v/100),name:'Сейчас',mode:'lines',line:{color:T.muted,dash:'dash',width:2}});
  if(aq!=null&&(s.scope==='position'||r.after))traces.push({x,y:x.map(v=>aq*a.clean_price*v/100),name:'После',mode:'lines',line:{color:T.accent,width:2}});
  plot('stressChart',traces,{xaxis:{title:{text:'Гипотетическое изменение цены, %'},range:[-50,50],gridcolor:T.grid},yaxis:{title:{text:'Изменение стоимости, ₽'},gridcolor:T.grid},shapes:[{type:'line',x0:s.shock,x1:s.shock,y0:0,y1:1,yref:'paper',line:{color:T.muted,width:1}}]});
  drawModel(r);root.__lastResult=r;root.dataset.lastRenderMs=(performance.now()-start).toFixed(2);
 }
 function send(action){clearTimeout(timer);if(action)s.seq++;const request={context:d.context,state:{...s}};text('syncStatus','Проверяю состояние…');if(action)setTriggerValue('action',{...request,kind:action});else setStateValue('request',request);}
 function update(k,v,immediate=false){if(k==='quantity'&&s.quantity===0&&v>0&&!s.fee_known)$('fees').open=true;s[k]=v;s.seq++;render();clearTimeout(timer);timer=setTimeout(()=>send(),immediate?0:250);}
 all('[data-action]').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.action;if(k==='minus'||k==='plus')update('quantity',Math.max(0,Math.min(100000000,s.quantity+(k==='plus'?lot:-lot))));else if(k==='pin'){root.__pinned={state:{...s},result:JSON.parse(JSON.stringify(root.__lastResult))};render();}else if(k==='clear_pin'){root.__pinned=null;render();}else if(k==='reset'){root.__pinned=null;s=root.__state={...d.initial,seq:s.seq+1};$('fees').open=!s.fee_known&&s.quantity>0;render();send();}else send(k);},events));
 all('[data-mode]').forEach(b=>b.addEventListener('click',()=>update('mode',b.dataset.mode),events));all('[data-side]').forEach(b=>b.addEventListener('click',()=>update('side',b.dataset.side),events));all('[data-horizon]').forEach(b=>b.addEventListener('click',()=>update('horizon',Number(b.dataset.horizon)),events));
 $('unit').addEventListener('change',e=>update('unit',e.target.value),events);$('quantity').addEventListener('input',e=>update('quantity',Number(e.target.value)*(s.unit==='lots'?lot:1)),events);$('quantityRange').addEventListener('input',e=>update('quantity',Number(e.target.value)),events);$('funding').addEventListener('change',e=>update('funding',e.target.value),events);
 const bindings={feeKnown:['fee_known',true],feePct:['fee_pct'],feeMin:['minimum_fee'],profileKnown:['profile_known',true],months:['months'],maxLoss:['max_loss'],early:['early',true],concentrationKnown:['concentration_known',true],concentrationLimit:['concentration_limit'],shock:['shock'],scope:['scope',false,true]};
 for(const [id,[key,check,str]]of Object.entries(bindings))$(id).addEventListener(check||str?'change':'input',e=>update(key,check?e.target.checked:str?e.target.value:Number(e.target.value)),events);
 for(const id of ['quantity','quantityRange','shock','feePct','feeMin'])$(id).addEventListener('change',()=>{clearTimeout(timer);timer=setTimeout(()=>send(),0);},events);
 $('modelDetails').addEventListener('toggle',()=>{if($('modelDetails').open!==s.show_model)update('show_model',$('modelDetails').open,true)},events);
 text('assetName',a.name+' · '+a.symbol);text('unitPrice',pricefmt(a.unit_price));text('lotInfo','Лот '+lot+' · в портфеле '+held+' шт.');
 /* Shared provenance below intentionally replaces legacy formatting. */
 text('provenance',d.price_status.label+' · '+(d.price_status.observation_kind==='snapshot'?'снимок MOEX: ':'наблюдение: ')+d.price_status.observed_display);
 text('sourceDetails',a.source+' · '+a.board+' · '+a.currency+' · наблюдение '+d.price_status.observed_display+' · получение '+d.price_status.retrieved_display+' · сохранение '+d.price_status.saved_display+' · дата оценки '+d.price_status.valuation_display+(d.price_status.observation_kind==='snapshot'?' · SYSTIME: время снимка. Дата последней сделки неизвестна.':''));
 text('bondDetails',a.asset_type==='bond'?'Чистая цена '+a.quoted_pct+'% × номинал '+money(a.face_value)+' + НКД '+money(a.accrued_interest)+' = '+pricefmt(a.unit_price)+' за облигацию.':'Цена в рублях за одну бумагу.');
 text('liquidityDetails',d.liquidity_text||'Спред и глубина рынка не подтверждены.');
 if(changedContext)$('fees').open=!s.fee_known&&s.quantity>0;
 if(d.state&&s.seq>d.state.seq&&s.seq!==d.rejected_seq)timer=setTimeout(()=>send(),250);
 render();text('syncStatus',d.notice||(d.state?.seq===s.seq?'Проверено для снимка ':'Проверяю параметры · снимок ')+String(d.revision).slice(0,8));
 const observer=new ResizeObserver(()=>{for(const id of ['stressChart','modelChart']){const e=$(id);if(e.data&&e.isConnected&&e.getClientRects().length&&e.offsetParent!==null)globalThis.__MOEXPlotly?.Plots.resize(e).catch(()=>{});}});observer.observe(root);
 let cleaned=false;
 const cleanup=()=>{if(cleaned)return;cleaned=true;abort.abort();clearTimeout(timer);observer.disconnect();queueMicrotask(()=>{if(!root.isConnected)for(const id of ['stressChart','modelChart']){const e=$(id);if(e?.data)globalThis.__MOEXPlotly?.purge(e);}});};
 root.__cleanupRender=cleanup;return cleanup;
}
