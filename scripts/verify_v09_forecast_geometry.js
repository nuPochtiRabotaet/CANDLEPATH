#!/usr/bin/env node
// Pure forecast geometry contract check. No browser, credentials, network or trades.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../moex_intelligence/components/trade.js'),'utf8')
  .replace('export default function(component){','function render(component){');
const ctx={LightweightCharts:{}};
vm.runInNewContext(source+'\nglobalThis.__project=forecastProjection;',ctx,{timeout:2500});
const project=ctx.__project;

function sample(interval='15'){
 const seconds=interval==='D'?86400:Number(interval)*60;
 const start=1800000000-Math.floor(1800000000/seconds)*seconds + Math.floor(1800000000/seconds)*seconds;
 const anchor=start-seconds;
 const candles=[{time:anchor-seconds,close:101,closed:true},{time:anchor,close:100,closed:true}];
 return {symbol:'BTCUSDT',interval,candles,
   readiness:{forecast_feed_ready:true,candle_data_fresh:true},
   intelligence:{forecast:{
     status:'EXPERIMENTAL',symbol:'BTCUSDT',timeframe:interval,data_as_of:start,
     points:[1,2,4,8].map(h=>({target_time:start+h*seconds,
       lower:String(100-h),median:'100',upper:String(100+h)}))
   }}};
}
const copy=o=>JSON.parse(JSON.stringify(o));
let checked=0;
const valid=project(sample());
assert.ok(valid);
assert.deepEqual(Array.from(valid.line,p=>p.time),[0,1,2,4,8].map(h=>1800000000+h*900));checked++;
assert.deepEqual(Array.from(valid.grid,p=>p.time),Array.from({length:8},(_,i)=>1800000000+(i+1)*900));checked++;
assert.deepEqual(Array.from(valid.profile,p=>p.median),[100,100,100,100,100]);checked++;
assert.equal(valid.profile[0].time,sample().candles.at(-1).time+900);checked++;
for(const interval of ['1','5','15','30','60','240','D']){
 const fixture=sample(interval),result=project(fixture),step=interval==='D'?86400:+interval*60;
 assert.ok(result,interval);
 assert.deepEqual(Array.from(result.line,p=>p.time),
   [0,1,2,4,8].map(h=>fixture.intelligence.forecast.data_as_of+h*step));
 checked++;
}
const trailing=sample();
trailing.candles.push({time:trailing.intelligence.forecast.data_as_of,
                       close:999999,closed:false});
assert.deepEqual(Array.from(project(trailing).line,p=>p.time),
 Array.from(valid.line,p=>p.time));checked++;
const invalid=[
 d=>d.readiness.forecast_feed_ready=false,
 d=>d.readiness.candle_data_fresh=false,
 d=>d.intelligence.forecast.status='VALIDATED',
 d=>d.intelligence.forecast.symbol='ETHUSDT',
 d=>d.intelligence.forecast.timeframe='60',
 d=>d.intelligence.forecast.data_as_of-=900,
 d=>d.intelligence.forecast.points[0].lower='101',
 d=>d.intelligence.forecast.points[0].upper='99',
 d=>d.intelligence.forecast.points[0].median='-1',
 d=>d.intelligence.forecast.points[0].lower='Infinity',
 d=>d.intelligence.forecast.points[0].median='',
 d=>d.intelligence.forecast.points[1].target_time=d.intelligence.forecast.points[0].target_time,
 d=>d.intelligence.forecast.points[2].target_time+=1,
 d=>d.intelligence.forecast.points[3].target_time+=900*100,
 d=>d.candles=[],
 d=>d.candles.at(-1).close=0,
 d=>d.candles.at(-1).closed=false,
 d=>d.intelligence.forecast.points=[],
 d=>d.intelligence.forecast.points[0].lower='NaN',
];
for(const change of invalid){const d=copy(sample());change(d);assert.equal(project(d),null,'must hide malformed forecast');checked++;}
const empty=sample();delete empty.intelligence.forecast.data_as_of;
assert.equal(project(empty),null);checked++;
console.log('PASS: '+checked+' strict projection geometry and fail-closed checks (no live quotes)');
