# 场景 D: “混合模式”日内交易者

## 1. 目标与理念

此方案旨在实现一个纪律严明、风控严密的日内交易系统。它在开盘时交易，盘中进行风险检查，收盘前进行对账和清算，形成一个完整的交易闭环。该模式将自动化决策与关键节点的风险检查相结合，在保证执行效率的同时，极大地提升了系统的稳健性和安全性。

## 2. Firestore 配置

我们需要增加更多用于风控和应急的开关。

*   **路径**: `config/common`
*   **建议内容**:

```json
{
  "marketDataType": 2,
  "adaptivePriority": "Normal",
  "tradingEnabled": true,
  "enforceFlatEod": true,
  "maxDailyDrawdownPercent": 5.0,
  "alertingEmail": "your-email@example.com",
  "exposure": {
    "overall": 0.9,
    "strategies": {
      "spymacdvixy": 1.0
    }
  },
  "retryCheckMinutes": 600
}
```

## 3. Cloud Scheduler 设定

您需要设置三个独立的 Cloud Scheduler 作业。

1.  **作业一: `Open-Allocation-Job`**
2.  **作业二: `Midday-RiskCheck-Job`**
3.  **作业三: `EOD-Reconciliation-Job`**

(频率和目标等设定与前述文档一致)

## 4. 核心代码实现 (原始版本)

此方案涉及新增两个意图文件，并修改三个现有文件。

(此部分代码已在之前的文档中提供，此处省略以保持简洁)

## 5. 安全与干预机制 (最低标准)

此混合模式场景需要更周全的“安全网”，以确保在增加盘中操作的同时，风险依然可控。

(此部分内容已在之前的文档中提供，此处省略以保持简洁)

## 6. 进阶完善：增强日内工作流的健壮性

为应对“卡单”和“级联失败”的风险，我们需要引入一个“日内状态传递”机制，让开盘、盘中、收盘这三个独立的任务能够相互“沟通”，形成一条真正健壮、有状态感知的工作流水线。

**实现思路**: 我们将使用 Firestore 中的一个单独文档 `status/{trading_mode}` 作为“信使”，来记录和传递当日工作流的状态。

### 升级文件 1: `cloud-run/application/app/intents/allocation.py`

开盘的分配意图现在需要负责**开启**并**记录**一天工作的状态。

```python
from datetime import datetime, timedelta
import dateparser
from ib_insync import MarketOrder, TagValue

from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES

class Allocation(Intent):
    # ... (__init__ remains unchanged) ...

    def _core(self):
        # ... (retry logic and exposure check remains unchanged) ...

        # --- 1. 清理前一天的状态 --- 
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_doc_ref.set({'daily_status': 'ALLOCATION_STARTED'}, merge=False) # Overwrite previous day's status

        self._env.logging.info(f"Running allocator for {', '.join(self._strategies.keys())}...")

        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        # --- 2. 记录当日起始状态 --- 
        status_update = {
            'startOfDayNetLiq': net_liquidation,
            'utcTimestamp': datetime.utcnow()
        }
        status_doc_ref.set(status_update, merge=True)
        self._env.logging.info(f"Recorded start of day status: {status_update}")

        # ... (strategy signal generation remains unchanged) ...

        trades = Trade(strategies)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")

        if not self._dry_run:
            orders = trades.place_orders(MarketOrder,
                                         order_params={
                                             'algoStrategy': 'Adaptive',
                                             'algoParams': [TagValue('adaptivePriority', self._env.config['adaptivePriority'])]
                                         },
                                         order_properties={**self._order_properties, 'tif': 'DAY'})
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")

            # --- 3. 记录当日订单ID并更新最终状态 ---
            order_ids = [o.get('order', {}).get('permId') for o in orders.values() if o.get('order')]
            final_status = {
                'daily_status': 'ALLOCATION_SUCCESS',
                'morning_order_ids': order_ids
            }
            status_doc_ref.set(final_status, merge=True)
            self._env.logging.info(f"Allocation successful. Final status: {final_status}")
```

### 升级文件 2: `cloud-run/application/app/intents/risk_check.py`

盘中风控意图现在需要先**检查状态**，并增加对**卡单的监控**。

```python
from intents.intent import Intent

class RiskCheck(Intent):
    def _core(self):
        self._env.logging.info("Starting Mid-Day Risk Check...")
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_data = status_doc_ref.get().to_dict()

        # --- 1. 状态检查 --- 
        if not status_data or status_data.get('daily_status') != 'ALLOCATION_SUCCESS':
            msg = "Aborting risk check: Morning allocation did not complete successfully."
            self._env.logging.warning(msg)
            return {"status": msg}

        # ... (drawdown check logic remains unchanged) ...

        # --- 2. 卡单检查 (Stuck Order Check) --- 
        morning_order_ids = status_data.get('morning_order_ids', [])
        if morning_order_ids:
            open_orders = self._env.ibgw.reqOpenOrders()
            stuck_orders = []
            for order in open_orders:
                if order.permId in morning_order_ids:
                    stuck_orders.append(order.permId)
            
            if stuck_orders:
                warning_msg = f"WARNING: {len(stuck_orders)} morning order(s) still open by midday: {stuck_orders}"
                self._env.logging.warning(warning_msg)
                self._activity_log.update(stuckOrders=stuck_orders)

        # --- 3. 更新状态 --- 
        status_doc_ref.set({'daily_status': 'RISK_CHECK_SUCCESS'}, merge=True)
        self._env.logging.info("Mid-Day Risk Check completed.")
        
        # ... (return result logic remains unchanged) ...
        return result
```

### 升级文件 3: `cloud-run/application/app/intents/eod_check.py`

收盘检查意图同样需要先**检查状态**，并增加最终的**当日盈亏计算**。

```python
import pandas as pd
from intents.intent import Intent
from intents.close_all import CloseAll

class EodCheck(Intent):
    def _core(self):
        self._env.logging.info("Starting End-of-Day check...")
        status_doc_ref = self._env.db.document(f'status/{self._env.trading_mode}')
        status_data = status_doc_ref.get().to_dict()

        # --- 1. 状态检查 --- 
        if not status_data or status_data.get('daily_status') not in ['ALLOCATION_SUCCESS', 'RISK_CHECK_SUCCESS']:
            msg = "Aborting EOD check: Morning allocation did not complete successfully."
            self._env.logging.warning(msg)
            return {"status": msg}

        # ... (reconciliation, open order check, enforce flat logic remains unchanged) ...

        # --- 2. 最终盈亏计算 --- 
        summary = self._env.get_account_values(self._env.config['account'])
        end_of_day_net_liq = list(summary['NetLiquidation'].values())[0]
        start_of_day_net_liq = status_data.get('startOfDayNetLiq', end_of_day_net_liq)
        daily_pnl = end_of_day_net_liq - start_of_day_net_liq
        self._env.logging.info(f"Daily PnL: {daily_pnl:.2f}")

        result = {
            "netLiquidation": end_of_day_net_liq,
            "dailyPnl": daily_pnl,
            "reconciliationErrors": reconciliation_errors,
            "openOrdersFound": len(open_orders) > 0,
            "brokerPositions": ib_portfolio,
            "systemPositions": system_portfolio
        }
        self._activity_log.update(**result)

        # --- 3. 清理当日状态 --- 
        status_doc_ref.set({'daily_status': 'EOD_SUCCESS'}, merge=True)
        self._env.logging.info("End-of-Day check completed.")
        return result

    # ... (_reconcile method remains unchanged) ...
```