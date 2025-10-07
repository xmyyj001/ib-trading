import asyncio
from ib_insync import MarketOrder
from intents.intent import Intent

class CloseAll(Intent):
    """Closes all open positions and cancels all open orders."""

    async def _core_async(self):
        # 1. Cancel all open orders first to prevent new trades
        self._env.logging.warning("Cancelling all open orders...")
        open_orders = await self._env.ibgw.reqOpenOrdersAsync()
        for order in open_orders:
            await self._env.ibgw.cancelOrderAsync(order)
        
        # Give IB a moment to process cancellations if there were any
        if open_orders:
            await asyncio.sleep(2)

        # 2. Get all current positions from the broker (the ground truth)
        self._env.logging.warning("Closing all positions...")
        positions = await self._env.ibgw.reqPositionsAsync()
        if not positions:
            self._env.logging.info("No positions to close.")
            return {"status": "No positions to close."}

        closing_orders = []
        for p in positions:
            # Create an opposite order to close the position
            if p.position == 0:
                continue
            
            action = 'SELL' if p.position > 0 else 'BUY'
            quantity = abs(p.position)
            
            order = MarketOrder(action, quantity)
            
            # Use the correct ASYNC version of the placeOrder function
            trade = await self._env.ibgw.placeOrderAsync(p.contract, order)
            
            closing_orders.append({
                'symbol': p.contract.localSymbol,
                'action': action,
                'quantity': quantity,
                'orderId': trade.order.orderId
            })
            self._env.logging.info(f"Placed closing order for {quantity} of {p.contract.localSymbol}")

        self._activity_log.update(closing_orders=closing_orders)
        return {"status": "Close-all process initiated.", "closing_orders": closing_orders}
