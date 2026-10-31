#!/usr/bin/env node
// Pure chart update-plan contract. Synthetic data only; no Bybit or orders.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const src=fs.readFileSync(path.join(__dirname,'../moex_intelligence/components/trade.js'),'utf8')
 .replace('export default function(component){','function render(component){');
const context={LightweightCharts:{}};
vm.runInNewContext(src+'\nglobalThis.__plan=candleChangePlan;',context,{timeout:2500});
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

// This catches O(n^2) marker filtering regressions in source: index candles once.
assert.match(src,/const candleTimes=new Set\(d\.candles\.map\(/);
assert.match(src,/r\.signalsByTime=new Map\(\)/);
assert.doesNotMatch(src,/d\.candles\.some\(c=>c\.time===s\.timestamp\)/);
assert.doesNotMatch(src,/r\.data\?\.signals\.filter\(s=>s\.timestamp===p\.time\)/);

console.log('PASS: chart update-plan, immutable-history fallback, volume correction and indexed signal contract');
