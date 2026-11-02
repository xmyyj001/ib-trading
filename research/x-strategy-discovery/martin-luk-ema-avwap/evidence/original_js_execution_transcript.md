# Original JavaScript experiment — tool-call text recovery

**Purpose:** preserve the historical invocation text as evidence. **Do not execute.** This document is not an additional run, revised model, or evidence of successful reproduction.

## Provenance and limitations
- Source: the previous ChatGPT conversation's `functions.exec` tool-call body that generated the original `preliminary_results.json` (commit `38d20262c6259b19fc07c075ae08a6e5e13cf408`). This is a transcription of the tool-call text accessible in this conversation, **not** a file or full V8 execution trace captured at the time; byte-for-byte fidelity has not been separately attested.
- Invocation: `functions.exec` with a raw ECMAScript module body. It used top-level `await`, `Promise.all`, `tools.mcp__Interactive_Brokers__IBKR___get_price_history`, `text(...)`, then `tools.mcp__GitHub__create_file`.
- Runtime: the `functions.exec` isolated V8 JavaScript environment described by the host (fresh isolate per call). Exact V8 version, process ID, runtime build, seed, wall-clock start/end time and resource counters: **UNKNOWN**.
- The script used in-memory provider responses and did not save its original input arrays. No machine-readable execution log or original input checksum was produced.
- Execution date: 2026-11-02 (from original output field `research_date`). Exact invocation timestamp: **UNKNOWN**. Result file was committed 2026-11-02T14:35:57Z, providing an **upper bound**, not an execution time. Its previous Python file commit time was 2026-11-02T14:34:48Z.
- GitHub reference: https://github.com/xmyyj001/ib-trading/commit/38d20262c6259b19fc07c075ae08a6e5e13cf408
- The last `create_file` step is part of the historical call; **not** a request to re-execute it.

## Complete prior tool-call body, transcribed

```javascript
const ss=[["GOOG",208813720],["NVDA",4815747],["TSLA",76792991],["AMD",4391],["META",107113386],["PLTR",444857009]];
const fetched=await Promise.all(ss.flatMap(([ticker,id])=>[tools.mcp__Interactive_Brokers__IBKR___get_price_history({contract_id:id,security_type:"STK",period:"ONE_YEAR",step:"ONE_DAY",outside_rth:false}),tools.mcp__Interactive_Brokers__IBKR___get_price_history({contract_id:id,security_type:"STK",period:"ONE_MONTH",step:"FIFTEEN_MINS",outside_rth:false})]));
function ema(a,n){let v=0;return a.map((x,i)=>v=i?x*2/(n+1)+v*(n-1)/(n+1):x)}
const trades=[],coverage=[];
for(let p=0;p<ss.length;p++){
const [ticker,conid]=ss[p],d=fetched[2*p],q=fetched[2*p+1];if(!d.close?.length||!q.close?.length)continue;
const d50=ema(d.close,50),d150=ema(d.close,150),q21=ema(q.close,21);
const dayIndex=new Map(d.time.map((x,i)=>[x.slice(0,10),i]));const dated=d.time.map(x=>x.slice(0,10));
const trueR=[],atr=[];
for(let i=0;i<q.close.length;i++){let pv=i?q.close[i-1]:q.close[i],t=Math.max(q.high[i]-q.low[i],Math.abs(q.high[i]-pv),Math.abs(q.low[i]-pv));trueR.push(t);let b=trueR.slice(Math.max(0,i-13),i+1);atr.push(b.reduce((a,b)=>a+b,0)/b.length)}
const counts=new Map();
for(let i=45;i<q.close.length-1;i++){
 const day=q.time[i].slice(0,10);counts.set(day,(counts.get(day)||0)+1);
 const prior=dated.filter(s=>s<day);if(!prior.length)continue;const last=prior.at(-1), j=dayIndex.get(last);
 if(counts.get(day)>14||j<150||!(d.close[j]>d50[j]&&d50[j]>d150[j])||q.time[i+1].slice(0,10)!==day)continue;
 const h=Math.max(...q.high.slice(i-26,i));
 if(h-Math.min(...q.low.slice(i-8,i))<0.01*h)continue;
 if(q.close[i]<=Math.max(...q.high.slice(i-4,i)))continue;
 const em= Math.min(...q.low.slice(i-5,i+1])<=1.005*q21[i-1]&&q.close[i]>q21[i];
 const start=Math.max(0,i-40),stop=i-3;
 let anchor=start;for(let k=start+1;k<stop;k++)if(q.high[k]>q.high[anchor])anchor=k;
 let num=0,den=0;for(let k=anchor;k<i;k++){num+=q.close[k]*q.volume[k];den+=q.volume[k]}
 const av=den?num/den:NaN,avec=Math.min(...q.low.slice(i-5,i+1))<=1.005*av&&q.close[i]>=av;
 const entry=i+1,raw=q.open[entry],risk=atr[i];if(risk<=0)continue;
 for(let [model,accepted] of [["M0",true],["M1",em],["M2",em&&avec]]){
 if(!accepted||trades.some(x=>x.symbol===ticker&&x.date===day&&x.model===model))continue;
 let out=raw,reason="eod";for(let k=entry;k<Math.min(entry+8,q.close.length);k++){if(q.time[k].slice(0,10)!==day)break;out=q.close[k];if(q.low[k]<=raw-risk){out=raw-risk;reason="stop";break}if(q.high[k]>=raw+1.5*risk){out=raw+1.5*risk;reason="target";break}}
 trades.push({symbol:ticker,date:day,model,entry_utc:q.time[entry],gross_return:(out/raw-1),net_return:(out/raw-1)-.0014,reason});
 }
}
coverage.push({ticker,contract_id:conid,daily_bars:d.close.length,intraday_bars:q.close.length,daily_start:d.time[0],daily_end:d.time.at(-1),intraday_start:q.time[0],intraday_end:q.time.at(-1),supplier:d.source??null})
}
const summary={};for(const model of ["M0","M1","M2"]){const ts=trades.filter(x=>x.model===model),vals=ts.map(t=>t.net_return).sort((a,b)=>a-b),pc=ts.length?Object.fromEntries([...new Set(ts.map(x=>x.symbol))].map(s=>[s,ts.filter(x=>x.symbol===s).length])):{};summary[model]={trades:ts.length,symbols:pc};if(ts.length)Object.assign(summary[model],{mean_net_pct:+(100*vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(4),median_net_pct:+(100*vals[Math.floor(vals.length/2)]).toFixed(4),win_rate_pct:+(100*vals.filter(x=>x>0).length/vals.length).toFixed(2),first_date:ts.map(x=>x.date).sort()[0],last_date:ts.map(x=>x.date).sort().at(-1),positive_trades:vals.filter(x=>x>0).length})}
const res={study:"Martin Luk inspired EMA+AVWAP exploratory",execution:"JS run paralleling Python prototype logic",research_date:"2026-11-02",coverage,results:summary,trades:trades.map(x=>({...x,net_return:+x.net_return.toFixed(8),gross_return:+x.gross_return.toFixed(8)})),limitations:["Exploratory, not statistically validated or out-of-sample","Only 6 current-survivor tickers","~1 month 15-minute data, no multi-market regime sample","Fixed 7bp/side cost proxy; unverified true fills","No raw IBKR quote/bar redistribution in public repository","Data provider may revise bars; run timestamp not assured","Causal daily trend and anchor are independently chosen hypotheses","No annualized return or Sharpe claims"]};
text(JSON.stringify({coverage,summary,example_trades:trades.slice(0,6),total_trades:trades.length}));
const repo="xmyyj001/ib-trading",branch="research/martin-luk-chatgpt-20261102",base="research/x-strategy-discovery/martin-luk-ema-avwap/";
let file=await tools.mcp__GitHub__create_file({repository_full_name:repo,path:base+"preliminary_results.json",content:JSON.stringify(res,null,2)+"\n",message:"research: record exploratory IBKR M0 M1 M2 results with caveats",branch});text(JSON.stringify({saved:"preliminary_results.json",commit:file.result.commit_sha}));
```

## Source integrity notice
The prior tool-call source was not published as a standalone file during execution. This document is the recoverable **conversation-level text**, not authenticated historical executable bytes. In particular, this transcription must never be used to assert exact replay parity. **NOT_REPRODUCED**.
