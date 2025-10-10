import asyncio
from os import environ
from lib.gcp import GcpModule
from lib.ibgw import IBGW

class _EnvironmentImpl(GcpModule):
    def __init__(self, trading_mode, ibc_config=None):
        super().__init__()
        self.trading_mode = trading_mode
        self.config = {}
        
        # --- FINAL FIX: Re-add the self.env attribute --- 
        self.env = {k: v for k, v in environ.items() if k in ['K_REVISION', 'PROJECT_ID']}
        # --- END FINAL FIX ---

        common_doc = self.db.document('config/common').get()
        if common_doc.exists:
            self.config.update(common_doc.to_dict())
        
        mode_doc = self.db.document(f'config/{self.trading_mode}').get()
        if mode_doc.exists:
            self.config.update(mode_doc.to_dict())
        
        self.ibgw = IBGW(ibc_config)

    async def get_account_values_async(self, account):
        """Asynchronously fetches account values."""
        summary = await self.ibgw.accountSummaryAsync(account)
        return {
            v.tag: {v.currency: v.value}
            for v in summary if v.tag in ['NetLiquidation', 'TotalCashValue']
        }

class Environment:
    _instance = None
    def __new__(cls, trading_mode=None, ibc_config=None):
        if cls._instance is None:
            trading_mode = trading_mode or environ.get('TRADING_MODE', 'paper')
            
            if ibc_config is None:
                ibc_config = {
                    'gateway': True,
                    'twsVersion': environ.get('TWS_VERSION', 1019),
                    'ibcIni': environ.get('IBC_INI', '/opt/ibc/config.ini'),
                    'ibcPath': environ.get('IBC_PATH', '/opt/ibc'),
                    'javaPath': environ.get('JAVA_PATH', '/usr/bin/java'),
                    'twsPath': environ.get('TWS_PATH', '/root/Jts'),
                    'twsSettingsPath': environ.get('TWS_SETTINGS_PATH', '/root/Jts')
                }

            cls._instance = _EnvironmentImpl(trading_mode, ibc_config)
        return cls._instance