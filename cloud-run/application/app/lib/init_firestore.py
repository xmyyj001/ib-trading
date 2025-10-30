import sys
from google.cloud import firestore

if len(sys.argv) < 2:
    print("错误：请提供项目ID作为第一个参数。")
    print("用法: python init_firestore.py YOUR_PROJECT_ID")
    sys.exit(1)

project_id = sys.argv[1]
print(f"正在为项目 '{project_id}' 初始化 Firestore 配置...")

db = firestore.Client(project=project_id)

# Correctly formatted configuration data
config_data = {
    "common": {
        "tradingEnabled": False,
        "enforceFlatEod": False,
        "marketDataType": 2,
        "defaultOrderType": "LMT",
        "defaultOrderTif": "GTC",
        "retryCheckMinutes": 1440,
        "exposure": {
            "overall": 0.9,
            "strategies": {
                "spy_macd_vixy": 1.0,
                "testsignalgenerator": 1.0, # Correctly added here
                "dummy": 1.0
            }
        }
    },
    "paper": {
        "account": "DU1888364"
    },
    "live": {
        "account": "[REPLACE_WITH_YOUR_LIVE_ACCOUNT]"
    }
}

def initialize_firestore():
    """Writes the defined configuration to Firestore, overwriting existing docs."""
    for doc_id, data in config_data.items():
        doc_ref = db.collection("config").document(doc_id)
        try:
            doc_ref.set(data)
            print(f"成功创建/更新文档: 'config/{doc_id}'")
        except Exception as e:
            print(f"错误：写入文档 'config/{doc_id}'失败: {e}")
            sys.exit(1)
    
    print("\nFirestore 配置初始化完成。")
    print("重要提示: 请记得到 Firestore 控制台将 config/common -> tradingEnabled 设置为 true 以开启交易。")

if __name__ == "__main__":
    initialize_firestore()
