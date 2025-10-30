import sys
from types import ModuleType, SimpleNamespace


def install_ib_insync_stub():
    """
    Provide a lightweight stand-in for the ib_insync package so tests can
    run in environments where the real native extension is unavailable.
    """
    if 'ib_insync' in sys.modules:
        return

    ib_module = ModuleType('ib_insync')

    class _Base(SimpleNamespace):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    class MarketOrder(SimpleNamespace):
        def __init__(self, action=None, quantity=0):
            super().__init__(action=action, totalQuantity=quantity)

    class OrderStatus:
        ActiveStates = ['Submitted', 'PreSubmitted', 'PendingSubmit']
        DoneStates = ['Filled', 'Cancelled', 'Inactive']

    class Contract(_Base):
        pass

    class Stock(_Base):
        pass

    class Forex(_Base):
        pass

    class Future(_Base):
        pass

    class Option(_Base):
        pass

    class Order(_Base):
        pass

    class TagValue(_Base):
        pass

    class IB(SimpleNamespace):
        pass

    class IBC(SimpleNamespace):
        pass

    def dict_to_contract(data):
        return SimpleNamespace(**data)

    util_module = ModuleType('ib_insync.util')
    util_module.dictToContract = dict_to_contract

    objects_module = ModuleType('ib_insync.objects')

    class AccountValue(SimpleNamespace):
        def __init__(self, account=None, tag=None, value=None, currency=None, modelCode=''):
            super().__init__(account=account, tag=tag, value=value, currency=currency, modelCode=modelCode)

    objects_module.AccountValue = AccountValue

    ib_module.MarketOrder = MarketOrder
    ib_module.OrderStatus = OrderStatus
    ib_module.Contract = Contract
    ib_module.Stock = Stock
    ib_module.Forex = Forex
    ib_module.Future = Future
    ib_module.Option = Option
    ib_module.Order = Order
    ib_module.TagValue = TagValue
    ib_module.IB = IB
    ib_module.IBC = IBC
    ib_module.util = util_module
    ib_module.objects = objects_module

    sys.modules['ib_insync'] = ib_module
    sys.modules['ib_insync.util'] = util_module
    sys.modules['ib_insync.objects'] = objects_module


def install_google_cloud_stub():
    """
    Install lightweight google.cloud modules so unit tests can import code
    without pulling in heavy native dependencies.
    """
    if 'google' in sys.modules:
        keys_to_remove = [name for name in sys.modules if name == 'google' or name.startswith('google.')]
        for key in keys_to_remove:
            sys.modules.pop(key, None)

    google_module = ModuleType('google')
    google_module.__path__ = []
    cloud_module = ModuleType('google.cloud')
    cloud_module.__path__ = []
    setattr(google_module, 'cloud', cloud_module)

    module_map = {'google': google_module, 'google.cloud': cloud_module}

    def _add_cloud_module(name):
        module = ModuleType(f'google.cloud.{name}')
        setattr(cloud_module, name, module)
        module_map[f'google.cloud.{name}'] = module
        return module

    bigquery_module = _add_cloud_module('bigquery')
    bigquery_module.__path__ = []
    firestore_module = _add_cloud_module('firestore_v1')
    logging_module = _add_cloud_module('logging')
    secretmanager_module = _add_cloud_module('secretmanager_v1')

    class _BaseParameter(SimpleNamespace):
        def __init__(self, name=None, type=None, value=None):
            super().__init__(name=name, type=type, value=value)

        def __repr__(self):
            return f"{self.__class__.__name__}(name={self.name!r}, type={self.type!r}, value={getattr(self, 'value', getattr(self, 'values', None))!r})"

    class ScalarQueryParameter(_BaseParameter):
        pass

    class ArrayQueryParameter(_BaseParameter):
        def __init__(self, name=None, type=None, values=None):
            super().__init__(name=name, type=type)
            self.values = list(values or [])

    class QueryJobConfig(SimpleNamespace):
        def __init__(self, **kwargs):
            self.query_parameters = kwargs.get('query_parameters', [])

    class QueryJob(SimpleNamespace):
        def to_dataframe(self, **_):
            return SimpleNamespace(set_index=lambda *a, **k: None)

    class _LoggingClient:
        def __init__(self, *_, **__):
            pass

        def get_default_handler(self):
            return SimpleNamespace()

    class _FirestoreClient:
        def __init__(self, *_, **__):
            pass

        def collection(self, *_):
            return SimpleNamespace()

        def document(self, *_):
            return SimpleNamespace(get=lambda: SimpleNamespace(), set=lambda *_a, **_k: None)

    class _SecretManager:
        def __init__(self, *_, **__):
            pass

        def access_secret_version(self, *_, **__):
            return SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(decode=lambda: '')))

    class _BigQueryClient:
        def __init__(self, *_, **__):
            pass

        def query(self, *_ , **__):
            return SimpleNamespace(result=lambda: [], to_dataframe=lambda **_: SimpleNamespace(set_index=lambda *a, **k: None))

    bigquery_module.Client = _BigQueryClient
    bigquery_module.ArrayQueryParameter = ArrayQueryParameter
    bigquery_module.ScalarQueryParameter = ScalarQueryParameter
    job_module = ModuleType('google.cloud.bigquery.job')
    job_module.__path__ = []
    job_module.QueryJobConfig = QueryJobConfig
    module_map['google.cloud.bigquery.job'] = job_module
    bigquery_module.job = job_module
    bigquery_module.QueryJob = QueryJob

    firestore_module.Client = _FirestoreClient
    logging_module.Client = _LoggingClient
    secretmanager_module.SecretManagerServiceClient = _SecretManager

    auth_module = ModuleType('google.auth')
    setattr(google_module, 'auth', auth_module)

    class DefaultCredentialsError(Exception):
        pass

    auth_module.exceptions = SimpleNamespace(DefaultCredentialsError=DefaultCredentialsError)

    def _default_credentials(*args, **kwargs):
        raise DefaultCredentialsError()

    auth_module.default = _default_credentials
    module_map['google.auth'] = auth_module

    sys.modules.update(module_map)
