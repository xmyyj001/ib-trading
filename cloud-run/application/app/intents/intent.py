import json
from datetime import datetime
from hashlib import md5
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from lib.environment import Environment

class Intent:
    _activity_log = {}

    def __init__(self, env: "Environment", **kwargs):
        self._env = env
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
        if self._activity_log:
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(f"Failed to log activity: {e}", exc_info=True)

    async def run(self):
        retval = {}
        exc = None
        try:
            # Connect-on-demand: connect at the beginning of the request.
            await self._env.ibgw.start_and_connect_async()

            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading disabled by kill switch.")
            
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = await self._core()

        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            # Always disconnect at the end of the request.
            if self._env.ibgw.isConnected():
                self._env.ibgw.disconnect()
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
        
        if exc:
            raise exc

        return retval or self._activity_log