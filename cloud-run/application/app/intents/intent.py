import json
from datetime import datetime
from hashlib import md5

from lib.environment import Environment
from ib_insync import util # <--- 1. 重新导入

# 2. 增加一个全局标志位来跟踪patch状态
_asyncio_patched = False

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

    async def _core(self):
        return {'currentTime': (await self._env.ibgw.reqCurrentTimeAsync()).isoformat()}

    def _log_activity(self):
        if len(self._activity_log):
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(e)
                self._env.logging.info(self._activity_log)

    async def run(self):
        global _asyncio_patched
        # --- 3. 在运行时执行Patch --- 
        if not _asyncio_patched:
            self._env.logging.info("Applying asyncio patch for ib_insync in worker process...")
            util.patchAsyncio()
            _asyncio_patched = True
        # --- END PATCH --- 

        retval = {}
        exc = None
        try:
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading is globally disabled by kill switch.")
            
            await self._env.ibgw.start_and_connect_async()
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()
        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._env.logging.error(error_str)
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            if self._env.ibgw.isConnected():
                await self._env.ibgw.stop_and_terminate_async()
            
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
            
            if exc is not None:
                raise exc

        self._env.logging.info('Done.')
        if 'timestamp' in self._activity_log and isinstance(self._activity_log['timestamp'], datetime):
            self._activity_log['timestamp'] = self._activity_log['timestamp'].isoformat()
            
        return retval or self._activity_log