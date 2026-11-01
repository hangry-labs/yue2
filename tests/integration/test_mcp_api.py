"""Read-only MCP checks. These never enqueue music generation."""
import json
import os
import unittest
from urllib.request import Request, urlopen


@unittest.skipUnless(os.environ.get('YUE2_TEST_URL'), 'Set YUE2_TEST_URL to a running server')
class McpApiTests(unittest.TestCase):
    def rpc(self, method, params=None):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': method}
        if os.environ.get('YUE2_API_KEY'):
            headers['Authorization'] = 'Bearer ' + os.environ['YUE2_API_KEY']
        params = dict(params or {})
        params['_meta'] = {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                           'io.modelcontextprotocol/clientCapabilities': {}}
        if method == 'tools/call':
            headers['Mcp-Name'] = params['name']
        data = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
        request = Request(os.environ['YUE2_TEST_URL'].rstrip('/') + '/mcp', data=data, headers=headers)
        with urlopen(request, timeout=5) as response:
            result = json.load(response)
        self.assertNotIn('error', result)
        return result['result']

    def test_discovery_and_catalog_only_expose_music_workflow(self):
        discovery = self.rpc('server/discover')
        self.assertIn('skill', discovery['instructions'])
        self.assertEqual({t['name'] for t in self.rpc('tools/list')['tools']},
                         {'skill', 'generate_song', 'get_song', 'cancel_song'})

    def test_generation_without_guide_is_rejected_before_queueing(self):
        result = self.rpc('tools/call', {'name': 'generate_song', 'arguments': {'lyrics': 'words', 'direction': 'piano'}})
        self.assertTrue(result['isError'])

    def test_skill_is_served_as_text(self):
        url = os.environ['YUE2_TEST_URL'].rstrip('/') + '/skills/songwriting/SKILL.md'
        with urlopen(url, timeout=5) as response:
            self.assertIn('text/markdown', response.headers['Content-Type'])
            self.assertIn('name: yue2-music', response.read().decode())
