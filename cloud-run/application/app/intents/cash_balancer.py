from ib_insync import Forex, MarketOrder

from intents.intent import Intent


class CashBalancer(Intent):

    _dry_run = False

    def __init__(self, env, **kwargs):
        super().__init__(env=env, **kwargs)

        self._dry_run = kwargs.get('dryRun', self._dry_run) if kwargs is not None else self._dry_run
        self._activity_log.update(dryRun=self._dry_run)

    async def _core_async(self):
        self._env.logging.info('Checking cash balances...')

        account_values = await self._env.get_account_values_async(self._env.config['account'],
                                                      rows=['NetLiquidation', 'CashBalance', 'ExchangeRate'])
        base_currency = [*account_values['NetLiquidation'].keys()][0]
        exposure = {
            k: v * account_values['ExchangeRate'][k]
            for k, v in account_values['CashBalance'].items()
            if k != base_currency
        }
        self._activity_log.update(exposure=exposure)
        trades = {
            k + base_currency: -(int(v / account_values['ExchangeRate'][k]) // 1000 * 1000)
            for k, v in exposure.items()
            if abs(v) > self._env.config['cashBalanceThresholdInBaseCurrency']
        }
        self._activity_log.update(trades=trades)
        if len(trades):
            self._env.logging.info(f'Trades to reset cash balances: {trades}')
        else:
            self._env.logging.info('No cash balances above the threshold')

        if not self._dry_run and len(trades):
            # place orders
            perm_ids = []
            for k, v in trades.items():
                order = await self._env.ibgw.placeOrderAsync(Forex(pair=k, exchange='FXCONV'),
                                                  MarketOrder('BUY' if v > 0 else 'SELL', abs(v)))
                perm_ids.append(order.order.permId)
            
            # Wait for trades to appear
            await asyncio.sleep(2)

            orders = {
                t.contract.pair(): {
                    'order': {
                        k: v
                        for k, v in t.order.nonDefaults().items()
                        if isinstance(v, (int, float, str))
                    },
                    'orderStatus': {
                        k: v
                        for k, v in t.orderStatus.nonDefaults().items()
                        if isinstance(v, (int, float, str))
                    }
                } for t in self._env.ibgw.openTrades() if t.orderStatus.permId in perm_ids
            }
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    try:
        cash_balancer = CashBalancer(dryRun=False)
        cash_balancer._core()
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
