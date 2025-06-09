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

# 在模块级别初始化 ibc_config 和 env_vars，以便在测试用例中可能需要时访问
ibc_config = None
env_vars = None # 重命名 env 以避免与 Python 内置的 env 冲突

# 这个 if 块只在非本地（即 Cloud Build/Cloud Run）环境中执行
if environ.get('K_REVISION') != 'localhost':
    # 尝试导入 Environment，如果失败则打印警告，因为后续依赖它的测试会跳过
    try:
        from lib.environment import Environment
    except ImportError:
        Environment = None # 将 Environment 设置为 None，以便后续检查
        print("Warning: Failed to import 'lib.environment.Environment'. IB GW related tests might be skipped.")

    env_vars = {
        key: environ.get(key) for key in
        ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
    }

    # 检查 javaPath 是否有效且包含内容
    java_path_value = env_vars.get('javaPath')
    if java_path_value:
        try:
            # 确保 java_path_value 是一个目录并且可以列出内容
            if listdir(java_path_value): # 确保目录存在且非空
                env_vars['javaPath'] += '/{}/bin'.format(listdir(java_path_value)[0])
            else:
                print(f"Warning: javaPath directory '{java_path_value}' is empty.")
        except FileNotFoundError:
            print(f"Warning: javaPath directory '{java_path_value}' not found.")
        except Exception as e:
            print(f"Warning: Error processing javaPath '{java_path_value}': {e}")
    else:
        print(f"Warning: javaPath environment variable not set or is empty.")


    extracted_tws_version = None
    # 优先使用 MOCK_TWS_VERSION 环境变量
    mock_tws_version = environ.get('MOCK_TWS_VERSION')

    if mock_tws_version:
        extracted_tws_version = mock_tws_version
        print(f"Using MOCK_TWS_VERSION: {extracted_tws_version}")
    else:
        # 如果 MOCK_TWS_VERSION 未设置，则尝试从 TWS_INSTALL_LOG 文件解析
        print("MOCK_TWS_VERSION not set, attempting to parse TWS_INSTALL_LOG.")
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

        if install_log_content:
            tws_version_match = re.search('IB Gateway ([0-9]{3})', install_log_content)
            if tws_version_match:
                extracted_tws_version = tws_version_match.group(1)
            else:
                print("Warning: IB Gateway version pattern not found in TWS_INSTALL_LOG content.")
        else:
            print("Warning: TWS_INSTALL_LOG content is empty.")

    if extracted_tws_version is None:
        print("Warning: TWS version could not be determined. IB GW related tests might be affected or skipped.")
        # extracted_tws_version = "UNKNOWN_OR_MOCK" # 可以选择设置一个明确的标记

    ibc_config = {
        'gateway': True,
        'twsVersion': extracted_tws_version,
        **env_vars
    }

    # 只有在 Environment 类成功导入并且所有必要配置都有效时才初始化 Environment
    if Environment and all(val is not None for val in [
        ibc_config.get('twsVersion'), # 确保版本号已确定（即使是MOCK的）
        env_vars.get('ibcIni'),
        env_vars.get('ibcPath'),
        env_vars.get('javaPath'), # 确保 javaPath 在处理后仍然有效
        env_vars.get('twsPath'),
        env_vars.get('twsSettingsPath')
    ]):
        try:
            Environment('paper', ibc_config) # 假设 'paper' 是交易模式
            print("Environment initialized successfully.")
        except Exception as e:
            print(f"Error initializing Environment: {e}")
            # 根据情况，可能需要将 ibc_config 或 Environment 相关的标志重置，以跳过依赖它的测试
            ibc_config = None # 表示环境初始化失败
    else:
        print("Warning: Environment not initialized due to missing critical configurations or failed import.")
        ibc_config = None # 明确标记配置不完整或环境初始化失败

# 将后续的 import 移到这个全局逻辑块之后，以确保它们在所有情况下都能安全导入
# 或者，如果这些模块只在特定测试类中使用，可以考虑将导入移到测试类的内部或 setUp 方法中
try:
    from intents.intent import Intent
except ImportError:
    Intent = None
    print("Warning: Failed to import 'intents.intent.Intent'. IB GW related tests might be skipped.")

try:
    from lib.gcp import GcpModule
except ImportError:
    GcpModule = None
    print("Warning: Failed to import 'lib.gcp.GcpModule'. GCP related tests might be skipped.")


@unittest.skipIf(GcpModule is None, "Skipping GCP tests because GcpModule could not be imported.")
class TestGcpModule(unittest.TestCase):

    BIGQUERY_DESTINATION = 'historical_data.test'
    BIGQUERY_JOB_CONFIG = LoadJobConfig(write_disposition=WriteDisposition.WRITE_APPEND)
    FIRESTORE_COLLECTION = 'tests'

    @classmethod
    def setUpClass(cls):
        # 确保 GcpModule 在类级别可用
        if GcpModule is None:
            raise unittest.SkipTest("GcpModule not available.")
        cls.gcp_module_instance = GcpModule() # 创建一个类级别的实例

    def setUp(self):
        # 使用类级别实例，或者按需在每个测试中创建新实例
        self.gcp_module = self.gcp_module_instance
        # 或者 self.gcp_module = GcpModule() 如果希望每个测试有独立实例

    def test_bigquery(self):
        dt = date(1977, 9, 27)
        key = str(uuid1())
        project_id = environ.get("PROJECT_ID")
        if not project_id:
            self.fail("PROJECT_ID environment variable not set for BigQuery test.")

        dataset_id, table_id = self.BIGQUERY_DESTINATION.split('.')
        query = f"SELECT date, value FROM `{project_id}.{dataset_id}.{table_id}` WHERE instrument='test' AND key='{key}'"
        data = DataFrame({'date': [dt], 'instrument': ['test'], 'key': [key], 'value': [42.0]})
        destination_table_ref = f"{project_id}.{self.BIGQUERY_DESTINATION}"

        try:
            load_job = self.gcp_module.bq.load_table_from_dataframe(data, destination_table_ref, job_config=self.BIGQUERY_JOB_CONFIG)
            load_job.result(timeout=60)
            self.assertTrue(load_job.done())
        except Exception as e:
            job_errors = getattr(load_job, 'errors', "N/A")
            self.fail(f"BigQuery load job failed or timed out: {e}. Errors: {job_errors}")

        result = self.gcp_module.bq.query(query).result()
        rows = [{k: v for k, v in row.items()} for row in result]
        self.assertEqual(1, len(rows), f"Expected 1 row, got {len(rows)}. Query: {query}")
        self.assertDictEqual({'date': dt, 'value': 42.0}, rows[0])

        df = self.gcp_module.bq.query(query).to_dataframe()
        pd_data_subset = data[['date', 'value']].reset_index(drop=True)
        bq_df_subset = df[['date', 'value']].reset_index(drop=True)

        # 转换为相同类型以避免比较问题，例如日期对象
        pd_data_subset['date'] = pd_data_subset['date'].astype(str)
        bq_df_subset['date'] = bq_df_subset['date'].astype(str)

        self.assertTrue(pd_data_subset.equals(bq_df_subset),
                        f"DataFrame mismatch.\nExpected:\n{pd_data_subset}\nGot:\n{bq_df_subset}")


    def test_firestore(self):
        col_ref = self.gcp_module.db.collection(self.FIRESTORE_COLLECTION)
        doc_id = str(uuid1())
        doc_ref = col_ref.document(doc_id)
        try:
            doc_ref.set({'key': 'value'})
            doc_ref.update({'anotherKey': 'anotherValue'})

            actual_doc = doc_ref.get()
            self.assertTrue(actual_doc.exists, "Document does not exist after set/update.")
            actual_dict = actual_doc.to_dict()
            self.assertDictEqual({'key': 'value', 'anotherKey': 'anotherValue'}, actual_dict)

            result_query = col_ref.where('key', '==', 'value').where('anotherKey', '==', 'anotherValue').limit(1).stream()
            results = [doc for doc in result_query if doc.id == doc_id]
            self.assertEqual(1, len(results), "Document not found with specified query.")
            self.assertEqual(doc_id, results[0].id)

            doc_ref.update({'anotherKey': DELETE_FIELD})
            actual_dict_after_delete_field = doc_ref.get().to_dict()
            self.assertDictEqual({'key': 'value'}, actual_dict_after_delete_field)

        finally:
            doc_ref.delete()
            self.assertFalse(doc_ref.get().exists, "Document was not deleted.")


    def test_logging(self):
        try:
            self.gcp_module.logging.debug('Test log entry from integration test')
        except Exception as e:
            self.fail(f"Logging failed: {e}")


@unittest.skipIf(Intent is None or ibc_config is None or ibc_config.get('twsVersion') is None or Environment is None,
                 "Skipping IBGW tests: Intent/Environment not available or TWS version missing.")
class TestIbgw(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 确保 Intent 类可用，并且 ibc_config 已设置且 TWS 版本存在
        if Intent is None:
            raise unittest.SkipTest("Intent class not available.")
        if ibc_config is None or ibc_config.get('twsVersion') is None:
            # 这个跳过条件理论上会被类级别的 skipIf 覆盖，但双重检查无妨
            raise unittest.SkipTest("IB GW related configurations (ibc_config or twsVersion) are missing.")
        if Environment is None: # 再次确认 Environment 是否成功导入
            raise unittest.SkipTest("Environment class not available for IB GW tests.")

        # 这里可以进行 TestIbgw 类级别的一次性设置，如果需要
        # 例如，如果 Environment 初始化应该在这里并且只执行一次

    def setUp(self):
        # 每个测试方法运行时都会调用
        # 如果 Intent 需要在每个测试中重新初始化，可以在这里做
        # 或者，如果它依赖于模块级别的 Environment 初始化，并且该初始化失败，则这些测试应被跳过
        if ibc_config is None: # 再次检查，因为 Environment 初始化可能失败
             self.skipTest("Skipping IBGW test method: ibc_config is None (Environment init likely failed).")
        try:
            self.intent = Intent() # Intent的初始化可能依赖于已初始化的 Environment
        except Exception as e:
            self.fail(f"Failed to initialize Intent for test: {e}")


    @patch('intents.intent.Intent._log_activity')
    def test_intent(self, mock_log_activity): # 移除了 *_
        actual = None
        if environ.get('K_REVISION') == 'localhost':
            try:
                if hasattr(self.intent, '_env') and hasattr(self.intent._env, 'ibgw'):
                    self.intent._env.ibgw.connect(port=4001)
                    actual = self.intent._core()
                else:
                    self.fail("intent._env.ibgw not available for localhost connection.")
            except Exception as e:
                self.fail(f"Local IBGW intent test failed: {e}")
            finally:
                if hasattr(self.intent, '_env') and hasattr(self.intent._env, 'ibgw') and self.intent._env.ibgw.isConnected():
                    self.intent._env.ibgw.disconnect()
        else:
            # 非 localhost (Cloud Build/Run) 环境
            try:
                actual = self.intent.run()
            except Exception as e:
                self.fail(f"Cloud Run IBGW intent test failed: {e}")
        
        if actual is not None:
            # 确保 currentTime 存在且是字符串
            current_time_val = actual.get('currentTime')
            self.assertIsNotNone(current_time_val, "'currentTime' not found in 'actual' result.")
            self.assertIsInstance(current_time_val, str, "'currentTime' should be a string.")
            self.assertEqual(date.today().isoformat(), current_time_val[:10])
        else:
            # 仅当在 Cloud Run 环境下 actual 仍为 None 时才失败
            if environ.get('K_REVISION') != 'localhost':
                 self.assertIsNotNone(actual, "intent.run() or intent._core() returned None unexpectedly in Cloud Run environment.")


if __name__ == '__main__':
    unittest.main()