from random import randint

from lib.trading import Contract, InstrumentSet # 更改为导入 Contract 和 InstrumentSet
from strategies.strategy import Strategy


class Dummy(Strategy):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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
        # register allocation contracts so that they don't have to be created again
        self._register_contracts(self._instruments['spy'][0]) # 更改为 'spy'

    def _setup(self):
        # 更改为获取 SPY ETF 合约
        self._instruments = {
            'spy': InstrumentSet(Contract(symbol='SPY', exchange='SMART', currency='USD', secType='ETF')) # 更改 exchange 为 SMART
        }
        # 确保合约详情已获取
        if self._instruments['spy'].constituents:
            self._instruments['spy'].constituents[0].get_contract_details()
            if not self._instruments['spy'].constituents[0].contract:
                self._env.logging.error("Failed to get contract details for SPY. Check IB Gateway connection and market data permissions.")
                self._instruments['spy'] = None # 标记为无效，防止后续错误


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    env.ibgw.reqMarketDataType(2)
    try:
        Dummy(base_currency='CHF', exposure=1, net_liquidation=100000)
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
