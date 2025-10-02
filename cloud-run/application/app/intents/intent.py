import asyncio
import json
from datetime import datetime
from hashlib import md5
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from lib.environment import Environment

class Intent:
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

    async def _core_async(self):
        """Subclasses override this to implement their core async logic."""
        return {'currentTime': await self._env.ibgw.reqCurrentTimeAsync()}

    def _log_activity(self):
        if self._activity_log:
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(f"Failed to log activity: {e}", exc_info=True)

    async def _run_wrapper(self):
        """Handles the connection lifecycle for a request."""
        try:
            await self._env.ibgw.start_and_connect_async()
            if not self._env.config.get('tradingEnabled', True):
                raise SystemExit("Trading disabled by kill switch.")
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            return await self._core_async()
        finally:
            if self._env.ibgw.isConnected():
                self._env.ibgw.disconnect()

    def run(self):
        """Sync entrypoint called by the web handler."""
        retval = {}
        exc = None
        try:
            # Bridge to the async world in a new, isolated event loop.
            retval = asyncio.run(self._run_wrapper())
        except BaseException as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            if self._env.env.get('K_REVISION', 'localhost') != 'localhost':
                self._log_activity()
        if exc:
            raise exc
        return retval or self._activity_log
