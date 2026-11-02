"""Read-only System API checks against a running container.

Run with task test:api, or set YUE2_TEST_URL before unittest discovery.
"""
import json
import math
import os
import unittest
from urllib.request import urlopen


@unittest.skipUnless(os.environ.get('YUE2_TEST_URL'), 'Set YUE2_TEST_URL to a running YuE2 server')
class SystemApiTests(unittest.TestCase):
    def fetch(self, route):
        with urlopen(os.environ['YUE2_TEST_URL'].rstrip('/') + route, timeout=5) as response:
            self.assertIn('no-store', response.headers.get('Cache-Control', ''))
            self.assertIn('application/json', response.headers.get('Content-Type', ''))
            return json.load(response)

    def test_capabilities_are_explicit(self):
        props = self.fetch('/props')
        for name in ('transcribe', 'tokenize', 'vae'):
            self.assertIsInstance(props['capabilities'][name], bool)
        self.assertTrue(props['capabilities']['vae'])
        self.assertTrue(props['model'])
        self.assertTrue(props['vae'])
        self.assertEqual(props['defaults']['synth_batch_size'], 2)
        self.assertEqual(props['limits']['synth_batch_size_max'], 3)

    def test_queue_and_result_storage_are_reported_without_private_job_details(self):
        for route in ('/health', '/status', '/system/queue'):
            with self.subTest(route=route):
                data = self.fetch(route)
                self.assertEqual(data['status'], 'ok')
                queue = data['queue']
                self.assertEqual(queue['pending'], queue['active'] + queue['queued'])
                self.assertEqual(queue['available'], queue['limit'] - queue['pending'])
                self.assertIn(queue['active'], (0, 1))
                self.assertIsInstance(queue['accepting'], bool)
                self.assertGreaterEqual(queue['retry_after_seconds'], 1)
                self.assertNotIn('jobs', queue)
                self.assertEqual(data['results']['location'], 'volume')
                self.assertGreater(data['results']['ttl_seconds'], 0)
                self.assertGreater(data['results']['limit_bytes'], 0)
                self.assertLess(data['http']['synchronous_limit'], data['http']['workers'])

    def test_gpu_history_is_bounded_and_sensors_can_be_unavailable(self):
        data = self.fetch('/system/gpu')
        self.assertEqual(data['sampling'], 'on_request')
        self.assertGreaterEqual(data['sample_interval_seconds'], 1)
        self.assertIsInstance(data['message'], str)
        counts = {}
        for sample in data['history']:
            counts[sample['index']] = counts.get(sample['index'], 0) + 1
            self.assertLessEqual(counts[sample['index']], 600)
            self.assertGreater(sample['timestamp'], 0)
        for gpu in data['gpus']:
            self.assertTrue(gpu['name'])
            self.assertIsInstance(gpu['index'], int)
            self.assertIn(gpu['index'], counts)
            for key, value in gpu.items():
                if key.endswith(('_percent', '_mb', '_mhz', '_w', '_c')) and value is not None:
                    self.assertTrue(math.isfinite(value), key)
                    self.assertGreaterEqual(value, 0, key)
                    if key.endswith('_percent'):
                        self.assertLessEqual(value, 100, key)


if __name__ == '__main__':
    unittest.main()
