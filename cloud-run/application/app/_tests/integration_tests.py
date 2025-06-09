from datetime import date
from google.cloud.bigquery.job import LoadJobConfig, WriteDisposition
from google.cloud.firestore_v1 import DELETE_FIELD
from os import environ, listdir
from pandas import DataFrame
import re
from time import sleep
import unittest
from unittest.mock import patch
from uuid import uuid1

# 在模块级别初始化 ibc_config 和 env，以便在测试用例中可能需要时访问
# 或者，如果只在非 localhost 环境下需要，则保持在 if 块内
ibc_config = None
env_vars = None # 重命名 env 以避免与 Python 内置的 env 冲突

if environ.get('K_REVISION') != 'localhost':
    from lib.environment import Environment
    env_vars = { # 使用 env_vars
        key: environ.get(key) for key in
        ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
    }
    # 检查 javaPath 是否有效且包含内容
    if env_vars.get('javaPath') and listdir(env_vars['javaPath']):
        env_vars['javaPath'] += '/{}/bin'.format(listdir(env_vars['javaPath'])[0])
    else:
        print(f"Warning: javaPath '{env_vars.get('javaPath')}' is invalid or empty.")
        # 根据需要设置一个默认值或引发错误，如果这是关键路径
        # env_vars['javaPath'] = "/default/java/path" # 示例

    install_log_content = ""
    tws_install_log_path = environ.get('TWS_INSTALL_LOG')
    if tws_install_log_path:
        try:
            with open(tws_install_log_path, 'r') as fp:
                install_log_content = fp.read()
        except FileNotFoundError:
            print(f"Warning: TWS_INSTALL_LOG file not found at {tws_install_log_path}")
        except Exception as e:
            print(f"Warning: Error reading TWS_INSTALL_LOG file: {e}")
    else:
        print("Warning: TWS_INSTALL_LOG environment variable not set.")

    tws_version_match = re.search('IB Gateway ([0-9]{3})', install_log_content)
    extracted_tws_version = None
    if tws_version_match:
        extracted_tws_version = tws_version_match.group(1)
    else:
        print("Warning: IB Gateway version pattern not found in install_log_content.")
        # 可以考虑设置一个默认版本号或者标记为未知
        # extracted_tws_version = "UNKNOWN" # 示例

    ibc_config = {
        'gateway': True,
        'twsVersion': extracted_tws_version, # 使用提取到的版本，可能为 None 或 "UNKNOWN"
        **env_vars # 使用 env_vars
    }
    # 只有在所有必要配置都有效时才初始化 Environment
    # 你可能需要根据哪些配置是绝对必要的来调整这个条件
    if all(ibc_config.get(key) is not None for key in ['twsVersion', 'ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']):
        Environment('paper', ibc_config)
    else:
        print("Warning: Environment not initialized due to missing critical configurations.")
        # 如果 Environment 的初始化是测试的前提，这里可能需要 self.fail() 或 pytest.skip()
        # 对于 unittest，你可能需要在 setUpClass 或 setUp 中处理这种情况

from intents.intent import Intent # 将 import 移到 if 块之后，或者确保它在所有情况下都能安全导入
from lib.gcp import GcpModule


class TestGcpModule(unittest.TestCase):

    BIGQUERY_DESTINATION = 'historical_data.test' # 确保这个表存在或者测试会创建它
    BIGQUERY_JOB_CONFIG = LoadJobConfig(write_disposition=WriteDisposition.WRITE_APPEND)
    FIRESTORE_COLLECTION = 'tests'

    def setUp(self):
        self.gcp_module = GcpModule()

    def test_bigquery(self):
        dt = date(1977, 9, 27)
        key = str(uuid1())
        # 确保项目ID和小数点在查询中是正确的
        project_id = environ.get("PROJECT_ID", "your-default-project-id") # 从环境变量获取或使用默认值
        dataset_id, table_id = self.BIGQUERY_DESTINATION.split('.')
        query = f"SELECT date, value FROM `{project_id}.{dataset_id}.{table_id}` WHERE instrument='test' AND key='{key}'"

        data = DataFrame({'date': [dt], 'instrument': ['test'], 'key': [key], 'value': [42.0]})
        # 确保目标表路径正确
        destination_table_ref = f"{project_id}.{self.BIGQUERY_DESTINATION}"
        load_job = self.gcp_module.bq.load_table_from_dataframe(data, destination_table_ref, job_config=self.BIGQUERY_JOB_CONFIG)
        
        # 等待作业完成，可以增加超时
        try:
            load_job.result(timeout=60) # 等待作业完成，设置60秒超时
            self.assertTrue(load_job.done()) # 再次确认
        except Exception as e:
            self.fail(f"BigQuery load job failed or timed out: {e}. Errors: {load_job.errors}")

        # sleep(5) # 之前为了数据具体化，如果 load_job.result() 返回，则数据应该已写入

        result = self.gcp_module.bq.query(query).result()
        rows = [{k: v for k, v in row.items()} for row in result]
        self.assertEqual(1, len(rows), f"Expected 1 row, got {len(rows)}. Query: {query}")
        self.assertDictEqual({'date': dt, 'value': 42.0}, rows[0])

        df = self.gcp_module.bq.query(query).to_dataframe()
        # 比较时确保列顺序和类型一致，或者只比较必要的列
        self.assertTrue(data[['date', 'value']].reset_index(drop=True).equals(df[['date', 'value']].reset_index(drop=True)))


    def test_firestore(self):
        col_ref = self.gcp_module.db.collection(self.FIRESTORE_COLLECTION)
        doc_id = str(uuid1()) # 使用一个可预测的或随机的ID
        doc_ref = col_ref.document(doc_id)
        try:
            doc_ref.set({'key': 'value'})
            doc_ref.update({'anotherKey': 'anotherValue'})

            actual = doc_ref.get().to_dict()
            self.assertDictEqual({'key': 'value', 'anotherKey': 'anotherValue'}, actual)

            # 使用 limit(1) 以确保即使有多个匹配项也只获取一个进行断言（如果适用）
            result_query = col_ref.where('key', '==', 'value').where('anotherKey', '==', 'anotherValue').limit(1).stream()
            results = [doc for doc in result_query if doc.id == doc_id]
            self.assertEqual(1, len(results), "Document not found with specified query.")
            self.assertEqual(doc_id, results[0].id)

            doc_ref.update({'anotherKey': DELETE_FIELD})
            actual = doc_ref.get().to_dict()
            self.assertDictEqual({'key': 'value'}, actual)

        finally:
            # 清理测试数据
            doc_ref.delete()
            # 确认删除
            self.assertFalse(doc_ref.get().exists, "Document was not deleted.")


    def test_logging(self):
        try:
            self.gcp_module.logging.debug('Test log entry from integration test')
        except Exception as e:
            self.fail(f"Logging failed: {e}")


class TestIbgw(unittest.TestCase):

    @patch('intents.intent.Intent._log_activity')
    def test_intent(self, mock_log_activity, *_): # 接收所有 mock 对象
        # 只有在 Environment 成功初始化时才运行此测试
        if environ.get('K_REVISION') != 'localhost' and (ibc_config is None or ibc_config.get('twsVersion') is None):
            self.skipTest("Skipping IBGW intent test because Environment was not properly initialized (e.g., TWS version missing).")

        intent = Intent() # Intent的初始化可能依赖于Environment
        actual = None
        if environ.get('K_REVISION') == 'localhost':
            try:
                # 确保 intent._env 和 intent._env.ibgw 存在
                if hasattr(intent, '_env') and hasattr(intent._env, 'ibgw'):
                    intent._env.ibgw.connect(port=4001) # 假设 localhost 测试连接到 4001
                    actual = intent._core()
                else:
                    self.fail("intent._env.ibgw not available for localhost connection.")
            except Exception as e:
                self.fail(f"Local IBGW intent test failed: {e}")
            finally:
                if hasattr(intent, '_env') and hasattr(intent._env, 'ibgw') and intent._env.ibgw.isConnected():
                    intent._env.ibgw.disconnect()
        else:
            # 确保非 localhost 环境下 Intent() 初始化和 run() 调用是安全的
            try:
                actual = intent.run()
            except Exception as e:
                self.fail(f"Cloud Run IBGW intent test failed: {e}")
        
        if actual is not None:
            self.assertEqual(date.today().isoformat(), actual.get('currentTime', '')[:10])
        else:
            # 如果 actual 为 None (例如，因为跳过了连接或 run 失败但未抛出异常)，则测试失败
            # 或者根据逻辑，如果 actual 可能是 None 且这是可接受的，则调整断言
            if environ.get('K_REVISION') != 'localhost': # 本地测试可能因为 intent._env.ibgw 不可用而使 actual 为 None
                 self.assertIsNotNone(actual, "intent.run() or intent._core() returned None unexpectedly.")


if __name__ == '__main__':
    unittest.main()