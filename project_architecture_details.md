# 项目架构详细分析

本文档基于对项目文件结构、部署计划和核心代码文件的分析，详细描述了项目的账户设置、下单代码、策略文件以及 Firestore 数据库的设置结构。

## 1. 账户设置

项目的账户设置主要涉及 IB Gateway 的登录凭据和应用程序从 Firestore 获取的配置。

*   **IB Gateway 登录凭据 (`IB_USERNAME`, `IB_PASSWORD`)**:
    *   这些凭据**不**在 Python 应用程序中直接处理。
    *   它们通过环境变量在容器启动时由 `cloud-run/application/cmd.sh` 脚本传递给 IBC (Interactive Brokers Console) 的 `gatewaystart.sh` 脚本。
    *   `cloud-run/base/ibc/config.ini` 文件中包含 `IbLoginId` 和 `IbPassword` 字段，但它们通常留空，因为凭据通过环境变量注入。
*   **应用程序配置获取**:
    *   `cloud-run/application/app/lib/environment.py` 中的 `Environment` 类负责初始化应用程序环境。
    *   它会从 Google Secret Manager 获取交易模式 (`paper` 或 `live`) 对应的密钥。虽然 `environment.py` 中的代码注释表明凭据不再直接用于登录，但 Secret Manager 仍然是存储这些敏感信息的推荐方式。
    *   应用程序还会从 Firestore 的 `config/common` 和 `config/{trading_mode}` 文档中获取其他配置，这些配置可能包含 IB 账户号码 (`account`) 等。
*   **IB Gateway 连接参数**:
    *   `cloud-run/application/app/lib/ibgw.py` 中的 `IBGW` 类定义了默认的连接参数：`host='127.0.0.1'`, `port=4002`, `clientId=1`。
    *   `cloud-run/base/ibc/config.ini` 中的 `OverrideTwsApiPort=4002` 和 `TrustedIPs=127.0.0.1` 设置与此一致，表明应用程序期望连接到容器内部本地运行的 IB Gateway。

## 2. 下单代码文件

项目的下单逻辑分布在多个文件中，协同完成交易执行。

*   **`cloud-run/application/app/intents/allocation.py`**:
    *   这是处理资金分配意图的入口文件。
    *   它从 `_env.config` 中读取 `exposure` (风险敞口) 和 `retryCheckMinutes` (重复交易检查间隔) 等配置。
    *   在执行交易前，它会查询 Firestore 的 `activity` 集合，以防止在短时间内重复执行相同的交易。
    *   它调用 `lib.trading.Trade` 类来执行实际的下单操作。
*   **`cloud-run/application/app/lib/trading.py`**:
    *   定义了交易逻辑的核心构建块，包括 `Instrument`、`Contract`、`Forex`、`Future`、`Index`、`InstrumentSet` 和 `Trade` 等类。
    *   `Instrument` 类及其子类负责与 IB Gateway 交互，获取金融工具的合约详情 (`reqContractDetails`) 和实时行情数据 (`reqTickers`)。
    *   `Trade` 类是实际的交易执行器：
        *   `consolidate_trades()`: 合并来自不同策略的交易信号，生成最终的交易列表。
        *   `_log_trades()`: 将订单状态（未完成订单）记录到 Firestore 的 `positions/{trading_mode}/openOrders` 集合中。当订单完成时，它会更新 Firestore 的 `positions/{trading_mode}/holdings` 集合，记录按策略 ID 分类的持仓信息。
        *   `place_orders()`: 实际向 IB Gateway 提交订单，使用 `ib_insync.placeOrder`。它支持市价单 (`MarketOrder`)，并可以配置算法策略 (`algoStrategy`) 和其他订单属性（如 `tif` - Time In Force）。
*   **`cloud-run/application/app/lib/ibgw.py`**:
    *   提供了与 IB Gateway 的低级交互接口。
    *   `IBGW` 类继承自 `ib_insync.IB`，封装了连接、断开、请求行情、下单等操作。
    *   `start_and_connect()` 方法现在只负责连接到已经运行的 IB Gateway，不再负责启动 IBC，因为启动过程由容器的 `cmd.sh` 脚本处理。

## 3. 策略文件

项目的交易策略通过继承基类来实现，并定义了信号生成和持仓管理逻辑。

*   **`cloud-run/application/app/strategies/strategy.py`**:
    *   所有具体交易策略的基类。
    *   定义了策略的生命周期方法：
        *   `_setup()`: 用于初始化策略所需的金融工具（在子类中实现）。
        *   `_get_signals()`: 用于生成交易信号（在子类中实现）。
        *   `_get_holdings()`: 从 Firestore 的 `positions/{trading_mode}/holdings/{strategy_id}` 集合中获取策略当前的持仓信息。
        *   `_calculate_target_positions()`: 根据生成的信号和风险敞口计算目标头寸（即期望持有的合约数量）。
        *   `_calculate_trades()`: 根据目标头寸和当前持仓计算实际需要执行的交易（买入或卖出的数量）。
    *   还包含处理货币汇率 (`_get_currencies()`) 和合约注册 (`_register_contracts()`) 的通用逻辑。
*   **`cloud-run/application/app/strategies/dummy.py`**:
    *   一个示例策略，继承自 `Strategy`。
    *   `_setup()` 方法中，它通过 `Future.get_contract_series` 获取 MNQ 期货合约。
    *   `_get_signals()` 方法中，它随机生成 -1、0 或 1 的分配，模拟买入、持有或卖出信号。

## 4. Cloud Run 中 Firestore 数据库设置结构

Firestore 数据库在项目中扮演着关键角色，用于存储应用程序的运行时配置和交易相关的状态数据。

*   **初始化脚本**:
    *   `cloud-run/application/app/lib/init_firestore.py` 是一个独立的 Python 脚本，用于初始化 Firestore 中的基本配置文档。它需要一个 `PROJECT_ID` 作为命令行参数来运行。
*   **配置数据结构**:
    *   存储在名为 `config` 的顶级集合中，包含以下文档：
        *   **`config/common` 文档**: 存储通用配置，适用于所有交易模式。
            *   `default_setting`: 示例配置项。
            *   `risk_limit`: 风险限制参数。
            *   `marketDataType`: 市场数据类型（例如 1=Live, 2=Frozen, 3=Delayed），这是一个关键的配置项。
        *   **`config/paper` 文档**: 存储纸上交易模式的特定配置。
            *   `strategy_enabled`: 布尔值，指示是否启用策略。
            *   `max_positions`: 最大持仓数量限制。
            *   `account`: 您的纸上交易账户号码（需要根据实际情况替换）。
        *   **`config/live` 文档**: 存储实盘交易模式的特定配置。
            *   `strategy_enabled`: 布尔值。
            *   `max_positions`: 最大持仓数量限制。
            *   `account`: 您的真实交易账户号码（需要根据实际情况替换）。
*   **交易状态数据结构**:
    *   存储在名为 `positions` 的顶级集合中，并按交易模式 (`paper` 或 `live`) 分为子集合。
    *   **`positions/{trading_mode}/openOrders` 子集合**:
        *   存储所有未完成的订单信息。每个文档代表一个未完成订单。
        *   文档内容可能包括：`acctNumber` (账户号码), `contractId` (合约 ID), `orderId` (订单 ID), `permId` (永久 ID), `source` (订单来源策略), `timestamp` (订单创建时间)。
    *   **`positions/{trading_mode}/holdings` 子集合**:
        *   存储按策略 ID 分类的当前持仓信息。每个文档代表一个策略的持仓。
        *   文档 ID 为策略的 ID (例如 `dummy`)。
        *   文档内容是一个字典，键为合约 ID (字符串形式)，值为持仓数量。例如：`{"12345": 10, "67890": -5}`。

### Firestore 数据库结构示意图

```mermaid
graph TD
    Firestore --> ConfigCollection[Collection: config];
    Firestore --> PositionsCollection[Collection: positions];

    ConfigCollection --> ConfigCommonDoc[Document: common];
    ConfigCollection --> ConfigPaperDoc[Document: paper];
    ConfigCollection --> ConfigLiveDoc[Document: live];

    ConfigCommonDoc -- Fields --> CommonFields(default_setting, risk_limit, marketDataType);
    ConfigPaperDoc -- Fields --> PaperFields(strategy_enabled, max_positions, account);
    ConfigLiveDoc -- Fields --> LiveFields(strategy_enabled, max_positions, account);

    PositionsCollection --> PositionsTradingModeSubCollection[Sub-collection: {trading_mode} (e.g., paper, live)];

    PositionsTradingModeSubCollection --> OpenOrdersCollection[Sub-collection: openOrders];
    PositionsTradingModeSubCollection --> HoldingsCollection[Sub-collection: holdings];

    OpenOrdersCollection --> OpenOrderDoc[Document: auto-generated ID];
    OpenOrderDoc -- Fields --> OpenOrderFields(acctNumber, contractId, orderId, permId, source, timestamp);

    HoldingsCollection --> StrategyHoldingsDoc[Document: {strategy_id} (e.g., dummy)];
    StrategyHoldingsDoc -- Fields --> HoldingsFields(contractId1: quantity1, contractId2: quantity2, ...);