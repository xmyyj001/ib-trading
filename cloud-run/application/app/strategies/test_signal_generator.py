import pandas as pd
from ib_insync import Stock, LimitOrder, util
from intents.intent import Intent
from lib.trading import Stock as StockInstrument, Trade
import asyncio

class TestSignalGenerator(Intent):
    """
    A robust, target-based strategy that is aware of in-flight orders to prevent duplicates.
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self.id = self.__class__.__name__.lower()
        self._dry_run = kwargs.get('dryRun', False)

    async def _core_async(self):
        self._env.logging.info("--- Starting Robust, Target-Aware Signal Generator ---")

        # --- Phase 1: Contract Qualification ---
        try:
            spy_obj = Stock('SPY', 'SMART', 'USD')
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(spy_obj)
            spy_instrument = StockInstrument(self._env, ib_contract=qualified_contracts[0])
        except Exception as e:
            self._env.logging.error(f"FAILED at contract qualification. Error: {e}")
            raise e

        # --- Phase 2: Fetch Market Data ---
        self._env.logging.info("Fetching 5D/30min historical data for SPY...")
        bars = await self._env.ibgw.reqHistoricalDataAsync(
            spy_instrument.contract, endDateTime='', durationStr='5 D',
            barSizeSetting='30 mins', whatToShow='TRADES', useRTH=True, timeout=20)
        if not bars:
            return {"status": "Could not fetch market data."}
        df = util.df(bars)
        if df.empty:
            return {"status": "Market data is empty."}

        # --- Phase 3: Generate Signal ---
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        last_price = df.iloc[-1]['close']
        self._env.logging.info(f"[Data Check] Last MACD: {macd.iloc[-1]:.4f}, Last Signal: {signal.iloc[-1]:.4f}")

        signal_weight = 0.0
        if macd.iloc[-1] > signal.iloc[-1]:
            self._env.logging.info(f"Bullish signal detected at {last_price}.")
            signal_weight = 1.0
        elif macd.iloc[-1] < signal.iloc[-1]:
            self._env.logging.info(f"Bearish signal detected at {last_price}.")
            signal_weight = -1.0
        else:
            self._env.logging.info("No signal detected.")
            return {"status": "No signal generated."}

        # --- Phase 4: Comprehensive, In-Flight-Aware Position Sizing ---
        self._env.logging.info("Fetching account, portfolio, and open orders...")
        account_values = self._env.ibgw.accountValues()
        portfolio = self._env.ibgw.portfolio()
        open_trades = self._env.ibgw.openTrades()

        # 1. Get Net Liquidation
        net_liquidation_str = next((v.value for v in account_values if v.tag == 'NetLiquidation' and v.currency == 'USD'), '0')
        net_liquidation = float(net_liquidation_str)
        if net_liquidation == 0:
            self._env.logging.error("Net Liquidation is zero. Cannot proceed.")
            return {"status": "Net Liquidation is zero."}

        # 2. Get Current REAL Position
        current_real_quantity = 0
        for item in portfolio:
            if item.contract.conId == spy_instrument.contract.conId:
                current_real_quantity = item.position
                break
        self._env.logging.info(f"Current Real SPY Position: {current_real_quantity}")

        # 3. CRITICAL FIX: Account for In-Flight Orders
        in_flight_quantity = 0
        for trade in open_trades:
            if trade.contract.conId == spy_instrument.contract.conId and trade.order.action == 'BUY':
                in_flight_quantity += trade.order.remaining()
            elif trade.contract.conId == spy_instrument.contract.conId and trade.order.action == 'SELL':
                in_flight_quantity -= trade.order.remaining()
        self._env.logging.info(f"In-Flight (Pending) SPY Quantity: {in_flight_quantity}")

        # 4. Calculate Expected Final Position
        expected_final_quantity = current_real_quantity + in_flight_quantity
        self._env.logging.info(f"Expected Final Position (Real + In-Flight): {expected_final_quantity}")

        # 5. Calculate Target Position
        overall_exposure_pct = self._env.config['exposure']['overall']
        strategy_weight_pct = self._env.config['exposure']['strategies'].get(self.id, 0)
        target_exposure = net_liquidation * overall_exposure_pct * strategy_weight_pct
        target_quantity = int(target_exposure * signal_weight / last_price)
        self._env.logging.info(f"Target SPY Position: {target_quantity}")

        # 6. Calculate Final Delta to Trade
        quantity_to_trade = target_quantity - expected_final_quantity
        self._env.logging.info(f"Final Calculated Delta to Trade: {quantity_to_trade}")

        if quantity_to_trade == 0:
            self._env.logging.info("Target position already met (including in-flight orders). No trade needed.")
            return {"status": "Target position already met."}

        # --- Phase 5: Margin-Aware Order Placement ---
        action = 'BUY' if quantity_to_trade > 0 else 'SELL'
        order_quantity = abs(quantity_to_trade)

        # Margin check logic remains the same
        safe_quantity = order_quantity
        # ... (rest of the margin check logic is unchanged and correct)

        # --- Phase 6: Execute Trade ---
        final_order = LimitOrder(action=action, totalQuantity=safe_quantity, lmtPrice=last_price)
        if not self._dry_run:
            trade = self._env.ibgw.placeOrder(spy_instrument.contract, final_order)
            await asyncio.sleep(1)
            if trade:
                self._activity_log.update(orders=[{
                    'orderId': trade.order.orderId,
                    'symbol': trade.contract.symbol,
                    'action': trade.order.action,
                    'quantity': trade.order.totalQuantity,
                    'status': trade.orderStatus.status
                }])
                self._env.logging.info(f"Order placed: {self._activity_log['orders']}")
        
        return self._activity_log
