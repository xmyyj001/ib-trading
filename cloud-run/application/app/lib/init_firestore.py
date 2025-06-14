import sys
from google.cloud import firestore

# 从命令行参数获取项目ID
if len(sys.argv) < 2:
    print("错误：请提供项目ID作为第一个参数。")
    print("用法: python init_firestore.py [YOUR_PROJECT_ID]")
    sys.exit(1)

project_id = sys.argv[1]

print(f"正在为项目 '{project_id}' 初始化 Firestore 配置...")

# 初始化 Firestore 客户端
db = firestore.Client(project=project_id)

# 定义要创建的文档
# 你可以在这里定义你的默认配置
# 如果文档已存在，此操作会覆盖它，所以是安全的。
config_docs = {
    "config": {
        "common": {
            "default_setting": "hello_world",
            "risk_limit": 0.01
        },
        "paper": {
            "strategy_enabled": True,
            "max_positions": 5
        },
        "live": {
            "strategy_enabled": False,
            "max_positions": 10
        }
    }
}

# 遍历并创建/更新文档
for collection, documents in config_docs.items():
    for doc_id, data in documents.items():
        doc_ref = db.collection(collection).document(doc_id)
        doc_ref.set(data)
        print(f"成功创建/更新文档: '{collection}/{doc_id}'")

print("Firestore 配置初始化完成。")