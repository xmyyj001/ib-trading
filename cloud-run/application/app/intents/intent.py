import json
from datetime import datetime
from hashlib import md5
import logging

from lib.environment import Environment

class Intent:
    _activity_log = {}

    def __init__(self, env: Environment, **kwargs):
        self._env = env # Dependency Injection
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
        """Placeholder for core logic in subclasses."""
        return {'currentTime': (await self._env.ibgw.reqCurrentTimeAsync()).isoformat()}

    def _log_activity(self):
        if len(self._activity_log):
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                # .set() is a synchronous method, no await needed.
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(f"Failed to log activity: {e}", exc_info=True)

    async def run(self):
        """
        Executes the intent's logic, assuming a persistent connection.
        """
        retval = {}
        exc = None
        try:
            if not self._env.ibgw.isConnected():
                raise ConnectionError("Not connected to IB Gateway. Check lifespan startup logs.")

            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading is globally disabled by kill switch.")
            
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()

        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            logging.error(f"Exception in intent run: {error_str}", exc_info=True)
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
        
        if exc is not None:
            raise exc

        logging.info(f"Intent {self.__class__.__name__} completed successfully.")
        if 'timestamp' in self._activity_log and isinstance(self._activity_log['timestamp'], datetime):
            self._activity_log['timestamp'] = self._activity_log['timestamp'].isoformat()
            
        return retval or self._activity_log