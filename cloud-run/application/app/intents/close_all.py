import asyncio
from ib_insync import MarketOrder, Contract, Position
from intents.intent import Intent

class CloseAll(Intent):
    """
    Closes positions and cancels open orders.
    Can be configured to close all account positions, or only those for specific strategies.
    Supports dryRun mode.
    """
    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)
        self._dry_run = kwargs.get('dryRun', False)
        self._strategies_to_close = kwargs.get('strategies', [])
        self._activity_log.update(dryRun=self._dry_run, strategies=self._strategies_to_close)

    async def _core_async(self):
        # 1. 取消所有挂单 (这仍然是一个全局操作，是安全的)
        self._env.logging.warning("Cancelling all open orders...")
        if not self._dry_run:
            open_orders = await self._env.ibgw.reqOpenOrdersAsync()
            for order in open_orders:
                await self._env.ibgw.cancelOrderAsync(order)
            if open_orders:
                await asyncio.sleep(2)
                self._env.logging.info(f"{len(open_orders)} open orders cancelled.")

        # 2. 根据参数决定是清空全部还是部分
        positions_to_close = []
        if self._strategies_to_close:
            # --- 精确清仓逻辑 ---
            self._env.logging.warning(f"Closing positions for specified strategies: {self._strategies_to_close}")
            positions_to_close = await self._get_positions_for_strategies(self._strategies_to_close)
        else:
            # --- 一键清仓逻辑 ---
            self._env.logging.warning("Closing ALL positions for the account...")
            positions_to_close = await self._env.ibgw.reqPositionsAsync()

        if not positions_to_close:
            self._env.logging.info("No positions to close.")
            return {"status": "No positions to close."}

        # 3. 生成平仓计划
        closing_plan = []
        for p in positions_to_close:
            if p.position == 0: continue
            action = 'SELL' if p.position > 0 else 'BUY'
            quantity = abs(p.position)
            closing_plan.append({
                'symbol': p.contract.localSymbol, 'action': action, 'quantity': quantity
            })
        self._activity_log.update(closing_plan=closing_plan)

        # 4. 如果不是 dryRun，则执行下单
        if not self._dry_run:
            self._env.logging.info("Executing closing orders...")
            executed_orders = []
            for p in positions_to_close:
                 if p.position == 0: continue
                 action = 'SELL' if p.position > 0 else 'BUY'
                 quantity = abs(p.position)
                 order = MarketOrder(action, quantity)
                 trade = await self._env.ibgw.placeOrderAsync(p.contract, order)
                 executed_orders.append({'symbol': p.contract.localSymbol, 'orderId': trade.order.orderId, 'status': trade.orderStatus.status})
            self._activity_log.update(executed_orders=executed_orders)
        
        return self._activity_log

    async def _get_positions_for_strategies(self, strategy_ids: list) -> list:
        """
        从 Firestore 读取指定策略的持仓，并将其转换为 ib_insync 的 Position 对象列表。
        """
        positions_to_return = []
        holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
        
        for strategy_id in strategy_ids:
            doc_ref = holdings_ref.document(strategy_id)
            doc = await doc_ref.get()
            if not doc.exists:
                self._env.logging.warning(f"No holdings found in Firestore for strategy: {strategy_id}")
                continue

            holdings = doc.to_dict()
            for conId_str, quantity in holdings.items():
                # 创建一个临时的 Position 对象，以便后续代码可以统一处理
                pos = Position(
                    account=self._env.config['account'],
                    contract=Contract(conId=int(conId_str)),
                    position=float(quantity)
                )
                # 我们需要获取完整的合约信息才能下单
                await self._env.ibgw.qualifyContractsAsync(pos.contract)
                positions_to_return.append(pos)
                
        return positions_to_return