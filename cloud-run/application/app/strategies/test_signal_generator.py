from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from ib_insync import Stock, util

from intents.intent import Intent
from lib.trading import Stock as StockInstrument

# Firestore document template helpers
def _contract_dict(contract) -> Dict[str, Any]:
    """Serialize an ib_insync contract into a Firestore-friendly dict."""
    return util.contractToDict(contract) if contract else {}

class TestSignalGenerator(Intent):
    """
    A robust, target-based strategy that is aware of in-flight orders to prevent duplicates.
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self.id = kwargs.get('strategy_id', self.__class__.__name__.lower())
        self._dry_run = kwargs.get('dryRun', False)

    async def _core_async(self):
        self._env.logging.info("--- Starting Robust, Target-Aware Signal Generator ---")
        doc_ref = self._env.db.document(f"strategies/{self.id}/intent/latest")

        try:
            spy_obj = Stock('SPY', 'SMART', 'USD')
            qualified_contracts = await self._env.ibgw.qualifyContractsAsync(spy_obj)
            spy_instrument = StockInstrument(self._env, ib_contract=qualified_contracts[0])

            self._env.logging.info("Fetching 5D/30min historical data for SPY...")
            bars = await self._env.ibgw.reqHistoricalDataAsync(
                spy_instrument.contract,
                endDateTime='',
                durationStr='5 D',
                barSizeSetting='30 mins',
                whatToShow='TRADES',
                useRTH=True,
                timeout=20,
            )

            if not bars:
                payload = _error_payload("Could not fetch market data.")
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], error_message=payload["error_message"])
                return payload

            df = util.df(bars)
            if df.empty:
                payload = _error_payload("Market data is empty.")
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], error_message=payload["error_message"])
                return payload

            exp12 = df['close'].ewm(span=12, adjust=False).mean()
            exp26 = df['close'].ewm(span=26, adjust=False).mean()
            macd = exp12 - exp26
            signal = macd.ewm(span=9, adjust=False).mean()
            last_price = df.iloc[-1]['close']
            self._env.logging.info(f"[Data Check] Last MACD: {macd.iloc[-1]:.4f}, Last Signal: {signal.iloc[-1]:.4f}")

            if macd.iloc[-1] == signal.iloc[-1]:
                payload = {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "success",
                    "error_message": None,
                    "metadata": {
                        "signal_strength": 0.0,
                        "last_macd": float(macd.iloc[-1]),
                        "last_signal": float(signal.iloc[-1]),
                        "reason": "No crossover"
                    },
                    "target_positions": []
                }
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], metadata=payload["metadata"])
                return payload

            signal_weight = 1.0 if macd.iloc[-1] > signal.iloc[-1] else -1.0

            account_values = self._env.ibgw.accountValues()
            portfolio = self._env.ibgw.portfolio()
            open_trades = self._env.ibgw.openTrades()

            net_liquidation_str = next((v.value for v in account_values if v.tag == 'NetLiquidation' and v.currency == 'USD'), '0')
            net_liquidation = float(net_liquidation_str)
            if net_liquidation == 0:
                payload = _error_payload("Net Liquidation is zero.")
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], error_message=payload["error_message"])
                return payload

            current_real_quantity = 0
            for item in portfolio:
                if item.contract.conId == spy_instrument.contract.conId:
                    current_real_quantity = item.position
                    break

            in_flight_quantity = 0
            for trade in open_trades:
                if trade.contract.conId != spy_instrument.contract.conId:
                    continue
                remaining = trade.remaining()
                if trade.order.action == 'BUY':
                    in_flight_quantity += remaining
                elif trade.order.action == 'SELL':
                    in_flight_quantity -= remaining

            expected_final_quantity = current_real_quantity + in_flight_quantity
            overall_exposure_pct = self._env.config['exposure']['overall']
            strategy_weight_pct = self._env.config['exposure']['strategies'].get(self.id, 0)
            target_exposure = net_liquidation * overall_exposure_pct * strategy_weight_pct
            target_quantity = int(target_exposure * signal_weight / last_price) if last_price else 0
            proposed_delta = target_quantity - expected_final_quantity
            action = 'BUY' if proposed_delta > 0 else 'SELL' if proposed_delta < 0 else 'HOLD'

            target_positions: List[Dict[str, Any]] = [{
                "symbol": spy_instrument.contract.symbol,
                "secType": spy_instrument.contract.secType,
                "exchange": spy_instrument.contract.exchange,
                "currency": spy_instrument.contract.currency,
                "quantity": int(target_quantity),
                "contract": _contract_dict(spy_instrument.contract)
            }]

            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "error_message": None,
                "metadata": {
                    "signal_weight": signal_weight,
                    "last_price": float(last_price),
                    "net_liquidation": net_liquidation,
                    "target_quantity": int(target_quantity),
                    "expected_final_quantity": int(expected_final_quantity),
                    "proposed_delta": int(proposed_delta),
                    "action_hint": action,
                    "dry_run": self._dry_run
                },
                "target_positions": target_positions
            }

            doc_ref.set(payload)
            self._activity_log.update(status=payload["status"], metadata=payload["metadata"], target_positions=target_positions)
            return payload

        except Exception as exc:
            error_payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "error_message": str(exc),
                "metadata": {},
                "target_positions": []
            }
            doc_ref.set(error_payload)
            self._activity_log.update(status="error", error_message=str(exc))
            raise


def _error_payload(message: str) -> Dict[str, Any]:
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "error_message": message,
        "metadata": {},
        "target_positions": []
    }
