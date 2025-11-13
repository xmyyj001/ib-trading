"""
Momentum strategy that combines MACD and Stochastic signals.

Implements the Commander contract: fetch market data for a basket of tech
tickers, evaluate signal strength, and publish target positions to Firestore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from ib_insync import Stock, util

from intents.intent import Intent
from lib.ib_serialization import contract_to_dict
from lib.trading import Stock as StockInstrument


def _async_macd(df: pd.DataFrame, fast: int, slow: int, signal: int) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": macd_line, "signal": signal_line})


def _stochastic(df: pd.DataFrame, lookback: int, smooth: int) -> pd.Series:
    low_min = df["low"].rolling(window=lookback, min_periods=lookback).min()
    high_max = df["high"].rolling(window=lookback, min_periods=lookback).max()
    percent_k = (df["close"] - low_min) / (high_max - low_min) * 100
    return percent_k.rolling(window=smooth, min_periods=smooth).mean()


@dataclass(frozen=True)
class IndicatorSettings:
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    stochastic_lookback: int = 20
    stochastic_smooth: int = 3
    stochastic_threshold: float = 30.0


class IbMacdStochIntent(Intent):
    """Commander-friendly strategy intent."""

    DEFAULT_TICKERS: Sequence[str] = ("META", "AMZN", "TSLA", "MSFT", "AAPL")

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self.id = kwargs.get("strategy_id", "ib_macd_stoch")
        self._dry_run = kwargs.get("dryRun", False)
        self._tickers: Sequence[str] = tuple(kwargs.get("tickers", self.DEFAULT_TICKERS))
        self._settings = IndicatorSettings(
            macd_fast=kwargs.get("macd_fast", IndicatorSettings.macd_fast),
            macd_slow=kwargs.get("macd_slow", IndicatorSettings.macd_slow),
            macd_signal=kwargs.get("macd_signal", IndicatorSettings.macd_signal),
            stochastic_lookback=kwargs.get("stochastic_lookback", IndicatorSettings.stochastic_lookback),
            stochastic_smooth=kwargs.get("stochastic_smooth", IndicatorSettings.stochastic_smooth),
            stochastic_threshold=kwargs.get("stochastic_threshold", IndicatorSettings.stochastic_threshold),
        )

    async def _core_async(self) -> Dict[str, Any]:
        doc_ref = (
            self._env.db.collection("strategies")
            .document(self.id)
            .collection("intent")
            .document("latest")
        )
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            account_values = self._env.ibgw.accountValues()
            net_liquidation = self._extract_account_value(account_values, "NetLiquidation")
            if net_liquidation == 0:
                raise RuntimeError("Net Liquidation is zero.")

            portfolio = self._env.ibgw.portfolio()
            open_trades = self._env.ibgw.openTrades()

            exposure_cfg = self._env.config.get("exposure", {})
            overall_exposure = exposure_cfg.get("overall", 0)
            strategy_weight = exposure_cfg.get("strategies", {}).get(self.id, 0)
            deployable_capital = net_liquidation * overall_exposure * strategy_weight

            symbol_results = []
            active_signals = []
            for symbol in self._tickers:
                evaluation = await self._evaluate_symbol(symbol)
                symbol_results.append(evaluation)
                if evaluation["direction"] > 0:
                    active_signals.append(evaluation)

            target_positions: List[Dict[str, Any]] = []
            allocations: List[Dict[str, Any]] = []
            if active_signals:
                per_symbol_allocation = deployable_capital / len(active_signals) if deployable_capital else 0
                holdings = self._build_holdings_map(portfolio)
                inflight = self._build_inflight_map(open_trades)

                for entry in active_signals:
                    contract = entry["contract"]
                    price = entry["last_price"]
                    allocation = per_symbol_allocation
                    quantity = int(allocation / price) if price else 0
                    key = str(contract.conId)
                    expected_quantity = holdings.get(key, 0) + inflight.get(key, 0)

                    target_positions.append(
                        {
                            "symbol": contract.symbol,
                            "secType": contract.secType,
                            "exchange": contract.exchange,
                            "currency": contract.currency,
                            "price": price,
                            "quantity": quantity,
                            "contract": contract_to_dict(contract),
                        }
                    )
                    allocations.append(
                        {
                            "symbol": contract.symbol,
                            "allocation": allocation,
                            "target_quantity": quantity,
                            "expected_final_quantity": expected_quantity,
                        }
                    )

            metadata = {
                "symbols": symbol_results,
                "deployable_capital": deployable_capital,
                "allocations": allocations,
                "dry_run": self._dry_run,
            }
            payload = {
                "updated_at": timestamp,
                "status": "success",
                "error_message": None,
                "metadata": metadata,
                "target_positions": target_positions,
            }
            doc_ref.set(payload)
            self._activity_log.update(status="success", metadata=metadata, target_positions=target_positions)
            return payload

        except Exception as exc:  # noqa: BLE001
            payload = self._error_payload(str(exc), timestamp)
            doc_ref.set(payload)
            self._activity_log.update(status="error", error_message=str(exc))
            raise

    async def _evaluate_symbol(self, symbol: str) -> Dict[str, Any]:
        contract = await self._qualify_contract(symbol)
        bars = await self._env.ibgw.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr="1 Y",
            barSizeSetting="15 mins",
            whatToShow="ADJUSTED_LAST",
            useRTH=True,
            timeout=30,
        )
        df = util.df(bars)
        if df.empty:
            raise RuntimeError(f"No historical data for {symbol}.")
        df = df.rename(columns=str.lower)
        df = df[["date", "open", "high", "low", "close"]].set_index("date")

        macd_df = _async_macd(df, self._settings.macd_fast, self._settings.macd_slow, self._settings.macd_signal)
        stoch = _stochastic(df, self._settings.stochastic_lookback, self._settings.stochastic_smooth)

        last_macd = float(macd_df["macd"].iloc[-1])
        last_signal = float(macd_df["signal"].iloc[-1])
        last_stoch = float(stoch.iloc[-1])
        prev_stoch = float(stoch.iloc[-2]) if len(stoch) >= 2 else last_stoch
        last_price = float(df["close"].iloc[-1])

        direction = 1 if last_macd > last_signal and last_stoch > self._settings.stochastic_threshold and last_stoch > prev_stoch else 0

        return {
            "symbol": symbol,
            "last_macd": last_macd,
            "last_signal": last_signal,
            "last_stochastic": last_stoch,
            "direction": direction,
            "last_price": last_price,
            "contract": contract,
            "reason": "long" if direction else "no_signal",
        }

    async def _qualify_contract(self, symbol: str):
        stock = Stock(symbol, "SMART", "USD")
        qualified = await self._env.ibgw.qualifyContractsAsync(stock)
        if not qualified:
            raise RuntimeError(f"Failed to qualify contract for {symbol}.")
        return StockInstrument(self._env, ib_contract=qualified[0]).contract

    @staticmethod
    def _extract_account_value(account_values, tag: str, currency: str = "USD") -> float:
        for item in account_values:
            if item.tag == tag and item.currency == currency:
                try:
                    return float(item.value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    @staticmethod
    def _build_holdings_map(portfolio) -> Dict[str, int]:
        holdings: Dict[str, int] = {}
        for item in portfolio:
            holdings[str(item.contract.conId)] = int(item.position)
        return holdings

    @staticmethod
    def _build_inflight_map(open_trades) -> Dict[str, int]:
        inflight: Dict[str, int] = {}
        for trade in open_trades:
            remaining = trade.remaining()
            if remaining == 0:
                continue
            delta = remaining if trade.order.action == "BUY" else -remaining
            inflight[str(trade.contract.conId)] = inflight.get(str(trade.contract.conId), 0) + delta
        return inflight

    @staticmethod
    def _error_payload(message: str, timestamp: str) -> Dict[str, Any]:
        return {
            "updated_at": timestamp,
            "status": "error",
            "error_message": message,
            "metadata": {},
            "target_positions": [],
        }
