import pandas as pd
from ib_insync import Stock, LimitOrder, util
from intents.intent import Intent
from lib.trading import Stock as StockInstrument, Trade
import asyncio

class TestSignalGenerator(Intent):
    """
    An observation strategy that uses high-frequency (30-min) real market data
    to increase the probability of generating a trade signal for monitoring purposes.
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self.id = self.__class__.__name__.lower()
        self._dry_run = kwargs.get('dryRun', False)

    async def _core_async(self):
        self._env.logging.info("--- Starting Target-Based Signal Generator ---")

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

        # --- Phase 4: Target-Based Position Sizing ---
        self._env.logging.info("Fetching account and position data...")
        account_values = self._env.ibgw.accountValues()
        portfolio = self._env.ibgw.portfolio()

        # 1. Get Net Liquidation
        net_liquidation_str = next((v.value for v in account_values if v.tag == 'NetLiquidation' and v.currency == 'USD'), '0')
        net_liquidation = float(net_liquidation_str)
        if net_liquidation == 0:
            self._env.logging.error("Net Liquidation is zero. Cannot proceed.")
            return {"status": "Net Liquidation is zero."}

        # 2. Get Current Position
        current_quantity = 0
        for item in portfolio:
            if item.contract.conId == spy_instrument.contract.conId:
                current_quantity = item.position
                break
        self._env.logging.info(f"Current SPY Position: {current_quantity}")

        # 3. Calculate Target Position
        overall_exposure_pct = self._env.config['exposure']['overall']
        strategy_weight_pct = self._env.config['exposure']['strategies'].get(self.id, 0)
        target_exposure = net_liquidation * overall_exposure_pct * strategy_weight_pct
        target_quantity = int(target_exposure * signal_weight / last_price)
        self._env.logging.info(f"Target SPY Position: {target_quantity}")

        # 4. Calculate Delta to Trade
        quantity_to_trade = target_quantity - current_quantity
        self._env.logging.info(f"Calculated Delta to Trade: {quantity_to_trade}")

        if quantity_to_trade == 0:
            self._env.logging.info("Target position already met. No trade needed.")
            return {"status": "Target position already met."}

        # --- Phase 5: Margin-Aware Order Placement ---
        action = 'BUY' if quantity_to_trade > 0 else 'SELL'
        order_quantity = abs(quantity_to_trade)

        # Margin check logic remains the same, but now applied to the delta
        safe_quantity = order_quantity
        while safe_quantity > 0:
            simulated_order = LimitOrder(action=action, totalQuantity=safe_quantity, lmtPrice=last_price)
            self._env.logging.info(f"Checking margin for quantity: {safe_quantity} ({action})")
            what_if_state = await self._env.ibgw.whatIfOrderAsync(spy_instrument.contract, simulated_order)
            
            post_trade_ewl_str = what_if_state.equityWithLoanChange
            post_trade_init_margin_str = what_if_state.initMarginChange

            try:
                post_trade_ewl = float(post_trade_ewl_str.split(' ')[0]) if post_trade_ewl_str else 0.0
                post_trade_init_margin = float(post_trade_init_margin_str.split(' ')[0]) if post_trade_init_margin_str else 0.0
            except (ValueError, AttributeError):
                self._env.logging.error("Could not parse margin values. Aborting trade.")
                return {"status": "Failed to parse margin values."}

            if post_trade_ewl >= post_trade_init_margin:
                self._env.logging.info(f"Margin check passed for quantity {safe_quantity}.")
                break
            else:
                margin_deficit = post_trade_init_margin - post_trade_ewl
                self._env.logging.warning(f"Margin deficit of ${margin_deficit:.2f} detected. Reducing size...")
                reduction_factor = (post_trade_ewl / post_trade_init_margin) * 0.95
                safe_quantity = int(safe_quantity * reduction_factor)
        else:
            self._env.logging.error("Failed to find a safe quantity that meets margin requirements.")
            return {"status": "Margin check failed."}

        if safe_quantity == 0:
            self._env.logging.info("Final safe quantity is 0. No order will be placed.")
            return {"status": "Safe quantity is zero."}

        # --- Phase 6: Execute Trade ---
        final_order = LimitOrder(action=action, totalQuantity=safe_quantity, lmtPrice=last_price)
        if not self._dry_run:
            trade = self._env.ibgw.placeOrder(spy_instrument.contract, final_order)
            await asyncio.sleep(1) # Allow time for order status to update
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
