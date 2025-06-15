# --- START OF FILE test_ibgw.py ---

import unittest
from unittest.mock import MagicMock, patch, call

# 确保导入了我们将要模拟的库
import socket

from lib.ibgw import IBGW


class TestIbgw(unittest.TestCase):

    # 为了测试方便，我们使用较短的超时时间
    CONNECTION_TIMEOUT = 10
    TIMEOUT_SLEEP = 2
    IB_CONFIG = {'host': '127.0.0.1', 'port': 4001}
    IBC_CONFIG = {'twsPath': 'tws/path'}

    @patch('lib.ibgw.IB')
    @patch('lib.ibgw.IBC')
    def setUp(self, _, __):
        self.test_obj = IBGW(self.IBC_CONFIG, self.IB_CONFIG, self.CONNECTION_TIMEOUT, self.TIMEOUT_SLEEP)
        # 为所有外部依赖项创建 mock
        self.test_obj.ibc = MagicMock(start=MagicMock(), terminate=MagicMock())
        self.test_obj.isConnected = MagicMock()
        self.test_obj.connect = MagicMock()
        self.test_obj.disconnect = MagicMock()
        self.test_obj.sleep = MagicMock()


    # 这是一个辅助函数，用于简化对 socket.socket 的 mock 设置
    def _setup_socket_mock(self, patcher, side_effects):
        mock_socket_instance = MagicMock()
        mock_socket_instance.connect.side_effect = side_effects
        
        mock_socket_context_manager = MagicMock()
        mock_socket_context_manager.__enter__.return_value = mock_socket_instance
        
        patcher.return_value = mock_socket_context_manager
        return mock_socket_instance

    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_success_after_retries(self, mock_socket):
        """
        场景1: 端口在几次尝试后成功打开，然后成功连接。
        """
        # --- MOCK 设置 ---
        # 模拟尚未连接
        self.test_obj.isConnected.return_value = False
        
        # 模拟 socket.connect() 的行为：前两次失败，第三次成功
        # 'None' 代表成功调用，没有抛出异常
        mock_connect = self._setup_socket_mock(mock_socket, [
            ConnectionRefusedError, 
            socket.timeout, 
            None 
        ]).connect

        # --- 执行 ---
        self.test_obj.start_and_connect()

        # --- 断言 ---
        # 验证 IBC 启动了
        self.test_obj.ibc.start.assert_called_once()
        # 验证 socket.connect 被调用了3次
        self.assertEqual(mock_connect.call_count, 3)
        # 验证 sleep 被调用了2次 (在前两次失败后)
        self.assertEqual(self.test_obj.sleep.call_count, 2)
        # 验证最终的 ib_insync.connect 被调用
        self.test_obj.connect.assert_called_once_with(**self.test_obj.ib_config, timeout=30)
        # 验证 IBC.terminate 没有被调用
        self.test_obj.ibc.terminate.assert_not_called()

    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_timeout_failure(self, mock_socket):
        """
        场景2: 端口在超时时间内一直未能打开。
        """
        # --- MOCK 设置 ---
        # 模拟尚未连接
        self.test_obj.isConnected.return_value = False
        # 模拟 socket.connect() 总是失败
        mock_connect = self._setup_socket_mock(mock_socket, ConnectionRefusedError).connect

        # --- 执行 & 断言 ---
        # 验证代码是否按预期抛出了 TimeoutError
        with self.assertRaises(TimeoutError):
            self.test_obj.start_and_connect()

        # 验证 IBC 启动了
        self.test_obj.ibc.start.assert_called_once()
        # 验证 sleep 被调用了多次 (具体次数取决于超时设置)
        self.assertGreater(self.test_obj.sleep.call_count, 1)
        # 验证 ib_insync.connect 从未被调用
        self.test_obj.connect.assert_not_called()
        # 验证 IBC.terminate 被调用了，以清理资源
        self.test_obj.ibc.terminate.assert_called_once()


    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_already_connected(self, mock_socket):
        """
        场景3: 调用方法时已经处于连接状态。
        """
        # --- MOCK 设置 ---
        # 模拟已经连接
        self.test_obj.isConnected.return_value = True

        # --- 执行 ---
        self.test_obj.start_and_connect()

        # --- 断言 ---
        # 验证没有执行任何启动或连接操作
        self.test_obj.ibc.start.assert_not_called()
        mock_socket.assert_not_called()
        self.test_obj.connect.assert_not_called()

    def test_stop_and_terminate(self):
        """
        这个测试用例不受影响，保持原样。
        """
        self.test_obj.stop_and_terminate()
        self.test_obj.disconnect.assert_called_once()
        self.test_obj.ibc.terminate.assert_called_once()
        self.test_obj.sleep.assert_called_once_with(0)

# 如果你直接运行这个文件，需要这个
if __name__ == '__main__':
    unittest.main()

# --- END OF FILE test_ibgw.py ---