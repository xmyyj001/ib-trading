import sys
from google.cloud import firestore
import os

# ===================================================================
# 全功能 Firestore 查询脚本 (v3 - 明确项目ID)
# ===================================================================

if len(sys.argv) < 2:
    print("错误: 请提供 Google Cloud 项目ID 作为第一个参数。")
    print("用法: python query_firestore.py YOUR_PROJECT_ID")
    sys.exit(1)

project_id = sys.argv[1]

# 初始化 Firestore 客户端，并明确指定项目ID
try:
    db = firestore.Client(project=project_id)
except Exception as e:
    print(f"错误：初始化Firestore客户端失败: {e}")
    print("请确保您已通过gcloud认证 (gcloud auth application-default login)。")
    sys.exit(1)

def print_doc(doc):
    """打印单个文档的内容。"""
    print(f"\n📄 文档 ID: {doc.id}")
    print("---------------------------------")
    content = doc.to_dict()
    if not content:
        print("  (文档为空)")
        return
    for key, value in content.items():
        if isinstance(value, dict):
            print(f"  - {key}:")
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, dict):
                    print(f"    - {sub_key}:")
                    for sub_sub_key, sub_sub_value in sub_value.items():
                        print(f"      - {sub_sub_key}: {sub_sub_value}")
                else:
                    print(f"    - {sub_key}: {sub_value}")
        else:
            print(f"  - {key}: {value}")

def query_collection(collection_path, limit=10):
    """查询并打印指定集合的文档。"""
    print(f"\n---  查询集合: {collection_path} (最多显示 {limit} 条) ---")
    try:
        collection_ref = db.collection(collection_path)
        docs = list(collection_ref.stream())

        def _ts_key(doc):
            data = doc.to_dict() or {}
            ts = data.get('timestamp')
            if hasattr(ts, "isoformat"):
                return ts.isoformat()
            return ts or ""

        doc_list = sorted(docs, key=_ts_key, reverse=True)[:limit]
        if not doc_list:
            print("  (此集合中没有找到任何文档)")
            return
        for doc in doc_list:
            print_doc(doc)
    except Exception as e:
        print(f"错误：查询集合 '{collection_path}' 失败: {e}")

if __name__ == "__main__":
    trading_mode = os.environ.get('TRADING_MODE', 'paper')

    print("===============================================")
    print(f" Firestore 数据库快照 (项目: {project_id}, 模式: {trading_mode})")
    print("===============================================")

    # 1. 查询 config 集合
    query_collection('config')

    # 2. 查询最新快照 (优先 new snapshot, 回退 legacy holdings)
    print(f"\n---  查询持仓快照 (positions/{trading_mode}/latest_portfolio/snapshot) ---")
    try:
        snapshot_ref = db.document(f'positions/{trading_mode}/latest_portfolio/snapshot')
        snapshot_doc = snapshot_ref.get()
        if snapshot_doc.exists:
            print_doc(snapshot_doc)
        else:
            print("  (未找到 snapshot 文档，尝试 legacy holdings/all_positions)")
            holdings_doc_ref = db.document(f'positions/{trading_mode}/holdings/all_positions')
            doc = holdings_doc_ref.get()
            if doc.exists:
                print_doc(doc)
            else:
                print("  (legacy 持仓文档也不存在)")
    except Exception as e:
        print(f"错误: 查询持仓快照失败: {e}")

    # 3. 查询 openOrders 集合
    query_collection(f'positions/{trading_mode}/openOrders')

    # 4. 查询 activity 集合 (新增)
    query_collection('activity')

    print("\n--- 查询完毕 ---")
