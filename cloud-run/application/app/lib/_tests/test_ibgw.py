import unittest
from unittest.mock import MagicMock, mock_open, patch, ANY

# 确保导入 ANY，它在新的断言中非常有用
from lib.ibgw import IBGW


class TestIbgw(unittest.TestCase):

    CONNECTION_TIMEOUT = 60
    IB_CONFIG = {'abc': 123, 'def': 'ghi'}
    IBC_CONFIG = {'abc': 123, 'twsPath': 'tws/path'}
    TIMEOUT_SLEEP = 5

    @patch('lib.ibgw.IB')
    @patch('lib.ibgw.IBC')
    def setUp(self, *_):
        self.test_obj = IBGW(self.IBC_CONFIG, self.IB_CONFIG, self.CONNECTION_TIMEOUT, self.TIMEOUT_SLEEP)

    @patch('lib.ibgw.IB')
    @patch('lib.ibgw.IBC')
    def test_init(self, ibc, *_):
        # 这个测试用例不受影响，保持原样
        ibgw = IBGW(self.IBC_CONFIG, self.IB_CONFIG, self.CONNECTION_TIMEOUT, self.TIMEOUT_SLEEP)
        self.assertDictEqual(self.IBC_CONFIG, ibgw.ibc_config)
        self.assertDictEqual({**self.test_obj.IB_CONFIG, **self.IB_CONFIG}, ibgw.ib_config)
        self.assertEqual(self.CONNECTION_TIMEOUT, ibgw.connection_timeout)
        self.assertEqual(self.TIMEOUT_SLEEP, ibgw.timeout_sleep)
        try:
            ibc.assert_called_once_with(**self.IBC_CONFIG)
        except AssertionError:
            self.fail()

        ibgw = IBGW(self.IBC_CONFIG)
        self.assertDictEqual(self.IBC_CONFIG, ibgw.ibc_config)
        self.assertDictEqual(self.test_obj.IB_CONFIG, ibgw.ib_config)
        self.assertEqual(self.CONNECTION_TIMEOUT, ibgw.connection_timeout)
        self.assertEqual(self.TIMEOUT_SLEEP, ibgw.timeout_sleep)

    @patch('lib.ibgw.logging')
    def test_start_and_connect(self, logging):
        # --- 核心修改区域开始 ---
        # 旧的测试逻辑是基于一个 `while not self.isConnected()` 循环，
        # 它会反复调用 self.sleep()。
        # 新的逻辑是直接调用 self.connect()，让它自己处理超时和重试，
        # 所以我们不再需要验证 self.sleep() 的调用。
        
        # 我们需要模拟的对象保持不变
        self.test_obj.ibc = MagicMock(start=MagicMock(), terminate=MagicMock()) # 为 terminate 也添加 mock
        self.test_obj.isConnected = MagicMock()
        self.test_obj.connect = MagicMock()
        self.test_obj.sleep = MagicMock() # 尽管不再检查，但保留 mock 以防其他地方用到

        # --- 场景1: 成功连接 ---
        # 模拟尚未连接
        self.test_obj.isConnected.return_value = False 
        
        # 调用被测试的方法
        self.test_obj.start_and_connect()

        # 新的断言：验证 ibc.start() 被调用了一次
        self.test_obj.ibc.start.assert_called_once()
        
        # 新的断言：验证 self.connect() 被调用了一次，并且传入了正确的参数
        # 注意这里我们把 timeout 参数也加了进去，以匹配新方法的调用签名
        self.test_obj.connect.assert_called_once_with(
            **self.test_obj.ib_config, 
            timeout=self.CONNECTION_TIMEOUT
        )

        # 新的断言（可选，但推荐）：验证 self.sleep() 没有被调用
        self.test_obj.sleep.assert_not_called()

        # --- 场景2: 已经连接 ---
        # 重置 mock 对象以便进行下一次测试
        self.test_obj.ibc.start.reset_mock()
        self.test_obj.connect.reset_mock()
        
        # 模拟已经连接
        self.test_obj.isConnected.return_value = True

        # 再次调用被测试的方法
        self.test_obj.start_and_connect()

        # 新的断言：验证 start 和 connect 都没有被调用
        self.test_obj.ibc.start.assert_not_called()
        self.test_obj.connect.assert_not_called()

        # --- 场景3: 连接失败并超时 ---
        # 重置 mock 对象
        self.test_obj.ibc.start.reset_mock()
        self.test_obj.connect.reset_mock()
        self.test_obj.ibc.terminate.reset_mock()
        
        # 模拟尚未连接
        self.test_obj.isConnected.return_value = False
        # 模拟 connect 方法总是抛出异常
        self.test_obj.connect.side_effect = ConnectionRefusedError("Test connection refused")
        
        # 使用 assertRaises 来验证是否抛出了我们预期的异常
        # 这里的 TimeoutError 是我们自己代码里 raise 的，不是 gunicorn 的
        with self.assertRaises(ConnectionRefusedError):
            self.test_obj.start_and_connect()

        # 新的断言：验证即使连接失败，我们也尝试调用了 ibc.terminate() 来清理
        self.test_obj.ibc.terminate.assert_called_once()
        # --- 核心修改区域结束 ---


    def test_stop_and_terminate(self):
        # 这个测试用例不受影响，保持原样
        self.test_obj.disconnect = MagicMock()
        self.test_obj.ibc.terminate = MagicMock()
        self.test_obj.sleep = MagicMock()

        self.test_obj.stop_and_terminate()
        try:
            self.test_obj.disconnect.assert_called_once()
            self.test_obj.ibc.terminate.assert_called_once()
            self.test_obj.sleep.assert_called_once_with(0)
        except AssertionError:
            self.fail()

        self.test_obj.stop_and_terminate(5)
        try:
            self.test_obj.sleep.assert_called_with(5)
        except AssertionError:
            self.fail()


if __name__ == '__main__':
    unittest.main()