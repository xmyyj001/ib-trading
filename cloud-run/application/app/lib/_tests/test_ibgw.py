# --- START OF FULLY REVISED test_ibgw.py ---

import unittest
from unittest.mock import MagicMock, patch, AsyncMock  # Import AsyncMock

# 确保导入了我们将要模拟的库
import socket
import time

from lib.ibgw import IBGW


class TestIbgw(unittest.TestCase):

    # 为了测试方便，我们使用较短的超时时间
    CONNECTION_TIMEOUT = 10
    TIMEOUT_SLEEP = 2
    IB_CONFIG = {'host': '127.0.0.1', 'port': 4001}
    IBC_CONFIG = {'twsPath': 'tws/path'}

    # [FIX 1] The setUp method needs to know about the new 'terminateAsync' method
    # and make it an "awaitable" mock.
    @patch('lib.ibgw.IB')
    @patch('lib.ibgw.IBC')
    def setUp(self, _, __):
        self.test_obj = IBGW(self.IBC_CONFIG, self.IB_CONFIG, self.CONNECTION_TIMEOUT, self.TIMEOUT_SLEEP)
        # 为所有外部依赖项创建 mock
        self.test_obj.ibc = MagicMock(
            start=MagicMock(),
            terminate=MagicMock(), # Keep mocking the sync version for other tests
            terminateAsync=AsyncMock() # Mock the async version as an awaitable
        )
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

    # This test is correct and requires no changes
    @patch('lib.ibgw.time.sleep')
    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_success_after_retries(self, mock_socket, mock_time_sleep):
        """
        场景1: 端口在几次尝试后成功打开，然后成功连接。
        """
        self.test_obj.isConnected.return_value = False
        mock_connect = self._setup_socket_mock(mock_socket, [
            ConnectionRefusedError, 
            socket.timeout, 
            None 
        ]).connect

        self.test_obj.start_and_connect()

        self.test_obj.ibc.start.assert_called_once()
        self.assertEqual(mock_connect.call_count, 3)
        self.assertEqual(mock_time_sleep.call_count, 2)
        self.test_obj.connect.assert_called_once_with(**self.test_obj.ib_config, timeout=30)
        self.test_obj.ibc.terminate.assert_not_called()

    # This test is correct and requires no changes
    @patch('lib.ibgw.time.sleep')
    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_timeout_failure(self, mock_socket, mock_time_sleep):
        """
        场景2: 端口在超时时间内一直未能打开。
        """
        self.test_obj.isConnected.return_value = False
        self._setup_socket_mock(mock_socket, ConnectionRefusedError)

        with self.assertRaises(TimeoutError):
            self.test_obj.start_and_connect()

        self.test_obj.ibc.start.assert_called_once()
        self.assertGreater(mock_time_sleep.call_count, 1)
        self.test_obj.connect.assert_not_called()
        self.test_obj.ibc.terminate.assert_called_once()

    # This test is correct and requires no changes
    @patch('lib.ibgw.socket.socket')
    def test_start_and_connect_already_connected(self, mock_socket):
        """
        场景3: 调用方法时已经处于连接状态。
        """
        self.test_obj.isConnected.return_value = True

        self.test_obj.start_and_connect()

        self.test_obj.ibc.start.assert_not_called()
        mock_socket.assert_not_called()
        self.test_obj.connect.assert_not_called()

    # --- [FIX 2] This is the test that was failing. ---
    # We need to patch 'util.run' to prevent it from actually running an event loop
    # and then assert that the correct async method was called.
    @patch('lib.ibgw.util.run')
    def test_stop_and_terminate(self, mock_util_run):
        """
        这个测试用例现在验证异步调用的正确性。
        """
        # Arrange
        self.test_obj.isConnected.return_value = True

        # Act
        self.test_obj.stop_and_terminate()

        # Assert
        self.test_obj.disconnect.assert_called_once()
        
        # Assert that the async method was called
        self.test_obj.ibc.terminateAsync.assert_called_once()
        
        # Assert that util.run was called with the result of the async method
        mock_util_run.assert_called_once_with(self.test_obj.ibc.terminateAsync.return_value)

        # Assert that the synchronous sleep was NOT called (for wait=0)
        self.test_obj.sleep.assert_not_called()
        
        # Test the 'wait' parameter
        self.test_obj.sleep.reset_mock()
        self.test_obj.stop_and_terminate(wait=5)
        self.test_obj.sleep.assert_called_once_with(5)


# 如果你直接运行这个文件，需要这个
if __name__ == '__main__':
    unittest.main()

# --- END OF FULLY REVISED test_ibgw.py ---