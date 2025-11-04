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


class FakePositionsCollection:
    def __init__(self, trading_mode, portfolio):
        self._trading_mode = trading_mode
        self._portfolio = portfolio

    def document(self, name):
        if name != self._trading_mode:
            raise ValueError(f"Unsupported positions document: {name}")
        path = f'positions/{name}'
        return FakePortfolioDocument(path, {'latest_portfolio': self._portfolio})


class FakeDB:
    def __init__(self, portfolio, strategy_docs, execution_sink, trading_mode='paper'):
        self._portfolio = portfolio
        self._strategy_docs = strategy_docs
        self._execution_sink = execution_sink
        self._trading_mode = trading_mode

    def document(self, path):
        if path == f'positions/{self._trading_mode}':
            return FakePortfolioDocument(path, {'latest_portfolio': self._portfolio})
        raise ValueError(f"Unsupported document path: {path}")

    def collection(self, name):
        if name == 'strategies':
            return FakeStrategyCollection(self._strategy_docs)
        if name == 'executions':
            return FakeExecutionsCollection(self._execution_sink)
        if name == 'positions':
            return FakePositionsCollection(self._trading_mode, self._portfolio)
        raise ValueError(f"Unsupported collection: {name}")


class FakeIBGW:
    async def qualifyContractsAsync(self, contract):
        return [contract]

    def placeOrder(self, contract, order):
        return None


class RecordingIBGW(FakeIBGW):
    def __init__(self):
        self.calls = []
        self._next_order_id = 1

    async def qualifyContractsAsync(self, contract):
        return await super().qualifyContractsAsync(contract)

    def placeOrder(self, contract, order):
        order.orderId = self._next_order_id
        self._next_order_id += 1
        trade = SimpleNamespace(
            order=order,
            contract=contract,
            orderStatus=SimpleNamespace(status='Submitted', remaining=0),
            fills=[]
        )
        self.calls.append(trade)
        return trade


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

    def test_allocation_places_smart_routed_sell_order(self):
        recording_ibgw = RecordingIBGW()
        execution_sink = []
        now = datetime.now(timezone.utc).isoformat()
        portfolio_doc = {
            'updated_at': now,
            'holdings': [
                {
                    'contract': {
                        'conId': 2001,
                        'symbol': 'QQQ',
                        'secType': 'STK',
                        'exchange': 'NASDAQ',
                        'currency': 'USD'
                    },
                    'quantity': 10
                }
            ],
            'open_orders': []
        }
        env = SimpleNamespace(
            db=FakeDB(portfolio_doc, [], execution_sink),
            ibgw=recording_ibgw,
            logging=SimpleNamespace(
                info=lambda *args, **kwargs: None,
                warning=lambda *args, **kwargs: None,
                error=lambda *args, **kwargs: None
            ),
            trading_mode='paper',
            env={'K_REVISION': 'localhost'},
            config={}
        )

        result = asyncio.run(Allocation(env, dryRun=False)._core_async())

        self.assertEqual(len(recording_ibgw.calls), 1)
        trade = recording_ibgw.calls[0]
        self.assertEqual(trade.order.action, 'SELL')
        self.assertEqual(trade.order.totalQuantity, 10)
        self.assertEqual(trade.contract.exchange, 'SMART')
        self.assertEqual(trade.contract.primaryExchange, 'NASDAQ')
        self.assertEqual(result['orders'][0]['status'], 'Submitted')

    def test_allocation_skips_order_when_contract_missing(self):
        recording_ibgw = RecordingIBGW()
        execution_sink = []
        now = datetime.now(timezone.utc).isoformat()
        portfolio_doc = {
            'updated_at': now,
            'holdings': [],
            'open_orders': []
        }
        strategy_doc = FakeStrategyDoc(
            'orphan',
            {'enabled': True},
            {
                'status': 'success',
                'updated_at': now,
                'target_positions': [
                    {
                        'symbol': 'QQQ',
                        'secType': 'STK',
                        'exchange': 'NASDAQ',
                        'currency': 'USD',
                        'quantity': 5
                    }
                ]
            }
        )
        env = SimpleNamespace(
            db=FakeDB(portfolio_doc, [strategy_doc], execution_sink),
            ibgw=recording_ibgw,
            logging=SimpleNamespace(
                info=lambda *args, **kwargs: None,
                warning=lambda *args, **kwargs: None,
                error=lambda *args, **kwargs: None
            ),
            trading_mode='paper',
            env={'K_REVISION': 'localhost'},
            config={}
        )

        result = asyncio.run(Allocation(env, dryRun=False)._core_async())

        self.assertEqual(len(recording_ibgw.calls), 0)
        self.assertEqual(result['orders'], [])


if __name__ == '__main__':
    unittest.main()
