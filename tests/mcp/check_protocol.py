#!/usr/bin/env python3
"""Model-free checks against the same native MCP transport used by yue-server."""
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


def main(binary):
    process = subprocess.Popen([binary], stdout=subprocess.PIPE, text=True)
    try:
        base = process.stdout.readline().strip()
        assert base.startswith('http://127.0.0.1:'), base

        def send(message=None, path='/mcp', method='POST', headers=None, expected=200):
            values = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                      'Authorization': 'Bearer fixture-key', 'MCP-Protocol-Version': '2025-11-25'}
            values.update(headers or {})
            req = urllib.request.Request(base + path, data=json.dumps(message).encode() if message is not None else None,
                                         headers=values, method=method)
            try:
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                body = response.read()
                assert response.status == expected, (response.status, expected, body)
                return body, response.headers

        def rpc(method, params=None, modern=False, expected=200, headers=None):
            params = dict(params or {})
            values = dict(headers or {})
            if modern:
                params['_meta'] = {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                                   'io.modelcontextprotocol/clientCapabilities': {}}
                values.update({'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': method})
                if method in ('tools/call', 'resources/read'):
                    values['Mcp-Name'] = params.get('name', params.get('uri'))
            raw, _ = send({'jsonrpc': '2.0', 'id': 17, 'method': method, 'params': params},
                          headers=values, expected=expected)
            result = json.loads(raw)
            assert result['id'] == (None if expected == 403 else 17)
            return result

        def call(name, args=None, modern=False):
            return rpc('tools/call', {'name': name, 'arguments': args or {}}, modern)['result']

        init = rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                  'clientInfo': {'name': 'fixture', 'version': '1'}})['result']
        assert init['protocolVersion'] == '2025-11-25'
        assert 'skill' in init['instructions']
        send({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, expected=202)
        send(method='GET', expected=405)
        send(method='DELETE', expected=405)
        send({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, headers={'Authorization': ''}, expected=401)
        rpc('ping', headers={'Origin': 'https://evil.example'}, expected=403)
        rpc('ping', headers={'Host': 'evil.example'}, expected=403)
        send([], expected=400)
        send({'jsonrpc': '2.0', 'id': None, 'method': 'ping'}, expected=400)
        send({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, headers={'Accept': 'text/html'}, expected=406)
        send({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, headers={'Content-Type': 'text/plain'}, expected=415)

        for modern in (False, True):
            if modern:
                discovery = rpc('server/discover', modern=True)['result']
                assert '2026-07-28' in discovery['supportedVersions']
            listing = rpc('tools/list', modern=modern)['result']
            assert {t['name'] for t in listing['tools']} == {
                'skill', 'generate_song', 'get_song', 'cancel_song'}
            assert all('skill' in t['description'].lower() and 'first' in t['description'].lower() for t in listing['tools'])
            generate = next(t for t in listing['tools'] if t['name'] == 'generate_song')
            assert generate['inputSchema']['properties']['duration_seconds']['default'] == 150
            resource = rpc('resources/read', {'uri': 'yue2://skills/songwriting'}, modern)['result']
            skill, _ = send(path='/skills/songwriting/SKILL.md', method='GET', headers={'Authorization': ''})
            assert resource['contents'][0]['text'] == skill.decode()
            guide = call('skill', modern=modern)['structuredContent']
            assert guide['skill'] == skill.decode() and guide['skill_version'] == '5'
            assert guide['skill_loaded'] is True and 'retrieval is complete' in guide['next_step']
            arguments = {'lyrics': '[Verse]\nA little light', 'direction': 'English piano', 'duration_seconds': 30}
            assert call('generate_song', arguments, modern)['isError']
            arguments['guide_token'] = guide['guide_token']
            for field in ('steps', 'seed', 'model', 'adapters', 'cfg_scale', 'semantic_tokens', 'settings', 'speed', 'cot'):
                assert call('generate_song', {**arguments, field: 1}, modern)['isError'], field
            for field, value in [('duration_seconds', 0), ('duration_seconds', 361), ('format', 'mp3'),
                                 ('tempo_bpm', 29), ('tempo_bpm', 301), ('tempo_bpm', 90.5),
                                 ('lyrics', None), ('lyrics', 'a\0b'), ('direction', ''), ('guide_token', 'unknown')]:
                assert call('generate_song', {**arguments, field: value}, modern)['isError'], field
            assert call('skill', {'settings': {}}, modern)['isError']
            queued = call('generate_song', arguments, modern)['structuredContent']
            complete = call('get_song', {'job_id': queued['job_id']}, modern)['structuredContent']
            assert complete['ttl_seconds'] == 3600 and complete['format'] == 'opus'
            assert complete['sample_rate'] == 48000 and complete['channels'] == 2
            from urllib.parse import urlsplit
            path = urlsplit(complete['url']).path
            body, headers = send(path=path, method='GET', headers={'Authorization': ''})
            assert body == b'sample-audio-bytes-0123456789' and headers['Cache-Control'] == 'no-store'
            head, headers = send(path=path, method='HEAD', headers={'Authorization': ''})
            assert head == b'' and int(headers['Content-Length']) == len(body)
            part, _ = send(path=path, method='GET', headers={'Range': 'bytes=0-5', 'Authorization': ''}, expected=206)
            assert part == body[:6]
            send(path=path, method='GET', headers={'Range': 'bytes=99999-', 'Authorization': ''}, expected=416)
            send(path=path.replace('.opus', '.flac'), method='GET', expected=404)
            assert call('cancel_song', {'job_id': queued['job_id']}, modern)['structuredContent']['status'] == 'complete'
            assert call('get_song', {'job_id': '../invalid'}, modern)['isError']
            assert call('get_song', {'job_id': '0' * 64}, modern)['isError']
        malformed = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list',
                     'params': {'_meta': {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                                          'io.modelcontextprotocol/clientCapabilities': {}}}}
        send(malformed, headers={'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'wrong'}, expected=400)
        print('MCP transport, restricted tools, guide-first workflow, expiry/restart and HTTP downloads: passed')
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == '__main__':
    main(str(Path(sys.argv[1]).resolve()))
