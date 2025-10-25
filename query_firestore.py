import sys
from google.cloud import firestore
import os

# ===================================================================
# 全功能 Firestore 查询脚本 (中文版)
# ===================================================================

# 初始化 Firestore 客户端
try:
    db = firestore.Client()
except Exception as e:
    print(f"错误：初始化Firestore客户端失败: {e}")
    print("请确保您已通过gcloud认证 (gcloud auth application-default login) 并设置了项目。")
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
        # 按时间戳降序排序（如果存在）
        try:
            query = collection_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.stream()
        except Exception:
            # 如果没有 timestamp 字段，则不排序
            docs = collection_ref.limit(limit).stream()

        doc_list = list(docs)
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
    print(f" Firestore 数据库快照 (模式: {trading_mode})")
    print("===============================================")

    # 1. 查询 config 集合
    query_collection('config')

    # 2. 查询 holdings 集合 (新架构)
    print(f"\n---  查询持仓快照 (新架构) ---")
    try:
        holdings_doc_ref = db.document(f'positions/{trading_mode}/holdings/all_positions')
        doc = holdings_doc_ref.get()
        if doc.exists:
            print_doc(doc)
        else:
            print("  (没有找到 'all_positions' 持仓快照文档)")
    except Exception as e:
        print(f"错误: 查询持仓快照失败: {e}")

    # 3. 查询 openOrders 集合
    query_collection(f'positions/{trading_mode}/openOrders')

    # 4. 查询 activity 集合 (新增)
    query_collection('activity')

    print("\n--- 查询完毕 ---")
