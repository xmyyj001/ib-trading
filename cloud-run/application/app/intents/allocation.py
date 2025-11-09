import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ib_insync import MarketOrder, Contract
from lib.ib_serialization import dict_to_contract

from intents.intent import Intent


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        if ts.endswith('Z'):
            ts = ts.replace('Z', '+00:00')
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _contract_key(contract: Dict[str, Any]) -> str:
    con_id = contract.get('conId')
    if con_id is not None:
        return str(con_id)
    return f"{contract.get('symbol','')}:{contract.get('secType','')}:{contract.get('exchange','')}:{contract.get('currency','')}"


def _normalize_contract_for_order(contract: Contract, plan: Dict[str, Any]) -> None:
    if getattr(contract, 'secType', '').upper() != 'STK':
        return

    plan_contract = plan.get('contract') or {}
    stored_exchange = plan_contract.get('exchange') or plan.get('exchange')
    stored_primary = plan_contract.get('primaryExchange') or plan.get('primaryExchange')

    if not getattr(contract, 'primaryExchange', None):
        if stored_primary and stored_primary.upper() != 'SMART':
            contract.primaryExchange = stored_primary
        elif stored_exchange:
            upper_exchange = stored_exchange.upper()
            if upper_exchange != 'SMART':
                contract.primaryExchange = stored_exchange

    if getattr(contract, 'exchange', '').upper() != 'SMART':
        contract.exchange = 'SMART'


def _infer_target_symbol(target: Dict[str, Any], contract_info: Dict[str, Any]) -> Optional[str]:
    return target.get('symbol') or contract_info.get('symbol')


def _infer_target_price(target: Dict[str, Any], contract_info: Dict[str, Any]) -> Optional[float]:
    price_fields = ('price', 'last_price', 'lastPrice')
    contract_price_fields = ('price', 'marketPrice', 'lastTradePrice', 'avgCost')

    for field in price_fields:
        value = target.get(field)
        if isinstance(value, (int, float)):
            return float(value)

    for field in contract_price_fields:
        value = contract_info.get(field)
        if isinstance(value, (int, float)):
            return float(value)

    return None


class Allocation(Intent):
    """
    Commander intent:
    - Read the latest reconciled portfolio
    - Aggregate target intents from strategies
    - Compute order deltas and (optionally) place trades
    - Persist an execution log to Firestore
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self._dry_run = kwargs.get('dryRun', False)
        strategies = kwargs.get('strategies')
        self._strategy_ids = [s.lower() for s in strategies] if strategies else None
        self._fresh_minutes = kwargs.get('freshMinutes', 180)
        self._activity_log.update(dryRun=self._dry_run, strategies=self._strategy_ids, freshMinutes=self._fresh_minutes)

    async def _core_async(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        freshness_delta = timedelta(minutes=self._fresh_minutes)

        portfolio, portfolio_doc_ref, legacy_shape = self._load_portfolio_snapshot()
        if not portfolio:
            raise RuntimeError("Portfolio snapshot missing; run reconcile first.")
        snapshot_pointer = portfolio_doc_ref.path
        if legacy_shape:
            snapshot_pointer = f"{snapshot_pointer}#latest_portfolio"

        portfolio_updated_at = _parse_iso(portfolio.get('updated_at'))
        if portfolio_updated_at and now - portfolio_updated_at > freshness_delta:
            minutes_stale = (now - portfolio_updated_at).total_seconds() / 60
            self._env.logging.warning("Portfolio snapshot is stale by %.1f minutes", minutes_stale)

        (
            strategy_snapshots,
            intent_refs,
            stale_strategies,
            missing_strategies,
            aggregated_targets,
        ) = self._collect_strategy_targets(now, freshness_delta)

        holdings_map: Dict[str, Dict[str, Any]] = {}
        for holding in portfolio.get('holdings', []):
            contract_info = holding.get('contract', {})
            key = _contract_key(contract_info)
            holdings_map[key] = {
                'quantity': int(holding.get('quantity', 0)),
                'contract': contract_info,
                'symbol': holding.get('symbol') or contract_info.get('symbol'),
                'secType': holding.get('secType') or contract_info.get('secType'),
                'exchange': holding.get('exchange') or contract_info.get('exchange'),
                'currency': holding.get('currency') or contract_info.get('currency'),
            }
            if key not in aggregated_targets:
                aggregated_targets[key] = {
                    'contract': contract_info,
                    'symbol': holdings_map[key]['symbol'],
                    'secType': holdings_map[key]['secType'],
                    'exchange': holdings_map[key]['exchange'],
                    'currency': holdings_map[key]['currency'],
                    'quantity': 0,
                    'contributors': []
                }

        inflight_map: Dict[str, int] = {}
        for order in portfolio.get('open_orders', []):
            contract_info = order.get('contract', {})
            key = _contract_key(contract_info)
            remaining = int(order.get('remainingQuantity', 0))
            action = order.get('action')
            if remaining == 0 or action not in ('BUY', 'SELL'):
                continue
            delta = remaining if action == 'BUY' else -remaining
            inflight_map[key] = inflight_map.get(key, 0) + delta

        # Apply global risk adjustments here if needed. For now, final targets == aggregated targets.
        final_targets = aggregated_targets

        order_plan: List[Dict[str, Any]] = []
        for key, target in final_targets.items():
            desired_quantity = int(target.get('quantity', 0))
            current_quantity = int(holdings_map.get(key, {}).get('quantity', 0))
            inflight_quantity = inflight_map.get(key, 0)
            delta = desired_quantity - (current_quantity + inflight_quantity)
            if delta == 0:
                continue
            action = 'BUY' if delta > 0 else 'SELL'
            order_plan.append({
                'contract': target['contract'],
                'symbol': target.get('symbol'),
                'secType': target.get('secType'),
                'exchange': target.get('exchange'),
                'currency': target.get('currency'),
                'desired_quantity': desired_quantity,
                'current_quantity': current_quantity,
                'inflight_quantity': inflight_quantity,
                'delta': delta,
                'action': action,
                'quantity': abs(delta)
            })

        orders_placed: List[Dict[str, Any]] = []
        if not self._dry_run:
            for plan in order_plan:
                contract_payload = plan.get('contract')
                contract = dict_to_contract(contract_payload or {})
                if not getattr(contract, 'conId', None) and not getattr(contract, 'symbol', None):
                    self._env.logging.error(
                        "Skipping order for %s because contract metadata is missing",
                        plan.get('symbol') or plan
                    )
                    continue
                if contract.conId is None:
                    qualified = await self._env.ibgw.qualifyContractsAsync(contract)
                    if qualified:
                        contract = qualified[0]
                _normalize_contract_for_order(contract, plan)
                order = MarketOrder(plan['action'], plan['quantity'])
                trade = self._env.ibgw.placeOrder(contract, order)
                if trade:
                    await asyncio.sleep(0.1)
                    orders_placed.append({
                        'orderId': trade.order.orderId,
                        'symbol': trade.contract.symbol,
                        'action': trade.order.action,
                        'quantity': trade.order.totalQuantity,
                        'status': trade.orderStatus.status
                    })
        else:
            for plan in order_plan:
                orders_placed.append({
                    'simulated': True,
                    'symbol': plan['symbol'],
                    'action': plan['action'],
                    'quantity': plan['quantity']
                })

        summary_text = f"Planned {len(order_plan)} orders; {'placed' if not self._dry_run else 'simulated'} {len(orders_placed)}"

        execution_payload = {
            'executed_at': now.isoformat(),
            'trigger': 'scheduled',
            'status': 'completed',
            'summary': summary_text,
            'context': {
                'portfolio_snapshot_ref': f"{snapshot_pointer}@{portfolio.get('updated_at')}",
                'strategy_snapshots': strategy_snapshots,
                'strategy_intents_refs': intent_refs,
                'missing_strategies': missing_strategies,
                'stale_strategies': stale_strategies
            },
            'decision': {
                'aggregated_target': [
                    {
                        'contract': target['contract'],
                        'symbol': target.get('symbol'),
                        'quantity': target.get('quantity'),
                        'contributors': target.get('contributors')
                    }
                    for target in final_targets.values()
                ],
                'final_target': [
                    {
                        'contract': target['contract'],
                        'symbol': target.get('symbol'),
                        'quantity': target.get('quantity')
                    }
                    for target in final_targets.values()
                ],
                'diff': order_plan
            },
            'orders': orders_placed,
            'dry_run': self._dry_run
        }

        execution_doc = self._env.db.collection('executions').document()
        execution_doc.set(execution_payload)
        self._env.logging.info(
            "Commander: %s | missing=%s | stale=%s",
            summary_text,
            missing_strategies,
            stale_strategies
        )

        self._activity_log.update(
            status='success',
            ordersPlanned=len(order_plan),
            ordersPlaced=len(orders_placed),
            dryRun=self._dry_run,
            missingStrategies=missing_strategies,
            staleStrategies=stale_strategies
        )

        return execution_payload

    def _load_portfolio_snapshot(self) -> Tuple[Optional[Dict[str, Any]], Any, bool]:
        """
        Loads the latest reconciled portfolio.

        Returns:
            Tuple of (portfolio dict or None, DocumentReference used, bool indicating legacy embedded shape)
        """
        positions_ref = self._env.db.collection("positions").document(self._env.trading_mode)
        latest_doc_ref = positions_ref.collection("latest_portfolio").document("snapshot")
        latest_doc = latest_doc_ref.get()
        if latest_doc.exists:
            return latest_doc.to_dict() or {}, latest_doc_ref, False

        legacy_doc = positions_ref.get()
        if legacy_doc.exists:
            legacy_payload = legacy_doc.to_dict() or {}
            embedded = legacy_payload.get("latest_portfolio")
            if isinstance(embedded, dict):
                return embedded, positions_ref, True

        return None, latest_doc_ref, False

    def _collect_strategy_targets(
        self,
        now: datetime,
        freshness_delta: timedelta,
    ) -> Tuple[
        List[Dict[str, Any]],
        List[str],
        List[str],
        List[str],
        Dict[str, Dict[str, Any]]
    ]:
        strategies_ref = self._env.db.collection('strategies')
        streamed_docs = list(strategies_ref.stream())
        snapshot_map = {doc.id: doc for doc in streamed_docs}

        snapshots: List[Dict[str, Any]] = []
        intent_refs: List[str] = []
        stale_strategies: List[str] = []
        missing_strategies: List[str] = []
        aggregated_targets: Dict[str, Dict[str, Any]] = {}

        allowed_ids = [s for s in self._strategy_ids] if self._strategy_ids else None
        candidate_ids = allowed_ids or list(snapshot_map.keys())

        for strategy_id in candidate_ids:
            if strategy_id in snapshot_map:
                doc_snapshot = snapshot_map[strategy_id]
            else:
                doc_snapshot = strategies_ref.document(strategy_id).get()

            doc_ref = doc_snapshot.reference if getattr(doc_snapshot, "reference", None) else strategies_ref.document(strategy_id)
            strategy_config = doc_snapshot.to_dict() or {}

            if allowed_ids is None and not strategy_config.get('enabled', True):
                continue

            intent_ref = doc_ref.collection('intent').document('latest')
            intent_doc = intent_ref.get()
            intent_data = intent_doc.to_dict() if intent_doc.exists else None

            snapshot_meta = {
                'strategy_id': strategy_id,
                'config': strategy_config,
                'intent_updated_at': intent_data.get('updated_at') if intent_data else None,
                'intent_status': intent_data.get('status') if intent_data else None
            }
            snapshots.append(snapshot_meta)

            if not intent_doc.exists:
                missing_strategies.append(strategy_id)
                continue

            intent_refs.append(f"{intent_ref.path}@{intent_data.get('updated_at')}")
            updated_at = _parse_iso(intent_data.get('updated_at'))
            if updated_at and now - updated_at > freshness_delta:
                stale_strategies.append(strategy_id)
                continue
            if intent_data.get('status') != 'success':
                stale_strategies.append(strategy_id)
                continue

            for target in intent_data.get('target_positions', []):
                contract_info = target.get('contract', {})
                guardrail_quantity = self._apply_guardrails(strategy_id, strategy_config, target, contract_info)
                if guardrail_quantity is None or guardrail_quantity == 0:
                    continue
                key = _contract_key(contract_info)
                quantity = guardrail_quantity
                if key not in aggregated_targets:
                    aggregated_targets[key] = {
                        'contract': contract_info,
                        'symbol': target.get('symbol'),
                        'secType': target.get('secType'),
                        'exchange': target.get('exchange'),
                        'currency': target.get('currency'),
                        'quantity': 0,
                        'contributors': []
                    }
                aggregated_targets[key]['quantity'] += quantity
                aggregated_targets[key]['contributors'].append({
                    'strategy_id': strategy_id,
                    'quantity': quantity
                })

        return snapshots, intent_refs, stale_strategies, missing_strategies, aggregated_targets

    def _apply_guardrails(
        self,
        strategy_id: str,
        strategy_config: Dict[str, Any],
        target: Dict[str, Any],
        contract_info: Dict[str, Any],
    ) -> Optional[int]:
        quantity = int(target.get('quantity', 0))
        if quantity == 0:
            return 0

        symbol = _infer_target_symbol(target, contract_info)
        allowed = strategy_config.get('allowed_symbols')
        if allowed and symbol and symbol not in allowed:
            self._env.logging.warning(
                "Strategy %s target for %s dropped; symbol not in allowed list.",
                strategy_id,
                symbol
            )
            return None

        max_notional_raw = strategy_config.get('max_notional')
        try:
            max_notional = float(max_notional_raw)
        except (TypeError, ValueError):
            max_notional = 0.0

        if max_notional > 0:
            price = _infer_target_price(target, contract_info)
            if price and price > 0:
                max_quantity = int(max_notional // price)
                if max_quantity == 0:
                    self._env.logging.warning(
                        "Strategy %s target for %s trimmed to 0; max_notional %.2f too small for price %.2f",
                        strategy_id,
                        symbol,
                        max_notional,
                        price
                    )
                    return None
                if abs(quantity) > max_quantity:
                    trimmed_quantity = max_quantity if quantity > 0 else -max_quantity
                    self._env.logging.info(
                        "Strategy %s target for %s trimmed from %d to %d due to max_notional %.2f",
                        strategy_id,
                        symbol,
                        quantity,
                        trimmed_quantity,
                        max_notional
                    )
                    quantity = trimmed_quantity
            else:
                self._env.logging.warning(
                    "Strategy %s target for %s lacks price; cannot enforce max_notional %.2f",
                    strategy_id,
                    symbol,
                    max_notional
                )

        return quantity
