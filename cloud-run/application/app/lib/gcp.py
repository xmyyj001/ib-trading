# ===================================================================
# == FINAL GOLDEN CODE: gcp.py
# == Implements lazy initialization for all GCP clients.
# ===================================================================

import json
import logging
from os import environ

from google.cloud import bigquery, firestore_v1 as firestore, logging as gcp_logging, secretmanager_v1 as secretmanager

# Set up Cloud Logging robustly
try:
    gcp_project_id = environ.get('PROJECT_ID')
    if not gcp_project_id:
        # This will work in most GCP environments like Cloud Run, Cloud Functions
        import google.auth
        _, gcp_project_id = google.auth.default()
    
    gcp_logging_client = gcp_logging.Client(project=gcp_project_id)
    handler = gcp_logging_client.get_default_handler()
    logger = logging.getLogger('cloudLogger')
except (ImportError, google.auth.exceptions.DefaultCredentialsError, Exception):
    # Fallback for local development or environments without default credentials
    handler = logging.StreamHandler()
    logger = logging.getLogger(__name__)

logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False


class GcpModule:
    """
    A module for interacting with Google Cloud Platform services.
    It uses lazy initialization for its clients to ensure they are
    created only when needed and with the correct project ID.
    """

    def __init__(self):
        self._project_id = environ.get('PROJECT_ID')
        if not self._project_id:
            try:
                import google.auth
                _, self._project_id = google.auth.default()
            except google.auth.exceptions.DefaultCredentialsError:
                logger.warning("PROJECT_ID not found in environment or default credentials.")
                self._project_id = None
        
        # Clients are initialized to None and will be created on first access.
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
        """
        Fetches secrets from Secret Manager.
        """
        secret = self.sm.access_secret_version(name=secret_name).payload.data.decode()
        try:
            return json.loads(secret)
        except json.decoder.JSONDecodeError:
            return secret

    def query_bigquery(self, query, query_parameters=None, job_config=None, return_type='DataFrame', **kwargs):
        """
        Queries data form BigQuery.
        """
        query_parameters = query_parameters or {}
        job_config = job_config or bigquery.job.QueryJobConfig()

        def _create_query_parameters(params):
            parameter_types = {
                list: bigquery.ArrayQueryParameter
            }
            data_types = {
                bool: 'BOOL',
                int: 'INT64',
                float: 'FLOAT64',
                str: 'STRING'
            }
            bq_params = []
            for k, v in params.items():
                ptype, dtype = type(v), type(v[0] if isinstance(v, list) else v)
                if dtype in data_types:
                    bq_params.append(
                        parameter_types.get(ptype, bigquery.ScalarQueryParameter)(k, data_types[dtype], v))
                else:
                    self._logging.warning(f'No BigQuery query parameter type for {v.__class__.__name__} available')
            return bq_params

        try:
            job_config.query_parameters = _create_query_parameters(query_parameters)
        except Exception as e:
            self._logging.error(e)
            raise Exception('Query parameter error') from e

        try:
            self._logging.debug(f'Querying BigQuery with parameters {job_config.query_parameters}...')
            job = self.bq.query(query, job_config=job_config)
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