# --- START OF REVISED test_ibgw.py ---

import unittest
from unittest.mock import MagicMock, patch

# 确保导入了我们将要模拟的库
import socket
import time  # <--- [FIX] Import the time module

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

    # --- [FIX] Patched time.sleep and added it as an argument ---
    @patch('lib.ibgw.time.sleep')
    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_success_after_retries(self, mock_socket, mock_time_sleep):
        """
        场景1: 端口在几次尝试后成功打开，然后成功连接。
        """
        # --- MOCK 设置 ---
        self.test_obj.isConnected.return_value = False
        mock_connect = self._setup_socket_mock(mock_socket, [
            ConnectionRefusedError, 
            socket.timeout, 
            None 
        ]).connect

        # --- 执行 ---
        self.test_obj.start_and_connect()

        # --- 断言 ---
        self.test_obj.ibc.start.assert_called_once()
        self.assertEqual(mock_connect.call_count, 3)
        # [FIX] Assert against the correctly mocked time.sleep
        self.assertEqual(mock_time_sleep.call_count, 2)
        self.test_obj.connect.assert_called_once_with(**self.test_obj.ib_config, timeout=30)
        self.test_obj.ibc.terminate.assert_not_called()

    # --- [FIX] Patched time.sleep and added it as an argument ---
    @patch('lib.ibgw.time.sleep')
    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_timeout_failure(self, mock_socket, mock_time_sleep):
        """
        场景2: 端口在超时时间内一直未能打开。
        """
        # --- MOCK 设置 ---
        self.test_obj.isConnected.return_value = False
        self._setup_socket_mock(mock_socket, ConnectionRefusedError)

        # --- 执行 & 断言 ---
        with self.assertRaises(TimeoutError):
            self.test_obj.start_and_connect()

        self.test_obj.ibc.start.assert_called_once()
        # [FIX] Assert against the correctly mocked time.sleep
        self.assertGreater(mock_time_sleep.call_count, 1)
        self.test_obj.connect.assert_not_called()
        self.test_obj.ibc.terminate.assert_called_once()


    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_already_connected(self, mock_socket):
        """
        场景3: 调用方法时已经处于连接状态。
        """
        # --- MOCK 设置 ---
        self.test_obj.isConnected.return_value = True

        # --- 执行 ---
        self.test_obj.start_and_connect()

        # --- 断言 ---
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

# --- END OF REVISED test_ibgw.py ---