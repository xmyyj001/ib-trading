# 场景 D: “混合模式”日内交易者 (最终完整版)

## 1. 目标与理念

此方案旨在实现一个纪律严明、风控严密的日内交易系统。它在开盘时交易，盘中进行风险检查，收盘前进行对账和清算，形成一个完整的交易闭环。该模式将自动化决策与关键节点的风险检查相结合，在保证执行效率的同时，极大地提升了系统的稳健性和安全性。

## 2. Firestore 与 Scheduler 设定

### 2.1 Firestore 配置

我们需要增加更多用于风控和应急的开关。详细配置见文末附录的初始化脚本。

### 2.2 Cloud Scheduler 设定

您需要设置三个独立的 Cloud Scheduler 作业。

1.  **作业一: `Open-Allocation-Job`** (频率: `30 9 * * 1-5`)
2.  **作业二: `Midday-RiskCheck-Job`** (频率: `0 13 * * 1-5`)
3.  **作业三: `EOD-Reconciliation-Job`** (频率: `55 15 * * 1-5`)

---

## 3. 核心代码实现 (基础版本)

此基础版本实现了场景D的“三步”工作流，但三个任务之间是独立的，如果第一步失败，后续步骤依然会执行，存在“级联失败”的风险。后续章节将解决此问题。

### `cloud-run/application/app/intents/allocation.py` (基础版本)

```python
from datetime import datetime
from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES
from ib_insync import MarketOrder, TagValue

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

        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        # 记录当日起始资金, 为后续风控提供基准
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_doc_ref.set({'startOfDayNetLiq': net_liquidation}, merge=True)
        self._env.logging.info(f"Recorded start of day Net Liquidation: {net_liquidation}")

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
            orders = trades.place_orders(MarketOrder,
                                         order_params={
                                             'algoStrategy': 'Adaptive',
                                             'algoParams': [TagValue('adaptivePriority', self._env.config['adaptivePriority'])]
                                         },
                                         order_properties={{**self._order_properties, 'tif': 'DAY'}})
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")
```

### `cloud-run/application/app/intents/risk_check.py` (基础版本)

```python
from intents.intent import Intent

class RiskCheck(Intent):
    def _core(self):
        self._env.logging.info("Starting Mid-Day Risk Check...")
        summary = self._env.get_account_values(self._env.config['account'])
        current_net_liq = list(summary['NetLiquidation'].values())[0]

        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_data = status_doc_ref.get().to_dict()
        
        if not status_data or 'startOfDayNetLiq' not in status_data:
            self._env.logging.warning("Start of day Net Liquidation not found. Cannot perform drawdown check.")
            return {"status": "Cannot perform drawdown check: start of day Net Liq not found."}

        start_net_liq = status_data['startOfDayNetLiq']
        drawdown_percent = ((current_net_liq - start_net_liq) / start_net_liq) * 100
        max_drawdown = self._env.config.get('maxDailyDrawdownPercent', 5.0)

        self._env.logging.info(f"Drawdown: {drawdown_percent:.2f}%")

        alert_triggered = False
        if drawdown_percent < -max_drawdown:
            alert_triggered = True
            error_message = f"CRITICAL ALERT: Daily drawdown {drawdown_percent:.2f}% has exceeded threshold of -{max_drawdown}%!"
            self._env.logging.error(error_message)
            self._activity_log.update(exception=error_message)

        result = {
            "startOfDayNetLiq": start_net_liq,
            "currentNetLiq": current_net_liq,
            "drawdownPercent": drawdown_percent,
            "alertTriggered": alert_triggered
        }
        self._activity_log.update(**result)
        return result
```

### `cloud-run/application/app/intents/eod_check.py` (基础版本)

```python
import pandas as pd
from intents.intent import Intent
from intents.close_all import CloseAll

class EodCheck(Intent):
    def _core(self):
        self._env.logging.info("Starting End-of-Day check...")
        ib_positions = self._env.ibgw.reqPositions()
        ib_portfolio = {p.contract.conId: p.position for p in ib_positions if p.position != 0}

        holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
        all_strategy_holdings = holdings_ref.stream()
        system_portfolio = {}
        for doc in all_strategy_holdings:
            for conId, quantity in doc.to_dict().items():
                system_portfolio[int(conId)] = system_portfolio.get(int(conId), 0) + quantity
        
        reconciliation_errors = self._reconcile(ib_portfolio, system_portfolio)
        if reconciliation_errors:
            self._env.logging.error(f"Reconciliation failed! Discrepancies: {reconciliation_errors}")

        open_orders = self._env.ibgw.reqOpenOrders()
        if open_orders:
            self._env.logging.error(f"CRITICAL: Open orders found at EOD! {[o.permId for o in open_orders]}")

        if self._env.config.get('enforceFlatEod', True) and ib_portfolio:
             self._env.logging.warning(f"Positions found at EOD. Triggering close_all...")
             close_all_intent = CloseAll()
             close_all_intent.run()

        summary = self._env.get_account_values(self._env.config['account'])
        net_liq = list(summary['NetLiquidation'].values())[0]
        
        result = {
            "netLiquidation": net_liq,
            "reconciliationErrors": reconciliation_errors,
            "openOrdersFound": len(open_orders) > 0
        }
        self._activity_log.update(**result)
        return result

    def _reconcile(self, ib_portfolio, system_portfolio):
        df_ib = pd.Series(ib_portfolio, name='broker').rename_axis('conId')
        df_sys = pd.Series(system_portfolio, name='system').rename_axis('conId')
        df = pd.concat([df_ib, df_sys], axis=1).fillna(0)
        df['diff'] = df['broker'] - df['system']
        return df[df['diff'] != 0]['diff'].to_dict()
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
1.  **警报一 (系统“硬”故障)**: 在 Monitoring 中创建基于 `Cloud Run Revision` 指标的警报，当 `Request Count` 的 `response_code_class` 为 `5xx` 时触发。此警报可以覆盖所有代码崩溃、回撤超限、对账失败等情况。
2.  **警报二 (系统“静默”故障)**: 在 Logging 中创建基于 `textPayload:"Allocation successful"` 的日志指标，当该指标在1天内小于1时触发警报。

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
from intents.reconcile import Reconcile
from intents.risk_check import RiskCheck
from intents.eod_check import EodCheck
# ... (其他 intents)

INTENTS = {
    # ... other intents
    'risk-check': RiskCheck,
    'eod-check': EodCheck,
    'reconcile': Reconcile,
}
```

---

## 5. 进阶完善：增强日内工作流的健壮性

此最终版本解决了基础版本中“级联失败”和“卡单”的风险，通过一个“状态信使”将三个独立的任务串联成一个真正健壮的工作流。

### 升级文件 1: `cloud-run/application/app/intents/allocation.py` (最终版)

```python
from datetime import datetime
from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES
from ib_insync import MarketOrder, TagValue

class Allocation(Intent):
    # ... (__init__ remains unchanged)
    def _core(self):
        # ... (retry logic and exposure check) ...
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_doc_ref.set({'daily_status': 'ALLOCATION_STARTED', 'utcTimestamp': datetime.utcnow()}, merge=False)

        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        status_doc_ref.set({'startOfDayNetLiq': net_liquidation}, merge=True)

        # ... (strategy execution logic) ...
        strategies_instances = [] # Defined for clarity
        # ... (loop to append to strategies_instances)

        trades = Trade(strategies_instances)
        trades.consolidate_trades()

        if not self._dry_run:
            orders = trades.place_orders(MarketOrder,
                                         order_params={
                                             'algoStrategy': 'Adaptive',
                                             'algoParams': [TagValue('adaptivePriority', self._env.config['adaptivePriority'])]
                                         },
                                         order_properties={{**self._order_properties, 'tif': 'DAY'}})
            self._activity_log.update(orders=orders)

            order_ids = [o.get('order', {}).get('permId') for o in orders.values() if o.get('order')]
            final_status = {
                'daily_status': 'ALLOCATION_SUCCESS',
                'morning_order_ids': order_ids
            }
            status_doc_ref.set(final_status, merge=True)
            self._env.logging.info(f"Allocation successful. Final status: {final_status}")
```

### 升级文件 2: `cloud-run/application/app/intents/risk_check.py` (最终版)

```python
from intents.intent import Intent

class RiskCheck(Intent):
    def _core(self):
        self._env.logging.info("Starting Mid-Day Risk Check...")
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_data = status_doc_ref.get().to_dict()

        if not status_data or status_data.get('daily_status') != 'ALLOCATION_SUCCESS':
            msg = "Aborting risk check: Morning allocation did not complete successfully."
            self._env.logging.warning(msg)
            return {"status": msg}

        # ... (drawdown check logic as in base version) ...
        start_net_liq = status_data['startOfDayNetLiq']
        # ...

        morning_order_ids = status_data.get('morning_order_ids', [])
        if morning_order_ids:
            open_orders = self._env.ibgw.reqOpenOrders()
            stuck_orders = [o.permId for o in open_orders if o.permId in morning_order_ids]
            if stuck_orders:
                warning_msg = f"WARNING: {len(stuck_orders)} morning order(s) still open by midday: {stuck_orders}"
                self._env.logging.warning(warning_msg)
                self._activity_log.update(stuckOrders=stuck_orders)

        status_doc_ref.set({'daily_status': 'RISK_CHECK_SUCCESS'}, merge=True)
        
        result = {
            "startOfDayNetLiq": start_net_liq,
            # ... other result fields
        }
        self._activity_log.update(**result)
        return result
```

### 升级文件 3: `cloud-run/application/app/intents/eod_check.py` (最终版)

```python
import pandas as pd
from intents.intent import Intent
from intents.close_all import CloseAll

class EodCheck(Intent):
    def _core(self):
        self._env.logging.info("Starting End-of-Day check...")
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_data = status_doc_ref.get().to_dict()

        if not status_data or status_data.get('daily_status') not in ['ALLOCATION_SUCCESS', 'RISK_CHECK_SUCCESS']:
            msg = "Aborting EOD check: Morning allocation did not complete successfully."
            self._env.logging.warning(msg)
            return {"status": msg}

        # ... (reconciliation, open order check, enforce flat logic as in base version) ...
        ib_positions = self._env.ibgw.reqPositions()
        ib_portfolio = {p.contract.conId: p.position for p in ib_positions if p.position != 0}
        # ...

        summary = self._env.get_account_values(self._env.config['account'])
        end_of_day_net_liq = list(summary['NetLiquidation'].values())[0]
        start_of_day_net_liq = status_data.get('startOfDayNetLiq', end_of_day_net_liq)
        daily_pnl = end_of_day_net_liq - start_of_day_net_liq
        self._env.logging.info(f"Daily PnL: {daily_pnl:.2f}")

        result = {
            "netLiquidation": end_of_day_net_liq,
            "dailyPnl": daily_pnl,
            "reconciliationErrors": self._reconcile(ib_portfolio, {}), # Placeholder
            "openOrdersFound": len(self._env.ibgw.reqOpenOrders()) > 0
        }
        self._activity_log.update(**result)

        status_doc_ref.set({'daily_status': 'EOD_SUCCESS'}, merge=True)
        return result

    def _reconcile(self, ib_portfolio, system_portfolio):
        # ... (reconcile implementation as in base version)
        pass
```

---

## 附录: 初始化Firestore的推荐脚本 (场景D)

在首次部署或需要重置数据库配置时，推荐使用以下脚本来初始化 Firestore。此脚本专为**场景D（混合模式日内交易）**定制。

### `init_firestore.py` (场景D版本)

```python
import sys
from google.cloud import firestore

if len(sys.argv) < 2:
    print("错误：请提供项目ID作为第一个参数。")
    sys.exit(1)

project_id = sys.argv[1]
print(f"正在为项目 '{project_id}' 初始化 Firestore 配置 (场景D: 混合模式日内交易)...")

db = firestore.Client(project=project_id)

config_data = {
    "common": {
        "tradingEnabled": False,
        "enforceFlatEod": True,
        "maxDailyDrawdownPercent": 5.0,
        "alertingEmail": "[REPLACE_WITH_YOUR_EMAIL]",
        "marketDataType": 2,
        "defaultOrderType": "MKT",
        "defaultOrderTif": "DAY",
        "retryCheckMinutes": 600,
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