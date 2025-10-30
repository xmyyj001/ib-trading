import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from intents.allocation import Allocation


class FakeIntentDocument:
    def __init__(self, path, data):
        self._data = data
        self.reference = SimpleNamespace(path=path)

    def get(self):
        return self

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class FakeIntentCollection:
    def __init__(self, doc_id, intent_data):
        self._doc_id = doc_id
        self._intent_data = intent_data

    def document(self, name):
        path = f"strategies/{self._doc_id}/intent/{name}"
        return FakeIntentDocument(path, self._intent_data)


class FakeStrategyDoc:
    def __init__(self, doc_id, data, intent_data):
        self.id = doc_id
        self._data = data
        self._intent_data = intent_data
        self.reference = SimpleNamespace(collection=lambda _: FakeIntentCollection(doc_id, intent_data))

    def to_dict(self):
        return self._data


class FakeStrategyCollection:
    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)


class FakeExecutionDocument:
    def __init__(self, sink):
        self._sink = sink
        self.path = f"executions/{len(sink) + 1}"

    def set(self, payload):
        self._sink.append(payload)


class FakeExecutionsCollection:
    def __init__(self, sink):
        self._sink = sink

    def document(self):
        return FakeExecutionDocument(self._sink)


class FakePortfolioDocument:
    def __init__(self, path, data):
        self.path = path
        self._data = data

    def get(self):
        return self

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class FakeDB:
    def __init__(self, portfolio, strategy_docs, execution_sink):
        self._portfolio = portfolio
        self._strategy_docs = strategy_docs
        self._execution_sink = execution_sink

    def document(self, path):
        if path.endswith('latest_portfolio'):
            return FakePortfolioDocument(path, self._portfolio)
        raise ValueError(f"Unsupported document path: {path}")

    def collection(self, name):
        if name == 'strategies':
            return FakeStrategyCollection(self._strategy_docs)
        if name == 'executions':
            return FakeExecutionsCollection(self._execution_sink)
        raise ValueError(f"Unsupported collection: {name}")


class FakeIBGW:
    async def qualifyContractsAsync(self, contract):
        return [contract]

    def placeOrder(self, contract, order):
        return None


class AllocationIntentTests(unittest.TestCase):
    def setUp(self):
        self.execution_sink = []
        now = datetime.now(timezone.utc).isoformat()
        # Portfolio: currently 10 shares, 2 buy orders pending
        self.portfolio_doc = {
            'updated_at': now,
            'holdings': [
                {
                    'contract': {'conId': 1001, 'symbol': 'SPY', 'secType': 'STK', 'exchange': 'SMART', 'currency': 'USD'},
                    'quantity': 10
                }
            ],
            'open_orders': [
                {
                    'contract': {'conId': 1001},
                    'action': 'BUY',
                    'remainingQuantity': 2
                }
            ]
        }
        # Strategy target: aim for 20 shares total
        self.strategy_doc = FakeStrategyDoc(
            'testsignalgenerator',
            {'enabled': True},
            {
                'status': 'success',
                'updated_at': now,
                'target_positions': [
                    {
                        'symbol': 'SPY',
                        'secType': 'STK',
                        'exchange': 'SMART',
                        'currency': 'USD',
                        'quantity': 20,
                        'contract': {'conId': 1001, 'symbol': 'SPY', 'secType': 'STK', 'exchange': 'SMART', 'currency': 'USD'}
                    }
                ]
            }
        )
        self.env = SimpleNamespace(
            db=FakeDB(self.portfolio_doc, [self.strategy_doc], self.execution_sink),
            ibgw=FakeIBGW(),
            logging=SimpleNamespace(info=lambda *args, **kwargs: None,
                                    warning=lambda *args, **kwargs: None,
                                    error=lambda *args, **kwargs: None),
            trading_mode='paper',
            env={'K_REVISION': 'localhost'},
            config={'exposure': {'overall': 1.0, 'strategies': {'testsignalgenerator': 1.0}}}
        )

    def test_allocation_generates_buy_plan_with_dry_run(self):
        allocation = Allocation(self.env, dryRun=True, strategies=['testsignalgenerator'])
        result = asyncio.run(allocation._core_async())

        self.assertTrue(result['dry_run'])
        self.assertEqual(len(result['decision']['diff']), 1)
        planned_order = result['decision']['diff'][0]
        # Current 10 + inflight 2 -> need 8 more to reach 20
        self.assertEqual(planned_order['quantity'], 8)
        self.assertEqual(planned_order['action'], 'BUY')
        # Execution log should be recorded
        self.assertEqual(len(self.execution_sink), 1)
        self.assertEqual(self.execution_sink[0]['orders'][0]['simulated'], True)


if __name__ == '__main__':
    unittest.main()
