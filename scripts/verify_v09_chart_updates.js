#!/usr/bin/env node
// Pure chart update-plan contract. Synthetic data only; no Bybit or orders.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const src=fs.readFileSync(path.join(__dirname,'../moex_intelligence/components/trade.js'),'utf8')
 .replace('export default function(component){','function render(component){');
const context={LightweightCharts:{}};
vm.runInNewContext(src+'\nglobalThis.__plan=candleChangePlan;globalThis.__markers=markerPlan;globalThis.__tooltip=chartSignalTooltip;',context,{timeout:2500});
const plan=context.__plan;
const copy=x=>JSON.parse(JSON.stringify(x));
const bar=(t,price=100,volume=5,closed=true)=>({
 time:t,open:price,high:price+1,low:price-1,close:price,volume,closed
});
const old=[bar(900),bar(1800),bar(2700)];
const kind=(a,b)=>({mode:plan(a,b).mode,from:plan(a,b).from});

assert.deepEqual(kind([],old),{mode:'reset',from:0});
assert.deepEqual(kind(old,copy(old)),{mode:'same',from:3});
const revised=copy(old);revised[2].close=101;
assert.deepEqual(kind(old,revised),{mode:'tail',from:2});
const changedVolume=copy(old);changedVolume[2].volume=7;
assert.deepEqual(kind(old,changedVolume),{mode:'tail',from:2});
const finalized=copy(old);finalized[2].closed=false;
assert.deepEqual(kind(old,finalized),{mode:'tail',from:2});
assert.deepEqual(kind(old,[...copy(old),bar(3600)]),{mode:'tail',from:3});
assert.deepEqual(kind(old,[...copy(old.slice(0,2)),bar(2700,101),bar(3600)]),
 {mode:'tail',from:2});
const historical=copy(old);historical[1].close=105;
assert.deepEqual(kind(old,historical),{mode:'reset',from:0});
assert.deepEqual(kind(old,old.slice(0,2)),{mode:'reset',from:0});
assert.deepEqual(kind(old,[bar(1800),bar(2700),bar(3600)]),{mode:'reset',from:0});
assert.deepEqual(kind(old,[bar(900),bar(1800),bar(2600)]),{mode:'reset',from:0});
assert.deepEqual(kind(old,[...copy(old),bar(2700)]),{mode:'reset',from:0});
assert.deepEqual(kind(old,[]),{mode:'empty',from:0});

// Multiple strategies can signal the same candle/type; do not silently
// discard the first hypothesis or draw overlapping duplicate arrows.

const markerPlan=context.__markers;
const tooltip=context.__tooltip;
const minimal=tooltip({type:'BUY',timestamp:1800,strategy:'One'},
 t=>'T'+t,x=>String(x));
assert.match(minimal,/BUY · One/);
assert.match(minimal,/Фактически обнаружен нет данных/);
assert.match(minimal,/цена неизвестна/);
assert.doesNotMatch(minimal,/undefined|Invalid Date/);
const full=tooltip({type:'EXIT',timestamp:1800,detected_at:1810,
 reference_price:102.5,strategy:'Range',explanation:['cross below'],
 regime:'Bearish',status:'confirmed',parameters:{window:20},
 cost_assumption:'round trip estimated'},t=>'T'+t,x=>String(x));
assert.match(full,/Фактически обнаружен T1810/);
assert.match(full,/102.5 USDT/);
assert.match(full,/cross below/);
assert.match(full,/round trip estimated/);
assert.doesNotMatch(full,/undefined|Invalid Date/);
const candidates=[
 {id:'A',timestamp:1800,type:'BUY',strategy:'Trend Following'},
 {id:'B',timestamp:1800,type:'BUY',strategy:'Breakout Detection'},
 {id:'C',timestamp:1800,type:'EXIT',strategy:'Mean Reversion'},
 {id:'A',timestamp:1800,type:'BUY',strategy:'Trend Following'},
 {id:'D',timestamp:2700,type:'BUY',strategy:'Trend Following'},
 {id:'E',timestamp:1800,type:'SHORT',strategy:'Unsupported'},
 {id:'F',timestamp:3600,type:'EXIT',strategy:'Out of view'},
];
const sourceBefore=JSON.stringify(candidates);
const grouped=copy(markerPlan(candidates,new Set([1800,2700])));
assert.deepEqual(grouped.map(m=>({time:m.time,text:m.text,position:m.position})),[
 {time:1800,text:'BUY ×2',position:'belowBar'},
 {time:1800,text:'EXIT',position:'aboveBar'},
 {time:2700,text:'BUY',position:'belowBar'}
]);
assert.equal(JSON.stringify(candidates),sourceBefore);
assert.deepEqual(copy(markerPlan([
 {timestamp:1800,type:'BUY',strategy:'One'},
 {timestamp:1800,type:'BUY',strategy:'One'},
 {timestamp:1800,type:'BUY',strategy:'Two'}
],new Set([1800]))).map(m=>m.text),['BUY ×2']);
assert.deepEqual(copy(markerPlan(candidates,new Set())),[]);
assert.deepEqual(copy(markerPlan([null,undefined,{timestamp:1800,type:'SHORT',strategy:'Bad'}],new Set([1800]))),[]);

// This catches O(n^2) marker filtering regressions in source: index candles once.
assert.match(src,/const candleTimes=new Set\(d\.candles\.map\(/);
assert.match(src,/r\.signalsByTime=new Map\(\)/);
assert.match(src,/function markerPlan\(/);
assert.doesNotMatch(src,/d\.candles\.some\(c=>c\.time===s\.timestamp\)/);
assert.doesNotMatch(src,/r\.data\?\.signals\.filter\(s=>s\.timestamp===p\.time\)/);

console.log('PASS: chart update-plan, immutable-history fallback, volume correction and indexed signal contract');

// Intrabar rendering is sourced from the live lifecycle, never backdated.
vm.runInNewContext('globalThis.__chartSignals=chartSignals;',context);
const chartSignals=context.__chartSignals;
const early={id:'early',symbol:'BTCUSDT',timeframe:'15',candle_time:1800,
 timestamp:2700,type:'BUY',strategy:'Trend Following',state:'POTENTIAL',
 confirmed_at:null,potential_detected_at:1830.25,reference_price:101};
const data={symbol:'BTCUSDT',interval:'15',signals:[],candles:[bar(1800,101,5,false)],
 lifecycle:{records:[early]},readiness:{forecast_feed_ready:true},signal_timing:{received_at:1830}};
assert.equal(chartSignals(data,1831).length,1);
const preliminary=copy(markerPlan(chartSignals(data,1831),new Set([1800])));
assert.equal(preliminary[0].time,1800);
assert.equal(preliminary[0].text,'POTENTIAL BUY');
assert.match(preliminary[0].color,/rgba/);
for(const now of [1799,2700,1896])assert.equal(chartSignals(data,now).length,0);
assert.equal(chartSignals({...data,readiness:{forecast_feed_ready:false}},1831).length,0);
assert.equal(chartSignals({...data,symbol:'ETHUSDT'},1831).length,0);
assert.equal(chartSignals({...data,interval:'5'},1831).length,0);
for(const state of ['INVALIDATED','EXPIRED'])assert.equal(chartSignals({...data,lifecycle:{records:[{...early,state}]}},1831).length,0);
const confirmed={...early,status:'confirmed',state:'CONFIRMED',confirmed_at:2702.5,available_at:2702.5};
const history={...data,signals:[confirmed],lifecycle:{records:[confirmed]},candles:[bar(1800)]};
const solid=copy(markerPlan(chartSignals(history,2800),new Set([1800])));
assert.equal(solid[0].text,'BUY · close');
assert.notEqual(solid[0].color,preliminary[0].color);
assert.match(tooltip(early,t=>'T'+t,String),/Фактически обнаружен T1830.25/);
assert.match(tooltip(early,t=>'T'+t,String),/Предварительное условие может исчезнуть/);
assert.match(tooltip(confirmed,t=>'T'+t,String),/Подтверждён T2702.5/);
console.log('PASS: intrabar source candle, status styling, fractional timestamps, invalidation, freshness and context');
