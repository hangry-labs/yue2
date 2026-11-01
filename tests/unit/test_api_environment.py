import os
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from dev import api_environment, api_env_flags


class ApiEnvironmentTests(unittest.TestCase):
    def test_image_updates_preserve_access_settings_without_logging_keys(self):
        previous = {'Config': {'Env': ['YUE2_API_KEY=previous-secret', 'YUE2_API_TIMEOUT_SECONDS=900']}}
        with patch.dict(os.environ, {}, clear=True):
            environment = api_environment(previous)
        self.assertEqual(environment['YUE2_API_KEY'], 'previous-secret')
        self.assertEqual(environment['YUE2_API_TIMEOUT_SECONDS'], '900')
        flags = api_env_flags(environment)
        self.assertNotIn('previous-secret', ' '.join(flags))
        self.assertEqual(flags, ['--env', 'YUE2_API_KEY', '--env', 'YUE2_API_TIMEOUT_SECONDS'])

    def test_explicit_host_values_can_replace_or_clear_the_key(self):
        previous = {'Config': {'Env': ['YUE2_API_KEY=previous-secret']}}
        for value in ('new-secret', ''):
            with self.subTest(value=value), patch.dict(os.environ, {'YUE2_API_KEY': value}, clear=True):
                self.assertEqual(api_environment(previous)['YUE2_API_KEY'], value)
