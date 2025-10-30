import unittest
from unittest.mock import MagicMock, patch
from test_support import install_google_cloud_stub

install_google_cloud_stub()

from google.cloud.bigquery import ArrayQueryParameter, ScalarQueryParameter

with patch('lib.gcp.bigquery'):
    with patch('lib.gcp.firestore'):
        with patch('lib.gcp.secretmanager'):
            from lib.gcp import GcpModule


class TestGcpModule(unittest.TestCase):

    def setUp(self, *_):
        self.test_obj = GcpModule()

    def test_get_secret(self):
        with patch.object(self.test_obj, '_GcpModule__sm', access_secret_version=MagicMock(return_value=MagicMock(payload=MagicMock(data=MagicMock(decode=MagicMock(return_value='{"key":"secret-value"}')))))) as p:
            actual = self.test_obj.get_secret('secret-name')
            self.assertDictEqual({'key': 'secret-value'}, actual)
            try:
                p.access_secret_version.assert_called_once_with(name='secret-name')
            except AssertionError:
                self.fail()

        with patch.object(self.test_obj, '_GcpModule__sm', access_secret_version=MagicMock(return_value=MagicMock(payload=MagicMock(data=MagicMock(decode=MagicMock(return_value='secret-value')))))) as p:
            actual = self.test_obj.get_secret('secret-name')
            self.assertEqual('secret-value', actual)

    @patch('lib.gcp.bigquery.job.QueryJobConfig', config='something', query_parameters=[])
    def test_query_bigquery(self, query_job_config):
        func = self.test_obj.query_bigquery
        data = [[1, 2, 3], [4, 5, 6]]

        fake_rows = [MagicMock(items=MagicMock(return_value=[(f'col{i + 1}', v) for i, v in enumerate(row)])) for row in data]
        fake_job = MagicMock()
        fake_job.result.return_value = fake_rows
        fake_bq = MagicMock(query=MagicMock(return_value=fake_job))
        self.test_obj._GcpModule__bq = fake_bq

        actual = func('query_str', job_config=query_job_config, return_type='list')
        expected = [{'col1': 1, 'col2': 2, 'col3': 3}, {'col1': 4, 'col2': 5, 'col3': 6}]
        self.assertEqual(expected, actual)
        try:
            fake_bq.query.assert_called_with('query_str', job_config=query_job_config)
        except AssertionError as e:
            self.fail(e)

        func('query_str', query_parameters={'str': 'str', 'int': 1, 'list': ['str1', 'str2'], 'none': None}, job_config=query_job_config, return_type='list')
        expected = [ScalarQueryParameter('str', 'STRING', 'str'), ScalarQueryParameter('int', 'INT64', 1), ArrayQueryParameter('list', 'STRING', ['str1', 'str2'])]
        self.assertListEqual(expected, query_job_config.query_parameters)
        try:
            fake_bq.query.assert_called_with('query_str', job_config=query_job_config)
        except AssertionError as e:
            self.fail(e)

        func('query_str', job_config=query_job_config, return_type='list')
        try:
            fake_bq.query.assert_called_with('query_str', job_config=query_job_config)
        except AssertionError as e:
            self.fail(e)

        fake_df = MagicMock()
        fake_job.to_dataframe.return_value = fake_df
        actual_df = func('query_str', job_config=query_job_config, return_type='DataFrame')
        self.assertIs(fake_df, actual_df)
        fake_job.to_dataframe.assert_called_once()
        fake_job.to_dataframe.reset_mock()

        fake_df_indexed = MagicMock()
        fake_job.to_dataframe.return_value = fake_df_indexed
        actual_df_indexed = func('query_str', job_config=query_job_config, return_type='DataFrame', index_col='col1')
        self.assertIs(fake_df_indexed, actual_df_indexed)
        fake_df_indexed.set_index.assert_called_once_with('col1', inplace=True)

        self.assertRaises(NotImplementedError, func, 'query_str', {}, query_job_config, 'NotImplemented')

        fake_job.to_dataframe.side_effect = Exception
        self.assertRaises(Exception, func)
        fake_job.to_dataframe.side_effect = None

        fake_bq.query.side_effect = Exception
        self.assertRaises(Exception, func)
        fake_bq.query.side_effect = None


if __name__ == '__main__':
    unittest.main()
