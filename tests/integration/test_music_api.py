"""Read-only/disallowed-request checks: these never enqueue GPU inference."""
import json
import os
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@unittest.skipUnless(os.environ.get('YUE2_TEST_URL'), 'Set YUE2_TEST_URL to a running server')
class MusicApiTests(unittest.TestCase):
    def call(self, path, body=None, status=200):
        headers = {'Content-Type': 'application/json'}
        if os.environ.get('YUE2_API_KEY'):
            headers['Authorization'] = 'Bearer ' + os.environ['YUE2_API_KEY']
        request = Request(os.environ['YUE2_TEST_URL'].rstrip('/') + path,
                          data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, status)
            return json.load(response)

    def test_model_discovery_identifies_music_and_serial_execution(self):
        model = self.call('/v1/models')['data'][0]
        self.assertEqual(model['id'], 'yue2')
        self.assertTrue(model['capabilities']['music_generation'])
        self.assertFalse(model['capabilities']['parallel_inference'])
        self.assertEqual(self.call('/v1/models/tts-1')['id'], 'yue2')

    def test_both_routes_reject_unsupported_streaming_and_conflicts(self):
        for path in ('/v1/audio/music', '/v1/audio/speech'):
            with self.subTest(path=path):
                result = self.call(path, {'input': 'words', 'stream_format': 'sse'}, status=400)
                self.assertEqual(result['error']['param'], 'stream_format')
                self.assertEqual(result['error']['type'], 'invalid_request_error')
                result = self.call(path, {'input': 'one', 'lyrics': 'two'}, status=400)
                self.assertEqual(result['error']['param'], 'input')
                result = self.call(path, {'input': 'words', 'steps': 0}, status=400)
                self.assertIn('steps', result['error']['message'])
                result = self.call(path, {'input': 'words', 'response_format': 'unknown'}, status=400)
                self.assertEqual(result['error']['param'], 'response_format')

    def test_missing_model_and_route_errors_have_openai_shape(self):
        result = self.call('/v1/models/not-a-model', status=404)
        self.assertEqual(result['error']['code'], 'model_not_found')
        result = self.call('/v1/not-a-route', status=404)
        self.assertEqual(result['error']['code'], 'not_found')

    def test_schema_covers_native_and_compatibility_routes(self):
        schema = self.call('/openapi.json')
        self.assertEqual(schema['openapi'], '3.1.0')
        for path in ('/v1/audio/music', '/v1/audio/speech', '/v1/models', '/synth', '/job', '/vae', '/props'):
            self.assertIn(path, schema['paths'])
