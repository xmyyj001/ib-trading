# 意图 (Intent) 测试指南

本文档列出了本项目支持的各种交易意图 (Intent)，并提供了使用 `curl` 命令进行测试的方法。

## 1. 可测试的意图 (Intents)

根据项目代码的架构，特别是 `cloud-run/application/app/main.py` 中 `INTENTS` 字典的定义，本项目支持以下意图：

1.  **`allocation` (资金分配)**
    *   **目的**：根据预设策略和风险敞口，计算并执行交易，以调整账户持仓。
    *   **请求方法**：`POST`
    *   **示例请求体**：
        ```json
        {
          "dryRun": true,
          "strategies": ["dummy"]
        }
        ```
        **注意**：`dummy` 策略已修改为使用 **SPY (ETF)** 合约进行测试，以适应您的账户权限。
    *   **相关文件**：
        *   [`intents/allocation.py`](cloud-run/application/app/intents/allocation.py)
        *   [`lib/trading.py`](cloud-run/application/app/lib/trading.py)
        *   [`strategies/dummy.py`](cloud-run/application/app/strategies/dummy.py)

2.  **`cash-balancer` (现金平衡)**
    *   **目的**：调整账户中的现金余额，可能涉及货币兑换或现金头寸的调整。
    *   **请求方法**：通常是 `POST` (可能需要请求体来指定目标现金量或货币)。
    *   **相关文件**：[`intents/cash_balancer.py`](cloud-run/application/app/intents/cash_balancer.py)

3.  **`close-all` (平仓)**
    *   **目的**：关闭账户中的所有现有头寸。
    *   **请求方法**：通常是 `POST` (可能不需要请求体)。
    *   **相关文件**：[`intents/close_all.py`](cloud-run/application/app/intents/close_all.py)

4.  **`collect-market-data` (收集市场数据)**
    *   **目的**：收集特定证券的市场数据。
    *   **请求方法**：通常是 `POST` (可能需要请求体来指定证券符号、数据类型等)。
    *   **相关文件**：[`intents/collect_market_data.py`](cloud-run/application/app/intents/collect_market_data.py)

5.  **`summary` (汇总)**
    *   **目的**：获取账户的摘要信息，如账户净清算值、持仓、未完成订单等。
    *   **请求方法**：`GET` (通常不需要请求体)。
    *   **相关文件**：[`intents/summary.py`](cloud-run/application/app/intents/summary.py)

6.  **`trade-reconciliation` (交易对账)**
    *   **目的**：对交易进行对账，可能涉及与历史交易记录的比较。
    *   **请求方法**：通常是 `POST` (可能需要请求体来指定日期范围或其他筛选条件)。
    *   **相关文件**：[`intents/trade_reconciliation.py`](cloud-run/application/app/intents/trade_reconciliation.py)

## 2. 如何进行测试

您可以使用 `curl` 命令向部署在 Google Cloud Run 上的服务发送 HTTP 请求来测试这些意图。

**通用 `curl` 命令格式：**

*   **GET 请求**：
    ```bash
    curl -X GET -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/<intent_name>"
    ```
*   **POST 请求** (带 JSON 请求体)：
    ```bash
    curl -X POST -H "Content-Type: application/json" -H "Authorization: Bearer ${TOKEN}" -d '{"key": "value"}' "${SERVICE_URL}/<intent_name>"
    ```
    其中：
    *   `${SERVICE_URL}` 是您的 Cloud Run 服务的实际 URL。
    *   `${TOKEN}` 是通过 `gcloud auth print-identity-token` 命令获取的身份令牌（如果您的 Cloud Run 服务配置为需要身份验证）。
    *   `<intent_name>` 是上述列表中的意图名称（例如 `allocation`, `summary`）。

**示例：测试 `allocation` 意图 (使用 `dummy` 策略和 `SPY` 合约)**

```bash
# 1. 获取您的 Cloud Run 服务 URL
SERVICE_URL=$(gcloud run services describe ib-paper --region asia-east1 --format="value(status.url)")

# 2. 获取身份令牌 (如果服务需要身份验证)
TOKEN=$(gcloud auth print-identity-token)

# 3. 执行 POST 请求测试 allocation 意图
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "dryRun": true,
    "strategies": ["dummy"]
  }' \
  "${SERVICE_URL}/allocation"
```

**示例：测试 `summary` 意图**

```bash
# 1. 获取您的 Cloud Run 服务 URL
SERVICE_URL=$(gcloud run services describe ib-paper --region asia-east1 --format="value(status.url)")

# 2. 获取身份令牌 (如果服务需要身份验证)
TOKEN=$(gcloud auth print-identity-token)

# 3. 执行 GET 请求测试 summary 意图
curl -X GET \
  -H "Authorization: Bearer ${TOKEN}" \
  "${SERVICE_URL}/summary"