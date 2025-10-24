import sys
from google.cloud import firestore
import os

# ===================================================================
# 全功能 Firestore 查询脚本
# ===================================================================

# 初始化 Firestore 客户端
# 它会自动使用 gcloud CLI 或环境变量中的项目和认证信息
try:
    db = firestore.Client()
except Exception as e:
    print(f"Error initializing Firestore client: {e}")
    print("Please ensure you are authenticated with gcloud ('gcloud auth application-default login') and have specified a project.")
    sys.exit(1)


def query_collection(collection_path):
    """一个辅助函数，用于查询并打印指定集合的所有文档。"""
    print(f"\n---  탐색 중인 컬렉션: {collection_path} ---")
    
    try:
        collection_ref = db.collection(collection_path)
        docs = collection_ref.stream()

        doc_list = list(docs) # 将生成器转换为列表以检查是否为空
        if not doc_list:
            print("이 컬렉션에서 문서를 찾을 수 없습니다.")
            return

        for doc in doc_list:
            print(f"\n📄 문서 ID: {doc.id}")
            print("---------------------------------")
            content = doc.to_dict()
            for key, value in content.items():
                # 如果值是字典，为了更好的可读性，进行特殊处理
                if isinstance(value, dict):
                    print(f"  - {key}:")
                    for sub_key, sub_value in value.items():
                        # 对第二层字典也进行特殊处理
                        if isinstance(sub_value, dict):
                            print(f"    - {sub_key}:")
                            for sub_sub_key, sub_sub_value in sub_value.items():
                                print(f"      - {sub_sub_key}: {sub_sub_value}")
                        else:
                            print(f"    - {sub_key}: {sub_value}")
                else:
                    print(f"  - {key}: {value}")
    except Exception as e:
        print(f"컬렉션 '{collection_path}' 조회 중 오류 발생: {e}")

if __name__ == "__main__":
    
    # 根据环境变量决定要查询的交易模式
    trading_mode = os.environ.get('TRADING_MODE', 'paper')

    print("===============================================")
    print(f" Firestore 데이터베이스 전체 스냅샷 조회")
    print("===============================================")

    # 1. 查询 config 集合
    query_collection('config')

    # 2. 查询 holdings 集合
    holdings_path = f'positions/{trading_mode}/holdings'
    query_collection(holdings_path)

    # 3. 查询 openOrders 集合
    open_orders_path = f'positions/{trading_mode}/openOrders'
    query_collection(open_orders_path)

    print("\n--- 조회 완료 ---")
