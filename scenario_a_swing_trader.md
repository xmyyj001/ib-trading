# 场景 A: 日线级别的“波段/趋势交易者” (最终完整版)

## 1. 目标与理念

此方案的目标是构建一个稳健的、低频的自动化交易系统。它在每日收盘后进行决策，旨在抓住持续数天或更长时间的市场趋势，并接受持仓隔夜。该模式逻辑简单，信号稳定，能有效过滤盘中噪音，且云资源和交易成本都非常低。

## 2. Firestore 与 Scheduler 设定

### 2.1 Firestore 配置

为适应隔夜持仓和盘后下单的模式，我们需要调整订单参数，并增加安全开关。

*   **路径**: `config/common`
*   **建议内容**:

```json
{
  "marketDataType": 2,
  "adaptivePriority": "Normal",
  "tradingEnabled": true,
  "defaultOrderTif": "GTC",
  "defaultOrderType": "LMT",
  "enforceFlatEod": false,
  "exposure": {
    "overall": 0.9,
    "strategies": {
      "spymacdvixy": 1.0
    }
  },
  "retryCheckMinutes": 1440
}
```

### 2.2 Cloud Scheduler 设定

您只需要一个 Cloud Scheduler 作业来触发交易。

*   **作业名称**: `EOD-Allocation-Job`
*   **频率 (Cron)**: `15 16 * * 1-5` (美东时间，每个交易日下午 4:15)
*   **目标类型**: `HTTP`
*   **URL**: 您的 Cloud Run 服务 URL
*   **HTTP 方法**: `POST`
*   **请求正文 (Body)**: `{"strategies": ["spymacdvixy"]}`
*   **认证**: 选择 `OIDC 令牌`，并使用与 Cloud Run 服务关联的服务账号。

---

## 3. 核心代码实现 (基础版本)

此基础版本实现了场景A的核心交易逻辑，即在收盘后运行，并能根据配置使用不同的订单类型（如LMT/MOC）。但请注意，此版本**未处理**在途的隔夜订单（GTC），在连续运行时有重复下单的风险。后续章节将解决此问题。

### `cloud-run/application/app/intents/allocation.py` (基础版本)

```python
from datetime import datetime, timedelta
import dateparser
from ib_insync import MarketOrder, LimitOrder, Order, TagValue
import ib_insync

from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES

class Allocation(Intent):

    _dry_run = False
    _order_properties = {}
    _strategies = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._dry_run = kwargs.get('dryRun', self._dry_run)
        self._order_properties = kwargs.get('orderProperties', {})
        strategies = kwargs.get('strategies', [])
        if any([s not in STRATEGIES.keys() for s in strategies]):
            raise KeyError(f"Unknown strategies: {','.join([s for s in strategies if s not in STRATEGIES.keys()])}")
        self._strategies = {s: STRATEGIES[s] for s in strategies}
        self._activity_log.update(dryRun=self._dry_run, orderProperties=self._order_properties, strategies=strategies)

    def _core(self):
        if (overall_exposure := self._env.config['exposure']['overall']) == 0:
            self._env.logging.info('Aborting allocator as overall exposure is 0')
            return

        self._env.logging.info(f"Running allocator for {', '.join(self._strategies.keys())}...")
        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        strategies_instances = []
        for k, v in self._strategies.items():
            if strategy_exposure := self._env.config['exposure']['strategies'].get(k, 0):
                self._env.logging.info(f'Getting signals for {k}...')
                try:
                    strategies_instances.append(v(base_currency=base_currency, exposure=net_liquidation * overall_exposure * strategy_exposure))
                except Exception as exc:
                    self._env.logging.error(f'{exc.__class__.__name__} running strategy {k}: {exc}')
        
        trades = Trade(strategies_instances)
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

            orders = trades.place_orders(OrderClass,
                                         order_params=order_params,
                                         order_properties={**self._order_properties, 'tif': self._env.config.get('defaultOrderTif', 'DAY')})
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
```

---

## 4. 安全与干预机制 (最低标准)

此章节为基础版本增加必要的安全功能，是生产投用的最低要求。

### 4.1 “紧急制动”开关 (Kill Switch)

**实现**: 修改 `intent.py` 基类，在执行任何操作前检查 Firestore 中的 `tradingEnabled` 标志。

**完整代码**: `cloud-run/application/app/intents/intent.py`
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

### 4.2 核心监控与警报

**实现**: 通过 GCP 控制台设置，无需编码。
1.  **警报一 (系统“硬”故障)**: 在 Monitoring 中创建基于 `Cloud Run Revision` 指标的警报，当 `Request Count` 的 `response_code_class` 为 `5xx` 时触发。
2.  **警报二 (系统“静默”故障)**: 在 Logging 中创建基于 `textPayload:"Orders placed"` 的日志指标，当该指标在1天内小于1时触发警报。

### 4.3 手动状态同步工具 (`/reconcile`)

**实现**: 新增一个 `/reconcile` 意图，用于在手动干预后，强制将系统状态与券商同步。

**新增文件**: `cloud-run/application/app/intents/reconcile.py`
```python
from intents.intent import Intent

class Reconcile(Intent):
    def _core(self):
        self._env.logging.warning("Starting manual reconciliation...")
        ib_positions = self._env.ibgw.reqPositions()
        broker_portfolio = {str(p.contract.conId): p.position for p in ib_positions}
        holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
        for doc in list(holdings_ref.stream()):
            doc.reference.delete()
        if broker_portfolio:
            recon_doc_ref = holdings_ref.document('reconciled_holdings')
            recon_doc_ref.set(broker_portfolio)
        result = {"status": "Reconciliation complete", "reconciledPortfolio": broker_portfolio}
        self._activity_log.update(**result)
        return result
```

**修改文件**: `cloud-run/application/app/main.py` (注册新意图)
```python
# ... (部分 imports)
from intents.allocation import Allocation
from intents.reconcile import Reconcile
# ... (其他 intents)

INTENTS = {
    'allocation': Allocation,
    'reconcile': Reconcile,
    # ... (其他 intents)
}
```

---

## 5. 进阶完善：处理隔夜订单 (GTC) 与状态管理

此最终版本解决了基础版本中的核心缺陷，能够正确管理在途的隔夜订单，是进行波段交易的健壮实现。

### 升级文件 1: `cloud-run/application/app/lib/trading.py`

```python
from abc import ABC
from datetime import datetime, timedelta, timezone
import ib_insync
from google.cloud.firestore_v1 import DELETE_FIELD
from lib.environment import Environment
from lib.gcp import GcpModule

# (Instrument, Contract, Forex, Future, Index, Stock, InstrumentSet 不变)

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
                self._trades[k]['lmtPrice'] = v.get('lmtPrice', 0)
                self._trades[k]['quantity'] = self._trades[k].get('quantity', 0) + v['quantity']
                self._trades[k]['source'] = self._trades[k].get('source', {})
                self._trades[k]['source'][strategy.id] = v['quantity']
        self._trades = {k: v for k, v in self._trades.items() if v['quantity'] != 0}

    def _log_trades(self, trades=None):
        # (此方法在之前的分析中未详细展开，此处保持项目原样或根据需要实现)
        pass

    def place_orders(self, order_type=ib_insync.MarketOrder, order_params=None, order_properties=None):
        order_properties = order_properties or {}
        order_params = order_params or {}
        perm_ids = []
        for v in self._trades.values():
            if order_type == ib_insync.LimitOrder:
                order_params['lmtPrice'] = v['lmtPrice']
            
            # 将策略ID作为orderRef传递，用于后续识别订单来源
            if 'orderRef' not in order_properties and 'source' in v:
                order_properties['orderRef'] = list(v['source'].keys())[0]

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
            for k, v_tuple in self._signals.items():
                if (c := self._contracts[k]).tickers is None:
                    c.get_tickers()
            self._get_currencies(self._base_currency)

            self._target_positions = {}
            for k, v_tuple in self._signals.items():
                weight, price = v_tuple
                if weight != 0 and price > 0:
                    self._target_positions[k] = round(self._exposure * weight
                                     / (price * int(self._contracts[k].contract.multiplier) * self._fx[self._contracts[k].contract.currency]))
                else:
                    self._target_positions[k] = 0
        else:
            self._target_positions = {k: 0 for k in self._signals.keys()}

    def _calculate_trades(self, virtual_holdings):
        self._trades = {}
        for k, v in self._target_positions.items():
            trade_qty = v - virtual_holdings.get(k, 0)
            if trade_qty != 0:
                self._trades[k] = {'quantity': trade_qty, 'lmtPrice': self._signals[k][1]}
        self._env.logging.info(f"Trades for {self._id}: { {self._contracts[k].local_symbol: v['quantity'] for k, v in self._trades.items()} }")

    def _get_signals(self):
        # This method must now return a dict of {conId: (weight, price)}
        # Example: return {12345: (1.0, 450.50)} for long SPY at 450.50
        self._signals = { k: (0, 0) for k in self._holdings.keys() }

    # ... (other methods like _get_holdings, _get_currencies, _register_contracts, _setup remain unchanged) ...
```

### 升级文件 3: `cloud-run/application/app/intents/allocation.py` (最终版)

```python
from datetime import datetime, timedelta
import dateparser
from ib_insync import LimitOrder
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

            new_action = 'BUY' if trade_for_contract['quantity'] > 0 else 'SELL'
            if new_action != order.action:
                self._env.logging.warning(f"Cancelling stale GTC order {order.orderId} for {order.action} {order.totalQuantity} of conId {conId}")
                self._env.ibgw.cancelOrder(order)

    def _core(self):
        all_open_orders = self._env.ibgw.reqOpenOrders()
        self._env.ibgw.sleep(2)

        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        strategies_instances = []
        for k, v in self._strategies.items():
            if strategy_exposure := self._env.config['exposure']['strategies'].get(k, 0):
                self._env.logging.info(f'Getting signals for {k}...')
                try:
                    strategy_open_orders = {o.contract.conId: o for o in all_open_orders if o.orderRef == k}
                    strategies_instances.append(v(base_currency=base_currency, 
                                        exposure=net_liquidation * overall_exposure * strategy_exposure,
                                        open_orders=strategy_open_orders,
                                        _id=k))
                except Exception as exc:
                    self._env.logging.error(f'{exc.__class__.__name__} running strategy {k}: {exc}')
        
        trades = Trade(strategies_instances)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")

        if not self._dry_run:
            self._cancel_stale_orders(all_open_orders, trades.trades)
            OrderClass = LimitOrder
            orders = trades.place_orders(OrderClass)
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
```

---

## 附录: 初始化Firestore的推荐脚本 (场景A)

在首次部署或需要重置数据库配置时，推荐使用以下脚本来初始化 Firestore。此脚本专为**场景A（波段交易）**定制，包含了所有必要的安全和交易参数。

**使用方法**:
1.  将以下内容保存或覆盖到 `cloud-run/application/app/lib/init_firestore.py` 文件中。
2.  在您的终端中，进入 `cloud-run/application/app` 目录。
3.  运行命令: `python lib/init_firestore.py [YOUR_PROJECT_ID]`

### `init_firestore.py` (场景A版本)

```python
import sys
from google.cloud import firestore

if len(sys.argv) < 2:
    print("错误：请提供项目ID作为第一个参数。")
    print("用法: python init_firestore.py YOUR_PROJECT_ID")
    sys.exit(1)

project_id = sys.argv[1]
print(f"正在为项目 '{project_id}' 初始化 Firestore 配置 (场景A: 波段交易)...")

db = firestore.Client(project=project_id)

config_data = {
    "common": {
        "tradingEnabled": False,
        "enforceFlatEod": False,
        "marketDataType": 2,
        "defaultOrderType": "LMT",
        "defaultOrderTif": "GTC",
        "retryCheckMinutes": 1440,
        "exposure": {
            "overall": 0.9,
            "strategies": {
                "spymacdvixy": 1.0,
                "dummy": 1.0
            }
        }
    },
    "paper": {
        "account": "[REPLACE_WITH_YOUR_PAPER_ACCOUNT]"
    },
    "live": {
        "account": "[REPLACE_WITH_YOUR_LIVE_ACCOUNT]"
    }
}

def initialize_firestore():
    """Writes the defined configuration to Firestore, overwriting existing docs."""
    for doc_id, data in config_data.items():
        doc_ref = db.collection("config").document(doc_id)
        try:
            doc_ref.set(data)
            print(f"成功创建/更新文档: 'config/{doc_id}'")
        except Exception as e:
            print(f"错误：写入文档 'config/{doc_id}'失败: {e}")
            sys.exit(1)
    
    print("\nFirestore 配置初始化完成。")
    print("重要提示: 请记得到 Firestore 控制台将 config/common -> tradingEnabled 设置为 true 以开启交易。")

if __name__ == "__main__":
    initialize_firestore()
```
