import asyncio
import json
import logging
import os

# ===================================================================
# 最终验证脚本：完整、干净地运行一次 test_signal_generator 意图
# ===================================================================

# 1. 导入所需类
from lib.environment import Environment
from strategies.test_signal_generator import TestSignalGenerator

# 2. 主测试函数
async def run_final_test():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # --- 初始化环境 (将连接到真实的 IB Gateway) ---
    os.environ.setdefault('TRADING_MODE', 'paper')
    os.environ.setdefault('TWS_VERSION', '1030')
    # 确保 PROJECT_ID 存在，以便 Firestore 初始化
    os.environ.setdefault('PROJECT_ID', 'gold-gearbox-424413-k1')

    env = Environment()
    
    try:
        # --- 连接 IB Gateway ---
        logging.info("--- [FINAL_TEST] Attempting to connect to IB Gateway... ---")
        await env.ibgw.connectAsync(host='127.0.0.1', port=4002, clientId=1, timeout=30)
        
        if not env.ibgw.isConnected():
            logging.error("--- [FINAL_TEST] FAILED to connect to IB Gateway. ---")
            return

        logging.info("--- [FINAL_TEST] Connection successful. ---")

        # --- 实例化并运行意图 ---
        logging.info("--- [FINAL_TEST] Instantiating and running TestSignalGenerator... ---")
        intent_to_test = TestSignalGenerator(env=env)
        
        # 完整运行 `run()` 方法
        result = await intent_to_test.run()
        
        logging.info("--- [FINAL_TEST] Finished intent execution. ---")
        
        # --- 打印最终结果 ---
        logging.info(f"--- FINAL RESULT ---\n{json.dumps(result, indent=2, default=str)}")

    except Exception as e:
        logging.critical(f"--- [FINAL_TEST] An unexpected error occurred: {e} ---", exc_info=True)
    finally:
        if env.ibgw.isConnected():
            env.ibgw.disconnect()
        logging.info("--- [FINAL_TEST] Test finished. ---")


# 3. 运行测试
if __name__ == "__main__":
    try:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(run_final_test())
    except Exception as e:
        logging.critical(f"An error occurred at the top level: {e}", exc_info=True)
