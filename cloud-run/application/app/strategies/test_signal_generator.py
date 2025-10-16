import pandas as pd
from ib_insync import Stock, LimitOrder, util
from intents.intent import Intent
from lib.trading import Stock as StockInstrument, Trade

class TestSignalGenerator(Intent):
    """
    An observation strategy that uses high-frequency (30-min) real market data
    to increase the probability of generating a trade signal for monitoring purposes.
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self._dry_run = False

    async def _core_async(self):
        self._env.logging.info("--- Starting High-Frequency Observation Intent ---")

        # --- Phase 1: Contract Qualification ---
        try:
            spy_obj = Stock('SPY', 'SMART', 'USD')
            vixy_obj = Stock('VIXY', 'BATS', 'USD')
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(spy_obj, vixy_obj)
            spy_instrument = StockInstrument(self._env, ib_contract=qualified_contracts[0])
            vixy_instrument = StockInstrument(self._env, ib_contract=qualified_contracts[1])
            if not spy_instrument.contract.conId:
                raise ValueError("SPY contract qualification failed.")
        except Exception as e:
            self._env.logging.error(f"FAILED at contract qualification. Error: {e}")
            raise e

        # --- Phase 2: Fetch REAL High-Frequency Market Data ---
        self._env.logging.info("Fetching 5D/30min historical data for SPY...")
        bars = await self._env.ibgw.reqHistoricalDataAsync(
            spy_instrument.contract,
            endDateTime='',
            durationStr='5 D',
            barSizeSetting='30 mins',
            whatToShow='TRADES',
            useRTH=True
        )
        if not bars:
            return {"status": "Could not fetch market data."}
        
        df = util.df(bars)
        if df.empty:
            return {"status": "Market data is empty."}

        # --- Phase 3: Calculate MACD & Generate Signal ---
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        last_price = df.iloc[-1]['close']
        self._env.logging.info(f"[Data Check] Last MACD: {macd.iloc[-1]:.4f}, Last Signal: {signal.iloc[-1]:.4f}")

        signals = {}
        if macd.iloc[-1] > signal.iloc[-1]:
            self._env.logging.info(f"Bullish signal detected at {last_price}.")
            signals = {spy_instrument.contract.conId: (1.0, last_price)}
        elif macd.iloc[-1] < signal.iloc[-1]:
            self._env.logging.info(f"Bearish signal detected at {last_price}.")
            signals = {spy_instrument.contract.conId: (-1.0, last_price)}
        else:
            self._env.logging.info("No signal detected.")
            return {"status": "No signal generated."}

        # --- Phase 4: Place Order ---
        if not signals:
            self._env.logging.info("Signal dictionary is empty. No trades to place.")
            return {"status": "No signals available to generate trades."}

        # 1. 让意图自身拥有 trades 和 contracts 属性，模拟一个策略对象
        self.trades = {
            conId: int(weight * 10)
            for conId, (weight, price) in signals.items()
        }
        self.contracts = {
            conId: spy_instrument.contract
            for conId in signals.keys()
        }

        # 2. 将自身作为策略传入 Trade 对象，并调用 consolidate_trades
        trade_obj = Trade(self._env, [self])
        trade_obj.consolidate_trades()

        # 检查 consolidate_trades 的结果
        if not trade_obj.trades:
            self._env.logging.warning("Consolidated trades are empty. No orders will be placed.")
            return {"status": "No trades after consolidation."}

        if not self._dry_run:
            order_params = {'lmtPrice': last_price}
            orders = await trade_obj.place_orders_async(LimitOrder, order_params=order_params)
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
        
        return self._activity_log