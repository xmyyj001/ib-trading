# Read-only research prototype. Authoritative parameter assumptions: experiment_config.json
# Run: python prototype_backtest.py input_market_data.json
# Not a replication of Martin Luk; NOT a production trading model.
import json, sys, math, collections
def ema(vals,n):
    out=[]; last=None
    for x in vals:
        last=x if last is None else (2/(n+1))*x+(1-2/(n+1))*last
        out.append(last)
    return out
def run(data):
    trades=[]
    for item in data:
        symbol=item['ticker']; d=item['daily']; q=item['intra']
        dema50=ema(d['close'],50); dema150=ema(d['close'],150)
        daytrend={}
        for i,t in enumerate(d['time']):
            day=t[:10]
            # prior *completed* day filter
            daytrend[day]= bool(i>=151 and d['close'][i-1]>dema50[i-1]>dema150[i-1])
        # Advance trend via last prior completed session for days where daily not perfectly aligned
        dates=list(daytrend)
        sids=sorted(set(x[:10] for x in q['time']))
        for k,day in enumerate(sids):
            prevdays=[dd for dd in dates if dd<day]
            if prevdays:
                last=prevdays[-1];j=dates.index(last)
                daytrend[day]= bool(j>=150 and d['close'][j]>dema50[j]>dema150[j])
        e21=ema(q['close'],21)
        tr=[]; atr=[]
        for i in range(len(q['close'])):
            v=max(q['high'][i]-q['low'][i],abs(q['high'][i]-(q['close'][i-1] if i else q['close'][i])),abs(q['low'][i]-(q['close'][i-1] if i else q['close'][i])))
            tr.append(v);atr.append(sum(tr[max(0,i-13):i+1])/min(14,i+1))
        ords=collections.Counter()
        for i in range(45,len(q['close'])-1):
            day=q['time'][i][:10]; ords[day]+=1
            if ords[day]>14 or not daytrend.get(day,False) or q['time'][i+1][:10]!=day:continue
            if max(q['high'][i-26:i])-min(q['low'][i-8:i])<0.01*max(q['high'][i-26:i]):continue
            if not q['close'][i]>max(q['high'][i-4:i]):continue
            emaok=min(q['low'][i-5:i+1])<=1.005*e21[i-1] and q['close'][i]>e21[i]
            # Causal AVWAP anchor: highest completed high in 40 bars, exclude latest 3 bars
            start=max(0,i-40);stop=i-3
            anchor=max(range(start,stop),key=lambda k:q['high'][k])
            vs=sum(q['volume'][k] for k in range(anchor,i))
            av=sum(q['close'][k]*q['volume'][k] for k in range(anchor,i))/vs if vs else float('nan')
            avok=min(q['low'][i-5:i+1])<=1.005*av and q['close'][i]>=av
            entry=i+1
            raw=q['open'][entry]
            risk=atr[i]
            if risk<=0:continue
            # skip if previous signal yielded a trade for symbol/model/day
            for model,accepted in [('M0',True),('M1',emaok),('M2',emaok and avok)]:
                if not accepted:continue
                if any(t['symbol']==symbol and t['date']==day and t['model']==model for t in trades):continue
                stop=raw-risk;target=raw+1.5*risk;out=raw;reason='eod'
                for j in range(entry,min(entry+8,len(q['close']))):
                    if q['time'][j][:10]!=day:break
                    out=q['close'][j]
                    if q['low'][j]<=stop:out=stop;reason='stop';break
                    if q['high'][j]>=target:out=target;reason='target';break
                ret=(out/raw-1)
                trades.append(dict(symbol=symbol,date=day,model=model,entry_utc=q['time'][entry],net_return=ret-0.0014,gross_return=ret,reason=reason))
    summary={}
    for name in ('M0','M1','M2'):
        ts=[t for t in trades if t['model']==name]
        summ={'trades':len(ts),'symbols':dict(collections.Counter(t['symbol'] for t in ts))}
        if ts:
            vals=[t['net_return'] for t in ts]
            summ.update(mean_net_pct=round(100*sum(vals)/len(vals),4),win_rate_pct=round(100*sum(v>0 for v in vals)/len(vals),2),net_return_median_pct=round(100*sorted(vals)[len(vals)//2],4),first_date=min(t['date'] for t in ts),last_date=max(t['date'] for t in ts))
        summary[name]=summ
    return summary,trades
if __name__=='__main__':
    with open(sys.argv[1]) as f:data=json.load(f)
    summary,trades=run(data)
    print(json.dumps({'summary':summary,'trades':trades},indent=2))
