from ib_insync import *
ib = IB()
ib.connect('127.0.0.1', 4002, clientId=999) # 使用一个新的clientId以避免冲突

spy_contract = Stock('SPY', 'SMART', 'USD')
ib.reqHeadTimeStamp(spy_contract, whatToShow='TRADES', useRTH=True)

bars = ib.reqHistoricalData(
    spy_contract,
    endDateTime='',
    durationStr='5 D',
    barSizeSetting='30 mins',
    whatToShow='TRADES',
    useRTH=True,
    timeout=20  # 等待20秒
)

print(f"Number of bars received: {len(bars)}")
if bars:
    print("Sample bar:", bars[0])
else:
    print("Failed to retrieve historical data.")

ib.disconnect()
