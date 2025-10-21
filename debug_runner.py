import asyncio
import json
import logging
import os

# ===================================================================
# 端到端测试脚本：完整运行 test_signal_generator 意图
# ===================================================================

# 1. 导入所需类
from lib.environment import Environment
from strategies.test_signal_generator import TestSignalGenerator

# 2. 主测试函数
async def run_e2e_test():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # --- 初始化环境 (将连接到真实的 IB Gateway) ---
    # 确保容器内的环境变量已设置 (通常在 docker run 时通过 -e 传入)
    # 如果没有，可以在这里手动设置用于调试
    os.environ.setdefault('TRADING_MODE', 'paper')
    os.environ.setdefault('TWS_VERSION', '1030')
    # ... 其他需要的环境变量 ...

    env = Environment()
    
    try:
        # --- 连接 IB Gateway ---
        logging.info("--- [E2E_TEST] Attempting to connect to IB Gateway... ---")
        # 使用一个合理的超时时间
        await env.ibgw.connectAsync(host='127.0.0.1', port=4002, clientId=1, timeout=30)
        
        if not env.ibgw.isConnected():
            logging.error("--- [E2E_TEST] FAILED to connect to IB Gateway. ---")
            return

        logging.info("--- [E2E_TEST] Connection successful. ---")

        # --- 实例化并运行意图 ---
        logging.info("--- [E2E_TEST] Instantiating and running TestSignalGenerator... ---")
        intent_to_test = TestSignalGenerator(env=env)
        
        # 完整运行 `run()` 方法，它会调用 `_core_async`
        result = await intent_to_test.run()
        
        logging.info("--- [E2E_TEST] Finished intent execution. ---")
        
        # --- 打印最终结果 ---
        # 使用 default=str 来处理无法序列化的 datetime 等对象
        logging.info(f"--- FINAL RESULT ---\n{json.dumps(result, indent=2, default=str)}")

    except Exception as e:
        logging.critical(f"--- [E2E_TEST] An unexpected error occurred: {e} ---", exc_info=True)
    finally:
        if env.ibgw.isConnected():
            env.ibgw.disconnect()
        logging.info("--- [E2E_TEST] Test finished. ---")


# 3. 运行测试
if __name__ == "__main__":
    try:
        # 确保 nest_asyncio 被应用，以防万一
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(run_e2e_test())
    except Exception as e:
        logging.critical(f"An error occurred at the top level: {e}", exc_info=True)
