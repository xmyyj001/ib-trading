import importlib
import lib.trading

# --- 关键步骤：重新加载模块 ---
importlib.reload(lib.trading)
print("--- Module 'lib.trading' has been reloaded. ---")

# --- 验证修改是否生效 ---
from lib.trading import Trade
from lib.environment import Environment

# 1. 创建一个模拟的 env 对象
env = Environment()

# 2. 创建一个模拟的、非列表形式的策略对象
class MockStrategy:
    pass

my_single_strategy = MockStrategy()

# 3. 使用单个对象实例化 Trade 类
try:
    trade_obj = Trade(env, my_single_strategy)
    
    # 4. 检查 _strategies 属性是否被成功转换为了列表
    if isinstance(trade_obj._strategies, list) and len(trade_obj._strategies) == 1:
        print("--- SUCCESS: Trade class correctly wrapped a single object into a list. ---")
        print(f"trade_obj._strategies is now: {trade_obj._strategies}")
    else:
        print("--- FAILED: Trade class did NOT correctly wrap the object. ---")

except Exception as e:
    print(f"--- FAILED: An error occurred during instantiation: {e} ---")
