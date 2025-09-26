import json
import inspect
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

    async def _core(self):
        return {'currentTime': await self._env.ibgw.reqCurrentTimeAsync()}

    def _log_activity(self):
        if len(self._activity_log):
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(e)
                self._env.logging.info(self._activity_log)

    async def run(self):
        retval = {}
        try:
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading is globally disabled by kill switch in Firestore config.")
            
            await self._env.ibgw.start_and_connect_async()
            await self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            
            # Await the core logic, which can now be async
            retval = await self._core()
            
        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._env.logging.error(error_str)
            self._activity_log.update(exception=error_str)
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
            raise e
        finally:
            await self._env.ibgw.stop_and_terminate_async()
            self._env.logging.info('Done.')

        if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
            self._log_activity()
        
        if 'timestamp' in self._activity_log:
            self._activity_log['timestamp'] = self._activity_log['timestamp'].isoformat()
            
        return retval or self._activity_log
