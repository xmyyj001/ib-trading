# 场景 A: 日线级别的“波段/趋势交易者”

## 1. 目标与理念

此方案的目标是构建一个稳健的、低频的自动化交易系统。它在每日收盘后进行决策，旨在抓住持续数天或更长时间的市场趋势，并接受持仓隔夜。该模式逻辑简单，信号稳定，能有效过滤盘中噪音，且云资源和交易成本都非常低。

## 2. Firestore 配置

为适应隔夜持仓和盘后下单的模式，我们需要调整订单参数。

*   **路径**: `config/common`
*   **建议内容**:

```json
{
  "marketDataType": 2,
  "adaptivePriority": "Normal",
  "tradingEnabled": true,
  "defaultOrderTif": "GTC",
  "defaultOrderType": "LMT",
  "exposure": {
    "overall": 0.9,
    "strategies": {
      "spymacdvixy": 1.0
    }
  },
  "retryCheckMinutes": 1440
}
```

## 3. Cloud Scheduler 设定

您只需要一个 Cloud Scheduler 作业来触发交易。

*   **作业名称**: `EOD-Allocation-Job`
*   **频率 (Cron)**: `15 16 * * 1-5` (美东时间，每个交易日下午 4:15)
*   **目标类型**: `HTTP`
*   **URL**: 您的 Cloud Run 服务 URL
*   **HTTP 方法**: `POST`
*   **HTTP Headers**: `Content-Type: application/json`
*   **请求正文 (Body)**:
    ```json
    {
        "strategies": ["spymacdvixy"]
    }
    ```
*   **认证**: 选择 `OIDC 令牌`，并使用与 Cloud Run 服务关联的服务账号。

## 4. 核心代码实现 (原始版本)

此方案的核心是让下单逻辑能够适应更多样的订单类型，这些类型从 Firestore 配置中动态读取。

### 修改文件: `cloud-run/application/app/intents/allocation.py`

```python
from datetime import datetime, timedelta

import dateparser
from ib_insync import MarketOrder, LimitOrder, Order, TagValue
import ib_insync

from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES # This will now be dynamically populated


class Allocation(Intent):

    _dry_run = False
    _order_properties = {}
    _strategies = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._dry_run = kwargs.get('dryRun', self._dry_run) if kwargs is not None else self._dry_run
        self._order_properties = kwargs.get('orderProperties', self._order_properties) if kwargs is not None else self._order_properties
        strategies = kwargs.get('strategies', [])
        if any([s not in STRATEGIES.keys() for s in strategies]):
            raise KeyError(f"Unknown strategies: {','.join([s for s in strategies if s not in STRATEGIES.keys()])}")
        self._strategies = {s: STRATEGIES[s] for s in strategies}
        self._activity_log.update(dryRun=self._dry_run, orderProperties=self._order_properties, strategies=strategies)

    def _core(self):
        if (overall_exposure := self._env.config['exposure']['overall']) == 0:
            self._env.logging.info('Aborting allocator as overall exposure is 0')
            return

        if self._env.config['retryCheckMinutes']:
            # check if agent has created an order before (prevent trade repetition)
            query = self._env.db.collection('activity') \
                .where('tradingMode', '==', self._env.trading_mode) \
                .where('signature', '==', self._signature) \
                .where('timestamp', '>', datetime.utcnow() - timedelta(minutes=self._env.config['retryCheckMinutes'])) \
                .order_by('timestamp') \
                .order_by('orders')
            if len(list(query.get())):
                self._env.logging.warning('Agent has run before.')
                return

        self._env.logging.info(f"Running allocator for {', '.join(self._strategies.keys())}...")

        # get base currency and net liquidation value
        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        # get signals for all strategies
        strategies = []
        for k, v in self._strategies.items():
            if strategy_exposure := self._env.config['exposure']['strategies'].get(k, 0):
                self._env.logging.info(f'Getting signals for {k}...')
                try:
                    strategies.append(v(base_currency=base_currency, exposure=net_liquidation * overall_exposure * strategy_exposure))
                except Exception as exc:
                    self._env.logging.error(f'{exc.__class__.__name__} running strategy {k}: {exc}')
        # log activity
        self._activity_log.update(**{
            'signals': {s.id: {s.contracts[k].local_symbol: v for k, v in s.signals.items()} for s in strategies},
            'holdings': {s.id: {s.contracts[k].local_symbol: v for k, v in s.holdings.items()} for s in strategies},
            'targetPositions': {s.id: {s.contracts[k].local_symbol: v for k, v in s.target_positions.items()} for s in strategies},
            'fx': {k: v for s in strategies for k, v in s.fx.items()},
            'contractIds': {v.contract.localSymbol: k for s in strategies for k, v in s.contracts.items()}
        })

        # consolidate trades over strategies, remembering to which strategies a trade belongs
        trades = Trade(strategies)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")

        if not self._dry_run:
            order_type_str = self._env.config.get('defaultOrderType', 'MKT')
            order_type_map = {
                'MKT': MarketOrder,
                'LMT': LimitOrder,
                'MOC': Order,
            }
            OrderClass = order_type_map.get(order_type_str, MarketOrder)
            order_params = {}
            if order_type_str == 'MOC':
                order_params = {'orderType': 'MOC'}

            if 'goodAfterTime' in self._order_properties:
                self._order_properties.update(goodAfterTime=dateparser.parse(self._order_properties['goodAfterTime']).strftime('%Y%m%d %H:%M:%S %Z'))

            orders = trades.place_orders(OrderClass,
                                         order_params=order_params,
                                         order_properties={**self._order_properties, 'tif': self._env.config.get('defaultOrderTif', 'DAY')})
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
```

## 5. 安全与干预机制 (最低标准)

此方案虽然简单，但仍需具备最核心的风险控制能力，以满足生产投用的最低安全标准。

### 5.1 “紧急制动”开关 (Kill Switch)

这是最高优先级的安全机制，允许您在盘中或任何时候立即停止系统所有未来的交易活动，而无需修改或停止 Cloud Scheduler。

**实现**: 在 `intent.py` 基类中加入一个检查。每次运行任何意图（如 `/allocation`）时，它都会首先读取您在 Firestore `config/common` 中设置的 `tradingEnabled` 标志。如果为 `false`，则中止一切操作。

**需要修改的文件**: `cloud-run/application/app/intents/intent.py`

**完整代码**:

```python
import json
from datetime import datetime
from hashlib import md5

from lib.environment import Environment


class Intent:

    _activity_log = {}

    def __init__(self, **kwargs):
        self._env = Environment()

        hashstr = self._env.env.get('K_REVISION', 'localhost') + self.__class__.__name__ + json.dumps(kwargs, sort_keys=True)
        self._signature = md5(hashstr.encode()).hexdigest()

        self._activity_log = {
            'agent': self._env.env.get('K_REVISION', 'localhost'),
            'config': self._env.config,
            'exception': None,
            'intent': self.__class__.__name__,
            'signature': self._signature,
            'tradingMode': self._env.trading_mode
        }

    def _core(self):
        return {'currentTime': self._env.ibgw.reqCurrentTime().isoformat()}

    def _log_activity(self):
        if len(self._activity_log):
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(e)
                self._env.logging.info(self._activity_log)

    def run(self):
        retval = {}
        exc = None
        try:
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading is globally disabled by kill switch in Firestore config.")

            self._env.ibgw.start_and_connect()
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = self._core()
        except Exception as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._env.logging.error(error_str)
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            self._env.ibgw.stop_and_terminate()
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
            if exc is not None:
                raise exc
            self._env.logging.info('Done.')
            return retval or {**self._activity_log, 'timestamp': self._activity_log['timestamp'].isoformat()}
```

### 5.2 核心监控与警报 (通过GCP控制台设置)

您无需编写代码，只需在 Google Cloud 控制台进行几次点击即可建立最核心的监控。

1.  **警报一：系统“硬”故障**
2.  **警报二：系统“静默”故障 (心跳检测)**

(设置步骤与场景D文档中描述的完全相同)

### 5.3 手动状态同步工具 (`/reconcile`)

*   **目的**: 当您手动干预交易或发生拆股等事件后，一键将系统的持仓记录（Firestore）与券商的真实持仓同步。这是一个重要的手动修复工具。
*   **实现**: 新增一个 `/reconcile` 意图。

**新增文件**: `cloud-run/application/app/intents/reconcile.py`

**修改文件**: `cloud-run/application/app/main.py` (注册新意图)

(实现代码与场景D文档中描述的完全相同)

## 6. 进阶完善：处理隔夜订单 (GTC) 与状态管理

对于波段交易，最大的挑战来自于如何管理可能跨越多日都未成交的“在途订单”（GTC订单）。如果系统不识别这些在途订单，第二天当策略产生相同信号时，就会重复下单。以下是解决此问题的完整代码升级方案。

### 升级文件 1: `cloud-run/application/app/lib/trading.py`

我们需要修改 `place_orders` 方法，使其能够处理限价单（LMT）的价格。

```python
from abc import ABC
from datetime import datetime, timedelta, timezone
import ib_insync
from google.cloud.firestore_v1 import DELETE_FIELD

from lib.environment import Environment
from lib.gcp import GcpModule

# ... (Instrument, Contract, etc. classes remain unchanged) ...

class Trade:

    _trades = {}
    _trade_log = {}

    def __init__(self, strategies=()):
        self._env = Environment()
        self._strategies = strategies

    @property
    def trades(self):
        return self._trades

    def consolidate_trades(self):
        self._trades = {}
        for strategy in self._strategies:
            for k, v in strategy.trades.items():
                if k not in self._trades:
                    self._trades[k] = {}
                self._trades[k]['contract'] = strategy.contracts[k]
                self._trades[k]['lmtPrice'] = v['lmtPrice']
                if 'quantity' in self._trades[k]:
                    self._trades[k]['quantity'] += v['quantity']
                else:
                    self._trades[k]['quantity'] = v['quantity']
                if 'source' in self._trades[k]:
                    self._trades[k]['source'][strategy.id] = v['quantity']
                else:
                    self._trades[k]['source'] = {strategy.id: v['quantity']}

        self._trades = {k: v for k, v in self._trades.items() if v['quantity'] != 0}

    def _log_trades(self, trades=None):
        # ... (this method remains unchanged) ...
        pass

    def place_orders(self, order_type=ib_insync.MarketOrder, order_params=None, order_properties=None):
        order_properties = order_properties or {}
        order_params = order_params or {}

        perm_ids = []
        for v in self._trades.values():
            # Add lmtPrice if it is a Limit Order
            if order_type == ib_insync.LimitOrder:
                order_params['lmtPrice'] = v['lmtPrice']

            order = self._env.ibgw.placeOrder(v['contract'].contract,
                                              order_type(action='BUY' if v['quantity'] > 0 else 'SELL',
                                                         totalQuantity=abs(v['quantity']), 
                                                         **order_params).update(**{'tif': 'GTC', **order_properties}))
            self._env.ibgw.sleep(2)
            perm_ids.append(order.order.permId)
        self._env.logging.debug(f'Order permanent IDs: {perm_ids}')

        self._trade_log = self._log_trades([t for t in self._env.ibgw.trades() if t.order.permId in perm_ids])

        return self._trade_log
```

### 升级文件 2: `cloud-run/application/app/strategies/strategy.py`

策略基类需要升级，以处理在途订单，并将它们计入“虚拟持仓”。

```python
from lib.environment import Environment
from lib.trading import Contract, Forex, Instrument, InstrumentSet

class Strategy:

    _contracts = {}
    _fx = {}
    _holdings = {}
    _instruments = {}
    _signals = {}
    _target_positions = {}
    _trades = {}
    _open_orders = {}

    def __init__(self, _id=None, open_orders=None, **kwargs):
        self._id = _id or self.__class__.__name__.lower()
        self._env = Environment()
        self._base_currency = kwargs.get('base_currency', None)
        self._exposure = kwargs.get('exposure', 0)
        self._open_orders = open_orders or {}

        self._setup()
        self._get_holdings()
        self._get_signals()

        contract_ids = set([*self._signals.keys()] + [*self._holdings.keys()] + [*self._open_orders.keys()])
        
        # Calculate virtual holdings by adding open orders to current holdings
        virtual_holdings = {**self._holdings}
        for conId, order in self._open_orders.items():
            qty = order.totalQuantity if order.action == 'BUY' else -order.totalQuantity
            virtual_holdings[conId] = virtual_holdings.get(conId, 0) + qty

        self._holdings = {**{cid: 0 for cid in contract_ids}, **self._holdings}
        self._signals = {**{cid: (0, 0) for cid in contract_ids}, **self._signals}
        
        self._calculate_target_positions()
        self._calculate_trades(virtual_holdings)

    # ... (properties remain unchanged) ...

    def _calculate_target_positions(self):
        if self._base_currency is not None and self._exposure:
            for k in self._signals.keys():
                if (c := self._contracts[k]).tickers is None:
                    c.get_tickers()
            self._get_currencies(self._base_currency)

            self._target_positions = {
                k: round(self._exposure * v[0]
                         / (v[1] * int(self._contracts[k].contract.multiplier) * self._fx[self._contracts[k].contract.currency])) if v[0] else 0
                for k, v in self._signals.items()
            }
        else:
            self._target_positions = {k: 0 for k in self._signals.keys()}

    def _calculate_trades(self, virtual_holdings):
        # Trades are calculated against VIRTUAL holdings now
        self._trades = {
            k: {'quantity': v - virtual_holdings.get(k, 0), 'lmtPrice': self._signals[k][1]}
            for k, v in self._target_positions.items()
            if v - virtual_holdings.get(k, 0)
        }
        self._env.logging.info(f"Trades for {self._id}: { {self._contracts[k].local_symbol: v['quantity'] for k, v in self._trades.items()} }")

    # ... (_get_currencies, _get_holdings, _register_contracts remain unchanged) ...

    def _get_signals(self):
        # This method must now return a dict of {conId: (weight, price)}
        self._signals = { k: (0, 0) for k in self._holdings.keys() }

    def _setup(self):
        pass
```

### 升级文件 3: `cloud-run/application/app/intents/allocation.py`

分配意图现在必须获取在途订单，将其传递给策略，并在需要时取消旧订单。

```python
from datetime import datetime, timedelta
import dateparser
from ib_insync import MarketOrder, LimitOrder, Order, TagValue
import ib_insync

from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES

class Allocation(Intent):

    # ... (__init__ remains unchanged) ...

    def _cancel_stale_orders(self, open_orders, trades):
        for conId, order in open_orders.items():
            trade_for_contract = trades.get(conId)
            if trade_for_contract is None:
                continue

            # If new trade has different direction, cancel old order
            new_action = 'BUY' if trade_for_contract['quantity'] > 0 else 'SELL'
            if new_action != order.action:
                self._env.logging.warning(f"Cancelling stale GTC order {order.orderId} for {order.action} {order.totalQuantity} of conId {conId}")
                self._env.ibgw.cancelOrder(order)

    def _core(self):
        # ... (retry logic remains unchanged) ...

        # --- GTC Order Management ---
        # 1. Get all open orders from broker
        all_open_orders = self._env.ibgw.reqOpenOrders()
        self._env.ibgw.sleep(2) # Give time for orders to come in

        # get base currency and net liquidation value
        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        # get signals for all strategies
        strategies = []
        for k, v in self._strategies.items():
            if strategy_exposure := self._env.config['exposure']['strategies'].get(k, 0):
                self._env.logging.info(f'Getting signals for {k}...')
                try:
                    # 2. Filter open orders for the current strategy
                    strategy_open_orders = {o.contract.conId: o for o in all_open_orders if o.orderRef == k}
                    
                    # 3. Pass open orders to the strategy instance
                    strategies.append(v(base_currency=base_currency, 
                                        exposure=net_liquidation * overall_exposure * strategy_exposure,
                                        open_orders=strategy_open_orders,
                                        _id=k))
                except Exception as exc:
                    self._env.logging.error(f'{exc.__class__.__name__} running strategy {k}: {exc}')
        
        # ... (log activity remains unchanged) ...

        trades = Trade(strategies)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")

        if not self._dry_run:
            # 4. Cancel stale orders if signals have flipped
            self._cancel_stale_orders(all_open_orders, trades.trades)

            order_type_str = self._env.config.get('defaultOrderType', 'LMT')
            OrderClass = LimitOrder if order_type_str == 'LMT' else MarketOrder

            # 5. Place new orders, passing the strategy_id as orderRef
            orders = trades.place_orders(OrderClass,
                                         order_properties={'orderRef': list(trades.trades.values())[0]['source'].keys() if trades.trades else ''})
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
```