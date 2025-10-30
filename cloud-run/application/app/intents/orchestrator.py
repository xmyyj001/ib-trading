from datetime import datetime, timezone
from typing import Any, Dict, List

from intents.intent import Intent
from intents.reconcile import Reconcile
from intents.allocation import Allocation
from strategies.test_signal_generator import TestSignalGenerator
from strategies.spy_macd_vixy import SpyMacdVixyIntent


STRATEGY_INTENT_REGISTRY = {
    'testsignalgenerator': TestSignalGenerator,
    'spy_macd_vixy': SpyMacdVixyIntent,
}


class Orchestrator(Intent):
    """
    Single entrypoint that sequentially:
    1. Executes enabled strategy intents to publish target positions.
    2. Runs the reconcile intent to capture live portfolio state.
    3. Invokes the commander (allocation) intent to aggregate and place orders.
    """

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self._strategy_ids = [s.lower() for s in kwargs.get('strategies', [])]
        self._dry_run = kwargs.get('dryRun', False)
        self._fresh_minutes = kwargs.get('freshMinutes', 180)
        self._run_reconcile = kwargs.get('runReconcile', True)
        self._activity_log.update(
            dryRun=self._dry_run,
            strategies=self._strategy_ids,
            freshMinutes=self._fresh_minutes,
            runReconcile=self._run_reconcile
        )

    async def _core_async(self) -> Dict[str, Any]:
        pipeline_results: Dict[str, Any] = {
            'strategies': [],
            'reconcile': None,
            'commander': None,
            'executed_at': datetime.now(timezone.utc).isoformat()
        }

        strategy_ids = self._strategy_ids or list(STRATEGY_INTENT_REGISTRY.keys())

        for strategy_id in strategy_ids:
            intent_cls = STRATEGY_INTENT_REGISTRY.get(strategy_id)
            if not intent_cls:
                error_msg = f"No registered strategy intent for '{strategy_id}'."
                self._env.logging.error(error_msg)
                pipeline_results['strategies'].append({
                    'strategy_id': strategy_id,
                    'status': 'error',
                    'error': error_msg
                })
                continue

            try:
                intent_instance = intent_cls(self._env, strategy_id=strategy_id, dryRun=self._dry_run)
                result = await intent_instance.run()
                pipeline_results['strategies'].append({
                    'strategy_id': strategy_id,
                    'status': result.get('status', 'unknown'),
                    'updated_at': result.get('updated_at'),
                    'error': result.get('error_message'),
                    'metadata': result.get('metadata')
                })
            except Exception as exc:  # noqa: BLE001
                self._env.logging.error(f"Strategy '{strategy_id}' failed: {exc}", exc_info=True)
                pipeline_results['strategies'].append({
                    'strategy_id': strategy_id,
                    'status': 'error',
                    'error': str(exc)
                })

        if self._run_reconcile:
            try:
                reconcile_intent = Reconcile(self._env)
                reconcile_result = await reconcile_intent.run()
                pipeline_results['reconcile'] = {
                    'status': 'success',
                    'updated_at': reconcile_result.get('updated_at'),
                    'holdings': len(reconcile_result.get('holdings', [])),
                    'open_orders': len(reconcile_result.get('open_orders', []))
                }
            except Exception as exc:  # noqa: BLE001
                self._env.logging.error(f"Reconcile failed: {exc}", exc_info=True)
                pipeline_results['reconcile'] = {
                    'status': 'error',
                    'error': str(exc)
                }

        try:
            commander_kwargs = {
                'dryRun': self._dry_run,
                'freshMinutes': self._fresh_minutes,
                'strategies': strategy_ids
            }
            commander_intent = Allocation(self._env, **commander_kwargs)
            commander_result = await commander_intent.run()
            pipeline_results['commander'] = {
                'status': commander_result.get('status', 'unknown'),
                'executed_at': commander_result.get('executed_at'),
                'orders': commander_result.get('orders', []),
                'summary': commander_result.get('summary'),
                'missing_strategies': commander_result.get('context', {}).get('missing_strategies'),
                'stale_strategies': commander_result.get('context', {}).get('stale_strategies')
            }
        except Exception as exc:  # noqa: BLE001
            self._env.logging.error(f"Commander failed: {exc}", exc_info=True)
            pipeline_results['commander'] = {
                'status': 'error',
                'error': str(exc)
            }

        self._activity_log.update(status='success', pipeline=pipeline_results)
        return pipeline_results
