from datetime import datetime, timezone
from typing import Any, Dict, List

from ib_insync import util

from intents.intent import Intent


class Reconcile(Intent):
    """
    Synchronize live broker state (holdings, cash, open orders) into Firestore.
    Acts as the single source of truth for Commander decisions.
    """

    async def _core_async(self) -> Dict[str, Any]:
        self._env.logging.info("Starting portfolio reconciliation against IB Gateway...")
        snapshot_ts = datetime.now(timezone.utc).isoformat()

        positions = await self._env.ibgw.reqPositionsAsync()
        open_trades = self._env.ibgw.openTrades()
        account_values = self._env.ibgw.accountValues()

        holdings: List[Dict[str, Any]] = []
        for pos in positions:
            holdings.append({
                "contract": util.contractToDict(pos.contract),
                "symbol": pos.contract.symbol,
                "secType": pos.contract.secType,
                "exchange": pos.contract.exchange,
                "currency": pos.contract.currency,
                "quantity": pos.position,
                "avgCost": float(pos.avgCost) if pos.avgCost is not None else None
            })

        open_orders: List[Dict[str, Any]] = []
        for trade in open_trades:
            order = trade.order
            order_status = trade.orderStatus
            open_orders.append({
                "orderId": order.orderId,
                "symbol": trade.contract.symbol,
                "secType": trade.contract.secType,
                "action": order.action,
                "totalQuantity": order.totalQuantity,
                "remainingQuantity": order_status.remaining,
                "status": order_status.status,
                "limitPrice": getattr(order, "lmtPrice", None),
                "order": util.orderToDict(order),
                "contract": util.contractToDict(trade.contract)
            })

        def _extract_value(tag: str, currency: str = 'USD') -> float:
            for item in account_values:
                if item.tag == tag and item.currency == currency:
                    try:
                        return float(item.value)
                    except (TypeError, ValueError):
                        return 0.0
            return 0.0

        payload = {
            "updated_at": snapshot_ts,
            "net_liquidation": _extract_value('NetLiquidation'),
            "available_funds": _extract_value('AvailableFunds'),
            "holdings": holdings,
            "open_orders": open_orders
        }

        doc_ref = self._env.db.document(f"positions/{self._env.trading_mode}/latest_portfolio")
        doc_ref.set(payload)

        self._activity_log.update(status="success", reconciledHoldings=len(holdings), openOrders=len(open_orders))
        return payload
