# 项目策略指南

本文档详细分析了项目中已给出的交易策略及其使用方法，并总结了策略文件的结构规范，旨在为新策略的开发提供指导。

## 1. 策略在项目中的作用

在本项目中，策略是实现自动化交易逻辑的核心组件。它们负责：
*   定义交易目标和规则。
*   获取所需的金融工具（合约）信息。
*   根据市场数据和内部逻辑生成交易信号。
*   管理当前持仓并计算目标头寸。
*   生成实际的交易指令，供 `allocation` 意图执行。

所有策略都基于一个通用的基类，这确保了代码结构的一致性和可扩展性。

## 2. `Strategy` 基类 (`cloud-run/application/app/strategies/strategy.py`)

`Strategy` 类是所有具体交易策略的抽象基类。它提供了一个标准化的框架和一系列通用功能，子类只需关注其特有的业务逻辑。

### 2.1 核心属性

`Strategy` 类维护了多个内部属性来管理策略的状态和数据：

*   `_contracts`: 存储策略使用的金融合约对象。
*   `_fx`: 存储货币汇率信息。
*   `_holdings`: 存储策略当前的持仓信息（从 Firestore 获取）。
*   `_instruments`: 存储策略初始化时定义的金融工具实例。
*   `_signals`: 存储策略生成的交易信号。
*   `_target_positions`: 存储根据信号计算出的目标头寸。
*   `_trades`: 存储根据目标头寸和当前持仓计算出的实际交易指令。

### 2.2 构造函数 (`__init__`)

`Strategy` 类的构造函数定义了策略的初始化流程和核心执行顺序：

```python
def __init__(self, _id=None, **kwargs):
    self._id = _id or self.__class__.__name__.lower() # 策略的唯一ID
    self._env = Environment() # 获取环境实例，用于与IB Gateway和GCP服务交互
    self._base_currency = kwargs.get('base_currency', None) # 基础货币
    self._exposure = kwargs.get('exposure', 0) # 风险敞口

    self._setup() # 1. 初始化金融工具 (子类实现)

    self._get_signals() # 2. 生成交易信号 (子类实现)
    self._get_holdings() # 3. 从Firestore获取当前持仓

    # 4. 补全持仓和信号中缺失的合约ID，确保一致性
    contract_ids = set([*self._signals.keys()] + [*self._holdings.keys()])
    self._holdings = {**{cid: 0 for cid in contract_ids}, **self._holdings}
    self._signals = {**{cid: 0 for cid in contract_ids}, **self._signals}
    assert all(k in self._holdings.keys() for k in contract_ids)

    self._calculate_target_positions() # 5. 计算目标头寸
    self._calculate_trades() # 6. 计算实际交易指令
```

### 2.3 核心方法

`Strategy` 基类定义了以下核心方法，其中一些是抽象的（需要在子类中实现），另一些提供了通用逻辑：

*   **`_setup()` (抽象方法)**:
    *   **职责**：用于子类初始化策略所需的金融工具（例如，定义要交易的股票、ETF、期货合约等）。
    *   **实现**：子类必须重写此方法来设置 `self._instruments` 属性。
*   **`_get_signals()` (抽象方法)**:
    *   **职责**：用于子类根据其交易逻辑生成交易信号。
    *   **实现**：子类必须重写此方法来设置 `self._signals` 属性。信号通常是合约 ID 到期望方向/强度的映射。
*   **`_get_holdings()`**:
    *   **职责**：从 Firestore 数据库中获取策略当前的持仓信息。
    *   **实现**：它会查询 `positions/{trading_mode}/holdings/{strategy_id}` 路径下的文档。
*   **`_calculate_target_positions()`**:
    *   **职责**：将 `_signals` 转换为具体的 `_target_positions`（即期望持有的合约数量）。
    *   **实现**：此方法会考虑基础货币、风险敞口、合约价格、乘数和汇率来计算目标头寸。
*   **`_calculate_trades()`**:
    *   **职责**：根据 `_target_positions` 和 `_holdings` 计算出实际需要执行的交易指令（买入或卖出的数量）。
    *   **实现**：它会计算目标头寸与当前持仓之间的差异。
*   **`_get_currencies(base_currency)`**:
    *   **职责**：获取所有涉及合约的货币与基础货币之间的汇率。
    *   **实现**：使用 `lib.trading.Forex` 和 `InstrumentSet` 来请求汇率数据。
*   **`_register_contracts(*contracts)`**:
    *   **职责**：将金融合约注册到 `self._contracts` 属性中，确保所有需要的合约信息都已加载。

### 2.4 属性 (`@property`)

`Strategy` 类通过 `@property` 装饰器提供了对内部状态的只读访问，例如 `contracts`, `fx`, `holdings`, `id`, `signals`, `target_positions`, `trades`。

## 3. `Dummy` 策略 (`cloud-run/application/app/strategies/dummy.py`)

`Dummy` 策略是一个简单的示例，用于演示如何实现 `Strategy` 基类，并作为测试框架的一部分。

### 3.1 作用

*   提供一个可运行的策略示例。
*   演示如何定义和获取交易工具（现在以 SPY ETF 为例）。
*   演示如何生成简单的交易信号。
*   包含健壮性检查，以处理合约获取失败的情况。

### 3.2 实现细节

*   **导入**：
    ```python
    from random import randint
    from lib.trading import Contract, InstrumentSet # 导入 Contract 和 InstrumentSet
    from strategies.strategy import Strategy
    ```
*   **`_setup()` 方法**：
    *   定义了策略要交易的金融工具。
    *   **示例**：获取 SPY ETF 合约。
    ```python
    def _setup(self):
        self._instruments = {
            'spy': InstrumentSet(Contract(symbol='SPY', exchange='ARCA', currency='USD', secType='ETF'))
        }
        # 确保合约详情已获取，并添加健壮性检查
        if self._instruments['spy'].constituents:
            self._instruments['spy'].constituents[0].get_contract_details()
            if not self._instruments['spy'].constituents[0].contract:
                self._env.logging.error("Failed to get contract details for SPY. Check IB Gateway connection and market data permissions.")
                self._instruments['spy'] = None # 标记为无效，防止后续错误
    ```
*   **`_get_signals()` 方法**：
    *   生成交易信号。
    *   **示例**：随机生成 -1 (卖出), 0 (持有), 1 (买入) 的信号。
    *   包含了对合约是否存在的健壮性检查。
    ```python
    def _get_signals(self):
        # 确保 _instruments['spy'] 存在且不为空
        if not self._instruments.get('spy') or not self._instruments['spy'].constituents:
            self._env.logging.warning("No valid 'spy' contracts found. Skipping signal generation.")
            self._signals = {}
            return

        # 使用 SPY 的合约 ID
        allocation = {
            self._instruments['spy'][0].contract.conId: randint(-1, 1)
        }
        self._env.logging.debug(f'Allocation: {allocation}')
        self._signals = allocation
        # 注册分配的合约
        self._register_contracts(self._instruments['spy'][0])
    ```

## 4. 策略文件结构规范总结

开发新策略时，应遵循以下规范：

1.  **继承 `Strategy` 基类**：
    *   所有新策略类都必须继承自 `strategies.strategy.Strategy`。
    *   这将自动获得策略生命周期管理、与环境交互的能力以及对 Firestore 和 IB Gateway 的访问。
2.  **实现核心抽象方法**：
    *   **`_setup()`**: 必须重写此方法来定义策略将使用的金融工具。使用 `lib.trading` 中提供的 `Contract`, `Forex`, `Future`, `Index` 等类来创建工具实例，并将其存储在 `self._instruments` 字典中。
    *   **`_get_signals()`**: 必须重写此方法来定义策略的信号生成逻辑。根据您的交易规则，计算出每个合约的信号，并将其存储在 `self._signals` 字典中（键为合约 ID，值为信号强度/方向）。
3.  **定义交易工具**：
    *   使用 `lib.trading` 模块中的 `Instrument` 子类来定义您要交易的证券类型。
    *   例如，对于股票/ETF 使用 `Contract(symbol='AAPL', exchange='SMART', currency='USD', secType='STK')` 或 `Contract(symbol='SPY', exchange='ARCA', currency='USD', secType='ETF')`。
    *   对于期货使用 `Future.get_contract_series()`。
    *   确保在定义工具后调用 `get_contract_details()` 来获取完整的合约信息。
4.  **与环境交互**：
    *   通过 `self._env` 属性访问 `Environment` 实例，从而获取配置 (`self._env.config`)、访问 Firestore (`self._env.db`) 和与 IB Gateway 交互 (`self._env.ibgw`)。
    *   使用 `self._env.logging` 进行日志记录，以便在 Cloud Run 日志中查看策略的运行情况。
5.  **健壮性与错误处理**：
    *   在获取合约详情、行情数据或进行任何可能失败的外部调用后，务必添加健壮性检查（例如检查返回结果是否为 `None` 或空）。
    *   使用 `self._env.logging.error` 或 `self._env.logging.warning` 记录重要的错误和警告。
6.  **命名约定**：
    *   策略文件名和类名应清晰、简洁，并反映策略的目的。
    *   策略 ID (`self._id`) 默认为类名的小写形式，但也可以在构造函数中显式指定。
7.  **测试**：
    *   每个策略文件可以包含一个 `if __name__ == '__main__':` 块，用于本地测试策略的独立功能，而无需部署整个应用程序。

遵循这些规范将有助于您开发出结构良好、易于维护和调试的交易策略。