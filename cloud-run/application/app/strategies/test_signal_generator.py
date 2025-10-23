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
        # 关键修复 1: 确保 id 属性存在
        self.id = self.__class__.__name__.lower()
        self._dry_run = kwargs.get('dryRun', False)

    async def _core_async(self):
        self._env.logging.info("--- Starting High-Frequency Observation Intent ---")

        # --- Phase 1: Contract Qualification ---
        try:
            spy_obj = Stock('SPY', 'SMART', 'USD')
            vixy_obj = Stock('VIXY', 'BATS', 'USD')
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(spy_obj, vixy_obj)
            spy_instrument = StockInstrument(self._env, ib_contract=qualified_contracts[0])
        except Exception as e:
            self._env.logging.error(f"FAILED at contract qualification. Error: {e}")
            raise e

        # --- Phase 2: Fetch REAL High-Frequency Market Data ---
        self._env.logging.info("Fetching 5D/30min historical data for SPY...")
        bars = await self._env.ibgw.reqHistoricalDataAsync(
            spy_instrument.contract, endDateTime='', durationStr='5 D',
            barSizeSetting='30 mins', whatToShow='TRADES', useRTH=True)
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

        # --- Phase 4: Margin-Aware Order Sizing & Placement ---
        if not signals:
            self._env.logging.info("Signal dictionary is empty. No trades to place.")
            return {"status": "No signals available to generate trades."}

        # 1. 获取关键账户指标
        self._env.logging.info("Fetching key account values for margin check...")
        account_summary = await self._env.ibgw.reqAccountSummaryAsync()
        
        # --- BUG FIX: Correctly parse account summary by iterating and filtering for USD currency ---
        net_liquidation_str = next((v.value for v in account_summary if v.tag == 'NetLiquidation' and v.currency == 'USD'), '0')
        excess_liquidity_str = next((v.value for v in account_summary if v.tag == 'ExcessLiquidity' and v.currency == 'USD'), '0')

        try:
            net_liquidation = float(net_liquidation_str)
            excess_liquidity = float(excess_liquidity_str)
        except (ValueError, TypeError):
            self._env.logging.error("Could not convert account values to float.")
            return {"status": "Invalid account values."}
        if net_liquidation == 0:
            self._env.logging.error("Net Liquidation is zero. Cannot proceed.")
            return {"status": "Net Liquidation is zero."}

        self._env.logging.info(f"Pre-trade Net Liquidation: {net_liquidation}, Excess Liquidity: {excess_liquidity}")

        # 2. 计算初始理想头寸
        overall_exposure_pct = self._env.config['exposure']['overall']
        strategy_weight_pct = self._env.config['exposure']['strategies'].get(self.id, 0)
        target_exposure = net_liquidation * overall_exposure_pct * strategy_weight_pct
        
        conId, (weight, price) = next(iter(signals.items()))
        initial_quantity = int(target_exposure * weight / price)

        self._env.logging.info(f"Initial desired quantity: {initial_quantity} for exposure ${target_exposure:.2f}")

        # 3. 保证金检查与头寸调整循环
        safe_quantity = initial_quantity
        
        # 创建一个模拟订单
        action = 'BUY' if weight > 0 else 'SELL'
        contract = spy_instrument.contract
        
        while abs(safe_quantity) > 0:
            simulated_order = LimitOrder(action=action, totalQuantity=abs(safe_quantity), lmtPrice=price)
            
            self._env.logging.info(f"Checking margin for quantity: {safe_quantity}")
            
            # 使用 whatIfOrder 检查保证金影响
            what_if_state = await self._env.ibgw.whatIfOrderAsync(contract, simulated_order)
            
            post_trade_ewl = float(what_if_state.equityWithLoan)
            post_trade_init_margin = float(what_if_state.initMargin)

            self._env.logging.info(f"Simulated Post-Trade -> EquityWithLoan: {post_trade_ewl:.2f}, InitMargin: {post_trade_init_margin:.2f}")

            if post_trade_ewl >= post_trade_init_margin:
                self._env.logging.info(f"Margin check passed for quantity {safe_quantity}. Finalizing trade.")
                break # 安全数量已找到
            else:
                margin_deficit = post_trade_init_margin - post_trade_ewl
                self._env.logging.warning(
                    f"Margin deficit of ${margin_deficit:.2f} detected for quantity {safe_quantity}. Reducing size..."
                )
                # 按比例缩减, 增加一个安全缓冲 (e.g., 5%)
                reduction_factor = (post_trade_ewl / post_trade_init_margin) * 0.95 
                safe_quantity = int(safe_quantity * reduction_factor)
        else:
            self._env.logging.error("Failed to find a safe quantity that meets margin requirements. No order will be placed.")
            return {"status": "Margin check failed, could not determine safe quantity."}

        # 4. 使用安全的数量执行交易
        if safe_quantity == 0:
            self._env.logging.info("Final safe quantity is 0. No order will be placed.")
            return {"status": "Safe quantity is zero, no trade placed."}

        # 更新信号字典以反映安全的数量
        self._signals = {conId: (weight, price, safe_quantity)}
        self._contracts = {conId: spy_instrument}

        # 创建交易对象并执行
        trade_obj = Trade(self._env, [self])
        trade_obj.consolidate_trades() # 这会使用 self._signals 中包含的数量

        if not trade_obj.trades:
            self._env.logging.warning("Consolidated trades are empty. No orders will be placed.")
            return {"status": "No trades after consolidation."}

        if not self._dry_run:
            order_params = {'lmtPrice': price}
            # 注意：place_orders_async 需要能处理从 consolidate_trades 传递过来的具体数量
            orders = await trade_obj.place_orders_async(LimitOrder, order_params=order_params)
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
        
        return self._activity_log
