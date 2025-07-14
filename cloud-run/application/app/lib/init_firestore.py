# init_firestore.py
import sys
from google.cloud import firestore

if len(sys.argv) < 2:
    print("错误：请提供项目ID作为第一个参数。")
    sys.exit(1)

project_id = sys.argv[1]
print(f"正在为项目 '{project_id}' 初始化 Firestore 配置...")

db = firestore.Client(project=project_id)

config_docs = {
    "config": {
        "common": {
            "default_setting": "hello_world",
            "risk_limit": 0.01,
            "marketDataType": 3,  # <-- 关键修复：添加缺失的配置项 (1=Live, 2=Frozen, 3=Delayed)
            "exposure": { # 新增 exposure 配置
                "overall": 1.0, # 整体风险敞口，例如 1.0 表示 100%
                "strategies": {
                    "dummy": 1.0 # dummy 策略的风险敞口，例如 1.0 表示 100%
                }
            }
        },
        "paper": {
            "strategy_enabled": True,
            "max_positions": 5,
            "account": "DU1888364" # <-- 关键修复：添加您的 paper trading 账号
        },
        "live": {
            "strategy_enabled": False,
            "max_positions": 10,
            "account": "YOUR_LIVE_ACCOUNT" # <-- 将来替换为您的真实账号
        }
    }
}

for collection, documents in config_docs.items():
    for doc_id, data in documents.items():
        doc_ref = db.collection(collection).document(doc_id)
        doc_ref.set(data)
        print(f"成功创建/更新文档: '{collection}/{doc_id}'")

print("Firestore 配置初始化完成。")