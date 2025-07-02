# ===================================================================
# == FINAL DEFINITIVE VERSION (GOLDEN CODE): gcp.py
# == Implements lazy initialization for all GCP clients.
# ===================================================================

import json
import logging
from os import environ

from google.cloud import bigquery, firestore_v1 as firestore, logging as gcp_logging, secretmanager_v1 as secretmanager

# set up Cloud Logging
# 关键修复：延迟 logging client 的初始化，直到它被真正需要
try:
    gcp_project_id = environ.get('PROJECT_ID')
    if not gcp_project_id:
        # 在非 Cloud Run/Build 环境中，尝试从默认配置获取
        try:
            import google.auth
            _, gcp_project_id = google.auth.default()
        except google.auth.exceptions.DefaultCredentialsError:
            gcp_project_id = None # 如果都找不到，就让它为空
    
    # 只有在能确定 project_id 时才使用 Cloud Logging，否则回退到标准输出
    if gcp_project_id:
        gcp_logging_client = gcp_logging.Client(project=gcp_project_id)
        handler = gcp_logging_client.get_default_handler()
        logger = logging.getLogger('cloudLogger')
    else:
        raise RuntimeError("Could not determine GCP Project ID for logging.")
except Exception:
    handler = logging.StreamHandler()
    logger = logging.getLogger(__name__)

logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False


class GcpModule:

    def __init__(self):
        # --- 关键修复：不再在类加载时创建实例，而是在构造函数中 ---
        self._project_id = environ.get('PROJECT_ID')
        if not self._project_id:
            try:
                import google.auth
                _, self._project_id = google.auth.default()
            except google.auth.exceptions.DefaultCredentialsError:
                logger.warning("PROJECT_ID not found in environment or default credentials.")
                self._project_id = None
        
        # 将客户端实例的创建延迟到属性被第一次访问时
        self.__bq = None
        self.__db = None
        self.__sm = None
        self._logging = logger

    @property
    def bq(self):
        if self.__bq is None:
            self._logging.info(f"Initializing BigQuery client for project '{self._project_id}'...")
            self.__bq = bigquery.Client(project=self._project_id)
        return self.__bq

    @property
    def db(self):
        if self.__db is None:
            self._logging.info(f"Initializing Firestore client for project '{self._project_id}'...")
            self.__db = firestore.Client(project=self._project_id)
        return self.__db

    @property
    def sm(self):
        if self.__sm is None:
            self._logging.info("Initializing Secret Manager client...")
            self.__sm = secretmanager.SecretManagerServiceClient()
        return self.__sm

    @property
    def logging(self):
        return self._logging

    @classmethod
    def get_logger(cls):
        return logger

    def get_secret(self, secret_name):
        secret = self.sm.access_secret_version(name=secret_name).payload.data.decode()
        try:
            return json.loads(secret)
        except json.decoder.JSONDecodeError:
            return secret

    def query_bigquery(self, query, query_parameters=None, job_config=None, return_type='DataFrame', **kwargs):
        """
        Queries data form BigQuery.

        :param query: query string (str)
        :param query_parameters: parameters for parametrised query (dict)
        :param job_config: query job configuration (bigquery.job.QueryJobConfig)
        :param return_type: type of the return object (e.g. 'DataFrame') (str)
        :param kwargs: additional arguments for the fetch method
        :return: data (type depending on return_type, defaults to list of tuple)
        """
        query_parameters = query_parameters or {}
        job_config = job_config or bigquery.job.QueryJobConfig()

        def _create_query_parameters(params):
            parameter_types = {
                # dict: bigquery.StructQueryParameter,
                list: bigquery.ArrayQueryParameter
            }
            data_types = {
                bool: 'BOOL',
                int: 'INT64',
                float: 'FLOAT64',
                str: 'STRING'
            }

            query_parameters = []
            for k, v in params.items():
                ptype, dtype = type(v), type(v[0] if isinstance(v, list) else v)
                if dtype in data_types.keys():
                    query_parameters.append(
                        parameter_types.get(ptype, bigquery.ScalarQueryParameter)(k, data_types[dtype], v))
                else:
                    self._logging.warning(f'No BigQuery query parameter type for {v.__class__.__name__} available')

            return query_parameters

        try:
            job_config.query_parameters = _create_query_parameters(query_parameters)
        except Exception as e:
            self._logging.error(e)
            raise Exception('Query parameter error')

        try:
            self._logging.debug(f'Querying BigQuery with parameters {job_config.query_parameters}...')
            job = self.bq.query(query, job_config=job_config)  # 需要确认的部分 job = self._bq.query(query, job_config=job_config) 
            
        except Exception as e:
            self._logging.error(f'BigQuery error: {e}')
            raise e

        try:
            if return_type.lower() == 'dataframe':
                to_dataframe_kwargs = {k: v for k, v in kwargs.items() if k in bigquery.QueryJob.to_dataframe.__code__.co_varnames}
                df = job.to_dataframe(**to_dataframe_kwargs)
                if 'index_col' in kwargs:
                    df.set_index(kwargs['index_col'], inplace=True)
                return df
            elif return_type.lower() == 'list':
                return [{k: v for k, v in row.items()} for row in job.result()]
            else:
                raise NotImplementedError(f'Return type "{return_type}" is not implemented')
        except NotImplementedError as e:
            raise e
        except Exception as e:
            self._logging.error(f'Error reading BigQuery result: {e}')
            raise e
