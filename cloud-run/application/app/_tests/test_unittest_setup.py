# --- START OF CORRECTED _tests/test_unittest_setup.py ---

from unittest.mock import patch

with patch('google.cloud.bigquery.Client'):
    with patch('google.cloud.firestore_v1.Client'):
        with patch('google.cloud.logging.Client'):
            with patch('google.cloud.secretmanager_v1.SecretManagerServiceClient'):
                from lib.environment import Environment

# [THE FIX IS HERE]
# We now provide a mock ibc_config dictionary when instantiating Environment.
# This prevents the TypeError in the IBGW constructor during test discovery.
MOCK_IBC_CONFIG = {
    'twsPath': 'mock/path',
    'twsVersion': '1030',
    'ibcPath': 'mock/ibc',
    'ibcIni': 'mock/ini'
    # No 'script' key is needed; the IBGW __init__ will add it.
}

with patch('lib.environment.environ', {'PROJECT_ID': 'project-id'}):
    with patch('lib.environment.GcpModule.get_secret', return_value={'userid': 'userid', 'password': 'password'}):
        # Pass the mock config here
        env = Environment(ibc_config=MOCK_IBC_CONFIG)

# --- END OF CORRECTED _tests/test_unittest_setup.py ---