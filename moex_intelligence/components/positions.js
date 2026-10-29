export default function({data:d,parentElement,setStateValue,setTriggerValue}){
 const root=parentElement.querySelector('.positions-view'),body=root.querySelector('#positionsRows');
 root.__cleanupRender?.();
 const ctx=d.context;if(root.__context!==ctx){root.__context=ctx;root.__selected=d.selected;root.__seq=d.seq||0;root.__sort='';root.__direction=1;}
 if((d.seq||0)>root.__seq){root.__seq=d.seq;root.__selected=d.selected;}
 const abort=new AbortController(),signal=abort.signal;
 function choose(symbol){root.__selected=symbol;root.__seq++;draw();setStateValue('selection',{symbol,seq:root.__seq,context:ctx});}
 function draw(){
  root.querySelector('#selectedPosition').textContent='Выбрана: '+root.__selected;
  const rows=[...d.rows];if(root.__sort)rows.sort((a,b)=>{let x=a.sort[root.__sort],y=b.sort[root.__sort];if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return root.__direction*(typeof x==='number'?x-y:String(x).localeCompare(String(y),'ru'));});
  body.replaceChildren();
  rows.forEach(row=>{
   const tr=document.createElement('tr');tr.dataset.symbol=row.symbol;tr.tabIndex=0;tr.setAttribute('aria-selected',root.__selected===row.symbol);tr.setAttribute('aria-label',row.name+' '+row.symbol);
   const asset=document.createElement('td'),name=document.createElement('span'),ticker=document.createElement('span');name.className='name';ticker.className='ticker';name.textContent=row.name;name.title=row.name;ticker.textContent=row.symbol;asset.append(name,ticker);tr.append(asset);
   [['quantity','Количество'],['price','Цена'],['value','Стоимость'],['weight','Доля'],['pnl','Результат']].forEach(([key,label])=>{let td=document.createElement('td'),l=document.createElement('span'),v=document.createElement('span');l.className='cell-label';l.textContent=label;v.className='cell-value';v.textContent=row.display[key];td.append(l,v);tr.append(td);});
   const actions=document.createElement('td');actions.className='mobile-actions';[['evaluate','Оценить'],['existing','Сценарии'],['buy','Моделировать']].forEach(([kind,label])=>{let b=document.createElement('button');b.textContent=label;b.addEventListener('click',e=>{e.stopPropagation();setTriggerValue('action',{symbol:row.symbol,kind,context:ctx});});actions.append(b)});tr.append(actions);
   tr.addEventListener('click',()=>choose(row.symbol));tr.addEventListener('keydown',e=>{if(e.target!==tr)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(row.symbol);body.querySelector('[data-symbol="'+row.symbol+'"]').focus();}else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();let next=e.key==='ArrowDown'?tr.nextElementSibling:tr.previousElementSibling;next?.focus();}});
   body.append(tr);
  });
  root.querySelectorAll('[data-sort]').forEach(b=>{const active=b.dataset.sort===root.__sort;b.parentElement.setAttribute('aria-sort',active?(root.__direction===1?'ascending':'descending'):'none');});
 }
 root.querySelectorAll('[data-sort]').forEach(b=>b.addEventListener('click',()=>{root.__direction=root.__sort===b.dataset.sort?-root.__direction:1;root.__sort=b.dataset.sort;draw();},{signal}));
 draw();const cleanup=()=>abort.abort();root.__cleanupRender=cleanup;return cleanup;
}
