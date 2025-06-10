from datetime import datetime
import falcon
import json
import logging
from os import environ, listdir
import re

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from lib.environment import Environment

# get environment variables
TRADING_MODE = environ.get('TRADING_MODE', 'paper')
TWS_INSTALL_LOG = environ.get('TWS_INSTALL_LOG')

if TRADING_MODE not in ['live', 'paper']:
    raise ValueError('Unknown trading mode')

# set constants
INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation
}

# build IBC config from environment variables
env = {
    key: environ.get(key) for key in
    ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
}
env['javaPath'] += f"/{listdir(env['javaPath'])[0]}/bin"

# --- 主要修改区域开始 ---
# 从日志文件中安全地提取 TWS 版本号

# 1. 首先读取日志文件内容
with open(TWS_INSTALL_LOG, 'r') as fp:
    install_log = fp.read()

# 2. 执行正则表达式搜索，并将结果保存在一个变量中
match = re.search('IB Gateway ([0-9]{3})', install_log)

# 3. 检查搜索是否成功。如果不成功，则抛出一个清晰的异常，而不是让程序崩溃
if not match:
    # 这个错误信息会非常清晰地告诉您问题所在，方便调试
    raise ValueError(
        f"无法在 TWS 安装日志中找到版本号。 "
        f"期望的模式是 'IB Gateway ([0-9]{3})'。 "
        f"日志文件 '{TWS_INSTALL_LOG}' 的内容是: '{install_log}'"
    )

# 4. 只有在搜索成功后，才提取版本号
tws_version = match.group(1)

# 5. 使用验证过的版本号来构建配置字典
ibc_config = {
    'gateway': True,
    'twsVersion': tws_version, # 使用安全获取到的版本号
    **env
}
# --- 主要修改区域结束 ---

Environment(TRADING_MODE, ibc_config)


class Main:
    """
    Main route.
    """

    def on_get(self, request, response, intent):
        self._on_request(request, response, intent)

    def on_post(self, request, response, intent):
        body = json.load(request.stream) if request.content_length else {}
        self._on_request(request, response, intent, **body)

    @staticmethod
    def _on_request(_, response, intent, **kwargs):
        """
        Handles HTTP request.

        :param _: Falcon request (not used)
        :param response: Falcon response
        :param intent: intent (str)
        :param kwargs: HTTP request body (dict)
        """

        try:
            if intent is None or intent not in INTENTS.keys():
                logging.warning('Unknown intent')
                intent_instance = Intent()
            else:
                intent_instance = INTENTS[intent](**kwargs)
            result = intent_instance.run()
            response.status = falcon.HTTP_200
        except Exception as e:
            error_str = f'{e.__class__.__name__}: {e}'
            result = {'error': error_str}
            response.status = falcon.HTTP_500

        result['utcTimestamp'] = datetime.utcnow().isoformat()
        response.content_type = falcon.MEDIA_JSON
        response.text = json.dumps(result) + '\n'


# instantiante Falcon App and define route for intent
app = falcon.App()
app.add_route('/{intent}', Main())

# 主要修改点
# 分离正则表达式搜索：我不再将 re.search(...) 和 .group(1) 写在同一行。而是先执行搜索，并将结果（可能是匹配对象，也可能是 None）保存在 match 变量中。
# 添加检查和错误处理：在尝试访问 .group(1) 之前，我添加了一个 if not match: 的检查。如果 re.search 没有找到匹配项（返回 None），代码现在会主动抛出一个 ValueError。
# 更清晰的错误信息：这个新的 ValueError 包含一个非常详细的错误信息，它会告诉你：
# 问题是找不到版本号。
# 它期望的格式是什么。
# 它查看的日志文件的实际内容是什么。
# 这样，如果将来你的基础镜像或环境配置发生变化导致日志内容改变，你会立刻得到一个有用的错误信息，而不是一个令人困惑的 AttributeError。
# 安全地构建配置：只有在检查通过后，代码才会从 match 对象中提取版本号，并用它来安全地构建 ibc_config 字典。