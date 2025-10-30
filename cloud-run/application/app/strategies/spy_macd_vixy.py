from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd
from ib_insync import Stock, util

from intents.intent import Intent
from lib.trading import Stock as StockInstrument
from strategies.strategy import Strategy


def _contract_dict(contract) -> Dict[str, Any]:
    return util.contractToDict(contract) if contract else {}


class SpyMacdVixy(Strategy):
    def __init__(self, **kwargs):
        self.spy = Stock('SPY', 'SMART', 'USD')
        self.vixy = Stock('VIXY', 'BATS', 'USD')
        super().__init__(**kwargs)

    def _get_signals(self):
        spy_contract = self._instruments['spy'][0].contract
        vixy_contract = self._instruments['vixy'][0].contract
        if not spy_contract or not vixy_contract:
            self._env.logging.error("SPY or VIXY contract details not available.")
            self._signals = {}
            return

        bars = self._env.ibgw.reqHistoricalData(
            spy_contract, endDateTime='', durationStr='100 D',
            barSizeSetting='1 day', whatToShow='TRADES', useRTH=True)
        if not bars:
            self._env.logging.error("Could not fetch historical data for SPY.")
            self._signals = {}
            return

        df = util.df(bars)
        if df.empty:
            self._env.logging.error("SPY data is empty.")
            self._signals = {}
            return

        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()

        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2]:
            self._signals = {spy_contract.conId: 1.0, vixy_contract.conId: 0.0}
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2]:
            self._signals = {spy_contract.conId: -1.0, vixy_contract.conId: 1.0}
        else:
            self._signals = {}

    def _setup(self):
        from lib.trading import InstrumentSet
        self._instruments = {
            'spy': InstrumentSet(self.spy),
            'vixy': InstrumentSet(self.vixy)
        }
        for key in self._instruments:
            inst = self._instruments[key].constituents[0]
            inst.get_contract_details()
            if inst.contract:
                inst.get_tickers()
            else:
                self._env.logging.error(f"Failed to get contract details for {key.upper()}.")
                self._instruments[key] = None


class SpyMacdVixyIntent(Intent):
    """
    Intent wrapper for the legacy SpyMacdVixy strategy.
    Publishes target holdings for SPY and VIXY instead of placing trades.
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self.id = kwargs.get('strategy_id', 'spy_macd_vixy')
        self._dry_run = kwargs.get('dryRun', False)

    async def _core_async(self) -> Dict[str, Any]:
        doc_ref = self._env.db.document(f"strategies/{self.id}/intent/latest")
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            spy_contract = await self._qualify_stock('SPY', 'SMART', 'USD')
            vixy_contract = await self._qualify_stock('VIXY', 'BATS', 'USD')

            spy_df = await self._fetch_history(spy_contract, duration='200 D', bar_size='1 day')
            if spy_df.empty or len(spy_df) < 2:
                payload = _error_payload("Insufficient SPY historical data.", now_iso)
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], error_message=payload["error_message"])
                return payload

            macd, signal = self._calculate_macd(spy_df)
            last_price = spy_df.iloc[-1]['close']

            regime = self._determine_regime(macd, signal)
            if regime == 'neutral':
                payload = {
                    "updated_at": now_iso,
                    "status": "success",
                    "error_message": None,
                    "metadata": {
                        "regime": regime,
                        "last_macd": float(macd.iloc[-1]),
                        "last_signal": float(signal.iloc[-1]),
                        "reason": "No MACD crossover detected"
                    },
                    "target_positions": []
                }
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], metadata=payload["metadata"])
                return payload

            vixy_df = await self._fetch_history(vixy_contract, duration='30 D', bar_size='1 day')
            vixy_price = vixy_df.iloc[-1]['close'] if not vixy_df.empty else None

            account_values = self._env.ibgw.accountValues()
            portfolio = self._env.ibgw.portfolio()
            open_trades = self._env.ibgw.openTrades()

            net_liquidation = self._extract_account_value(account_values, 'NetLiquidation')
            if net_liquidation == 0:
                payload = _error_payload("Net Liquidation is zero.", now_iso)
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], error_message=payload["error_message"])
                return payload

            exposure_cfg = self._env.config.get('exposure', {})
            overall_exposure_pct = exposure_cfg.get('overall', 0)
            strategy_weight_pct = exposure_cfg.get('strategies', {}).get(self.id, 0)
            deployable_capital = net_liquidation * overall_exposure_pct * strategy_weight_pct

            weights = self._regime_weights(regime)
            total_weight = sum(abs(w) for w in weights.values())

            if total_weight == 0 or deployable_capital == 0:
                payload = {
                    "updated_at": now_iso,
                    "status": "success",
                    "error_message": None,
                    "metadata": {
                        "regime": regime,
                        "deployable_capital": deployable_capital,
                        "reason": "Zero exposure or weights"
                    },
                    "target_positions": []
                }
                doc_ref.set(payload)
                self._activity_log.update(status=payload["status"], metadata=payload["metadata"])
                return payload

            holdings_map = self._build_holdings_map(portfolio)
            inflight_map = self._build_inflight_map(open_trades)

            target_positions, allocations = self._build_targets(
                weights,
                deployable_capital,
                total_weight,
                {
                    'SPY': (spy_contract, last_price),
                    'VIXY': (vixy_contract, vixy_price)
                },
                holdings_map,
                inflight_map
            )

            payload = {
                "updated_at": now_iso,
                "status": "success",
                "error_message": None,
                "metadata": {
                    "regime": regime,
                    "last_macd": float(macd.iloc[-1]),
                    "last_signal": float(signal.iloc[-1]),
                    "deployable_capital": deployable_capital,
                    "allocations": allocations,
                    "dry_run": self._dry_run
                },
                "target_positions": target_positions
            }
            doc_ref.set(payload)
            self._activity_log.update(status=payload["status"], metadata=payload["metadata"], target_positions=target_positions)
            return payload

        except Exception as exc:  # noqa: BLE001
            payload = _error_payload(str(exc), now_iso)
            doc_ref.set(payload)
            self._activity_log.update(status="error", error_message=str(exc))
            raise

    async def _qualify_stock(self, symbol: str, exchange: str, currency: str):
        stock = Stock(symbol, exchange, currency)
        qualified = await self._env.ibgw.qualifyContractsAsync(stock)
        if not qualified:
            raise RuntimeError(f"Failed to qualify contract for {symbol}.")
        return StockInstrument(self._env, ib_contract=qualified[0]).contract

    async def _fetch_history(self, contract, duration: str, bar_size: str) -> pd.DataFrame:
        bars = await self._env.ibgw.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow='TRADES',
            useRTH=True,
            timeout=30,
        )
        if not bars:
            return pd.DataFrame()
        return util.df(bars)

    @staticmethod
    def _calculate_macd(df: pd.DataFrame):
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal

    @staticmethod
    def _determine_regime(macd: pd.Series, signal: pd.Series) -> str:
        if len(macd) < 2 or len(signal) < 2:
            return 'neutral'
        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
            return 'bullish'
        if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
            return 'bearish'
        return 'neutral'

    @staticmethod
    def _regime_weights(regime: str) -> Dict[str, float]:
        if regime == 'bullish':
            return {'SPY': 1.0, 'VIXY': 0.0}
        if regime == 'bearish':
            return {'SPY': -1.0, 'VIXY': 1.0}
        return {'SPY': 0.0, 'VIXY': 0.0}

    @staticmethod
    def _extract_account_value(account_values, tag: str, currency: str = 'USD') -> float:
        for item in account_values:
            if item.tag == tag and item.currency == currency:
                try:
                    return float(item.value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    @staticmethod
    def _build_holdings_map(portfolio) -> Dict[str, Dict[str, Any]]:
        holdings = {}
        for item in portfolio:
            contract = util.contractToDict(item.contract)
            key = str(item.contract.conId)
            holdings[key] = {
                'quantity': item.position,
                'contract': contract,
                'symbol': item.contract.symbol,
                'secType': item.contract.secType,
                'exchange': item.contract.exchange,
                'currency': item.contract.currency
            }
        return holdings

    @staticmethod
    def _build_inflight_map(open_trades) -> Dict[str, int]:
        inflight = {}
        for trade in open_trades:
            remaining = trade.remaining()
            if remaining == 0:
                continue
            key = str(trade.contract.conId)
            delta = remaining if trade.order.action == 'BUY' else -remaining
            inflight[key] = inflight.get(key, 0) + delta
        return inflight

    def _build_targets(
        self,
        weights: Dict[str, float],
        deployable_capital: float,
        total_weight: float,
        contract_map: Dict[str, Any],
        holdings_map: Dict[str, Dict[str, Any]],
        inflight_map: Dict[str, int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        targets: List[Dict[str, Any]] = []
        allocations: List[Dict[str, Any]] = []

        for symbol, (contract, price) in contract_map.items():
            weight = weights.get(symbol, 0.0)
            if weight == 0 or not contract or not price:
                continue

            portion = abs(weight) / total_weight if total_weight else 0
            dollar_allocation = deployable_capital * portion
            raw_quantity = int(dollar_allocation / price) if price else 0
            target_quantity = raw_quantity if weight >= 0 else -raw_quantity

            key = str(contract.conId)
            current = holdings_map.get(key, {}).get('quantity', 0)
            inflight = inflight_map.get(key, 0)
            expected_final = current + inflight

            allocations.append({
                'symbol': symbol,
                'weight': weight,
                'price': float(price),
                'target_quantity': int(target_quantity),
                'expected_final_quantity': int(expected_final),
                'dollar_allocation': dollar_allocation
            })

            targets.append({
                "symbol": symbol,
                "secType": contract.secType,
                "exchange": contract.exchange,
                "currency": contract.currency,
                "quantity": int(target_quantity),
                "contract": _contract_dict(contract)
            })

        return targets, allocations


def _error_payload(message: str, timestamp: str) -> Dict[str, Any]:
    return {
        "updated_at": timestamp,
        "status": "error",
        "error_message": message,
        "metadata": {},
        "target_positions": []
    }
