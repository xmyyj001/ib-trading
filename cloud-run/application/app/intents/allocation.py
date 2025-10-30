import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ib_insync import MarketOrder, util

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

        portfolio_doc_ref = self._env.db.document(f"positions/{self._env.trading_mode}/latest_portfolio")
        portfolio_doc = portfolio_doc_ref.get()
        if not portfolio_doc.exists:
            raise RuntimeError("Portfolio snapshot missing; run reconcile first.")
        portfolio = portfolio_doc.to_dict() or {}

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
                contract = util.dictToContract(plan['contract'])
                if contract.conId is None:
                    qualified = await self._env.ibgw.qualifyContractsAsync(contract)
                    if qualified:
                        contract = qualified[0]
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

        execution_payload = {
            'executed_at': now.isoformat(),
            'trigger': 'scheduled',
            'status': 'completed',
            'summary': f"Planned {len(order_plan)} orders; {'placed' if not self._dry_run else 'simulated'} {len(orders_placed)}",
            'context': {
                'portfolio_snapshot_ref': f"{portfolio_doc_ref.path}@{portfolio.get('updated_at')}",
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

        self._activity_log.update(
            status='success',
            ordersPlanned=len(order_plan),
            ordersPlaced=len(orders_placed),
            dryRun=self._dry_run,
            missingStrategies=missing_strategies,
            staleStrategies=stale_strategies
        )

        return execution_payload

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
        docs = list(strategies_ref.stream())

        snapshots: List[Dict[str, Any]] = []
        intent_refs: List[str] = []
        stale_strategies: List[str] = []
        missing_strategies: List[str] = []
        aggregated_targets: Dict[str, Dict[str, Any]] = {}

        allowed_ids = set(self._strategy_ids) if self._strategy_ids else None

        for doc in docs:
            strategy_id = doc.id
            strategy_config = doc.to_dict() or {}
            if allowed_ids is not None and strategy_id not in allowed_ids:
                continue
            if allowed_ids is None and not strategy_config.get('enabled', True):
                continue

            intent_ref = doc.reference.collection('intent').document('latest')
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

            intent_refs.append(f"{intent_doc.reference.path}@{intent_data.get('updated_at')}")
            updated_at = _parse_iso(intent_data.get('updated_at'))
            if updated_at and now - updated_at > freshness_delta:
                stale_strategies.append(strategy_id)
                continue
            if intent_data.get('status') != 'success':
                stale_strategies.append(strategy_id)
                continue

            for target in intent_data.get('target_positions', []):
                contract_info = target.get('contract', {})
                key = _contract_key(contract_info)
                quantity = int(target.get('quantity', 0))
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

        if allowed_ids:
            existing = {snap['strategy_id'] for snap in snapshots}
            for requested in allowed_ids:
                if requested not in existing:
                    missing_strategies.append(requested)

        return snapshots, intent_refs, stale_strategies, missing_strategies, aggregated_targets
