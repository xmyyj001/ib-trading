# 场景 A: 日线级别的“波段/趋势交易者” (最终完整版)

## 1. 目标与理念

此方案的目标是构建一个稳健的、低频的自动化交易系统。它在每日收盘后进行决策，旨在抓住持续数天或更长时间的市场趋势，并接受持仓隔夜。该模式逻辑简单，信号稳定，能有效过滤盘中噪音，且云资源和交易成本都非常低。

在项目初期，我们采用了一种非常经典和直观的架构模式，可以称之为**“总指挥模式”**。这个模式的核心是 `allocation` 这个意图（Intent）。

### 1.1 “总指挥” allocation 的工作流程

让我们用一个餐厅的厨房来比喻这个模式：

*   **`allocation` 意图**：是厨房的**行政总厨**。他不亲自炒菜，但他决定今晚要做哪些菜，以及每道菜用多少预算。
*   **策略 (如 `spymacdvixy`)**：是负责研发菜谱的**菜品研发员**。他们只负责提供“菜谱”（交易信号），比如“今天适合多放点辣”（看涨信号，权重 `1.0`）或者“今天应该清淡点”（看跌信号，权重 `-0.5`）。他们不关心这道菜具体要炒多少份，也不关心后厨的采购成本。
*   **HTTP 请求**: 是来自前厅的**订单**。订单上写着：“尊敬的总厨，请用今晚的预算，做一份‘辣子鸡丁’（`spymacdvixy`）和一份‘清炒时蔬’（`dummy`）。”

**工作流程如下**：

1.  “总厨”(`allocation`) 接到订单，看到需要做 `spymacdvixy` 和 `dummy` 两道菜。
2.  他去问 `spymacdvixy` 的研发员：“今天的菜谱是什么？” 研发员回答：“多放辣（权重 `1.0`）。”
3.  他又去问 `dummy` 的研发员，得到另一份菜谱。
4.  “总厨”拿到所有菜谱后，拿出厨房的总预算（账户净值 `netLiquidation`），根据每道菜的权重，计算出具体要用多少钱来买原材料（`exposure * weight`），然后根据原材料市价（`price`），计算出要买多少斤（`quantity`）。
5.  最后，“总厨”把采购清单交给采购员（`place_order` 方法），完成下单。

### 1.2 对“总指挥”模式的评价

这种模式对于初创项目来说，非常清晰易懂。

*   **优点：集中控制**
    *   **资金管理**: 所有的资金分配都由“总厨”一人负责，绝对不会超预算。全局风险控制非常容易。
    *   **策略简单**: “菜品研发员”非常省心，只需要专注于味道（信号强弱），不需要考虑成本和库存，开发新“菜谱”很快。

*   **缺点：僵化与瓶颈**
    *   **总厨是瓶颈**: 随着餐厅菜品越来越多，“总厨”需要了解的菜谱也越来越多，他的工作变得异常复杂。如果某道菜需要一种特殊的烹饪技巧（例如，不是炒，而是低温慢煮），“总厨”就必须亲自去学，他的能力决定了整个厨房的上限。
        *   **对应到代码**: 如果一个新策略需要特殊的订单类型（如期权组合单）或下单逻辑，“总厨” `allocation` 就必须被修改，变得越来越臃g肿和难以维护。
    *   **沟通模糊**: “菜谱”里的“多放点辣”是一个很模糊的概念。到底放多少？“总厨”只能根据自己的理解（`exposure * weight / price`）去转换。当厨房预算很少，或者辣椒很贵时，他计算出的辣椒用量可能是 `0.01` 克，取整后就变成了 `0`，导致菜里最终没有放辣。
        *   **对应到代码**: 这正是我们遇到的 `int(0.xx)` 问题。策略提供的抽象 `weight` 无法保证在所有资金和价格下都能转换成有效的交易数量。

**结论**：“总指挥”模式在系统规模扩大、策略复杂度增加后，其**灵活性不足和沟通模糊**的缺点会成为严重的瓶颈。因此，我们需要一种新的、更能适应变化的架构。

---

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

## 4. 安全与干预机制 (最低标准)

此章节为基础版本增加必要的安全功能，是生产投用的最低要求。

### 4.1 “紧急制动”开关 (Kill Switch)

**实现**: 修改 `intent.py` 基类，在执行任何操作前检查 Firestore 中的 `tradingEnabled` 标志。

**完整代码**: `cloud-run/application/app/intents/intent.py`

### 4.2 核心监控与警报

**实现**: 通过 GCP 控制台设置，无需编码。
1.  **警报一 (系统“硬”故障)**: 在 Monitoring 中创建基于 `Cloud Run Revision` 指标的警报，当 `Request Count` 的 `response_code_class` 为 `5xx` 时触发。
2.  **警报二 (系统“静默”故障)**: 在 Logging 中创建基于 `textPayload:"Orders placed"` 的日志指标，当该指标在1天内小于1时触发警报。

### 4.3 手动状态同步工具 (`/reconcile`)

**实现**: 新增一个 `/reconcile` 意图，用于在手动干预后，强制将系统状态与券商同步。

**新增文件**: `cloud-run/application/app/intents/reconcile.py`


**修改文件**: `cloud-run/application/app/main.py` (注册新意图)


### 4.4 进阶完善：处理隔夜订单 (GTC) 与状态管理

这个版本解决了基础版本中的核心缺陷，能够正确管理在途的隔夜订单，是进行波段交易的健壮实现。

### 有关文件 1: `cloud-run/application/app/lib/trading.py`

### 有关文件 2: `cloud-run/application/app/strategies/strategy.py`

### 有关文件 3: `cloud-run/application/app/intents/allocation.py` 

---

##  初始化Firestore `init_firestore.py` 
在首次部署或需要重置数据库配置时，推荐使用以下脚本来初始化 Firestore。此脚本专为**场景A（波段交易）**定制，包含了所有必要的安全和交易参数。

为确保本文档的完整性，此处提供与上述进阶方案完全兼容的 `spymacdvixy.py` 策略代码。

### `cloud-run/application/app/strategies/spy_macd_vixy.py` (最终版)



### 5. 演进**“策略即意图”**的新模式。

## 因为项目的试运行，由allocation 调用 spy_macd_vixy 的策略并没有跑通。
所以引入了"策略即意图"验证模式：每天可以产生交易信号以验证系统可行性的测试策略：`test_signal_generator.py` 

## 对“总指挥” allocation 的补充讨论和疑问：
1. 挂单管理 (Pending Orders): 计算可用资金时，必须查询 Firestore 中的 openOrders 集合，将所有“在途”的、未成交的挂单的名义价值也计算在内，并从可用额度中扣除。我将其比喻为“假装它已经成交”。

2.准确地计算当前持仓并管理: 可用资金 = 理论总额度 - 已有持仓的总市值 - 所有未成交挂单的名义价值

3. 平仓必须实现：将 close-all 重构为平仓“指令分发者”，针对指定的单个策略，准确地清算该策略的头寸。
