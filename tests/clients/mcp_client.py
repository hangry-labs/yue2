#!/usr/bin/env python3
"""Explicit GPU smoke check using the official MCP Python SDK v2.

Install the test-only dependency with `pip install 'mcp>=2,<3'`.
Read-only: python tests/clients/mcp_client.py --url http://localhost:8087 --mode auto
Generate: add --fixture request.json --output data/results/mcp-check/song.opus
The fixture contains only the public generate_song arguments (no guide token).
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
import urllib.request

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def check(args):
    headers = {}
    if os.environ.get('YUE2_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['YUE2_API_KEY']
    async with httpx2.AsyncClient(headers=headers) as http:
        transport = streamable_http_client(args.url.rstrip('/') + '/mcp', http_client=http)
        async with Client(transport, mode=args.mode) as client:
            tools = await client.list_tools()
            assert {t.name for t in tools.tools} == {'skill', 'generate_song', 'get_song', 'cancel_song'}
            resources = await client.list_resources()
            assert any(str(r.uri) == 'yue2://skills/songwriting' for r in resources.resources)
            resource = await client.read_resource('yue2://skills/songwriting')
            guide = await client.call_tool('skill', {})
            assert not guide.is_error
            data = guide.structured_content
            assert data['skill'] == resource.contents[0].text
            print(f'{args.mode}: official SDK discovery, tools, resource and skill passed', flush=True)
            if not args.fixture:
                return
            fixture = json.loads(args.fixture.read_text(encoding='utf-8'))
            fixture['guide_token'] = data['guide_token']
            result = await client.call_tool('generate_song', fixture)
            assert not result.is_error, result.content
            job = result.structured_content['job_id']
            deadline = time.monotonic() + 1200
            poll_after = result.structured_content.get('poll_after_seconds', 30)
            while time.monotonic() < deadline:
                await asyncio.sleep(poll_after)
                result = await client.call_tool('get_song', {'job_id': job})
                assert not result.is_error, result.content
                song = result.structured_content
                if song['status'] == 'complete':
                    assert song['ttl_seconds'] == 3600 and song['sample_rate'] == 48000 and song['channels'] == 2
                    # Capability download deliberately has no Bearer header.
                    with urllib.request.urlopen(song['url']) as download:
                        audio = download.read()
                    assert len(audio) == song['size_bytes'] and audio
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_bytes(audio)
                    args.output.with_suffix('.metadata.json').write_text(json.dumps(song, indent=2) + '\n', encoding='utf-8')
                    print(f'{args.mode}: real {song["duration_seconds"]:.2f}s {song["format"]} downloaded ({len(audio)} bytes)', flush=True)
                    return
                if song['status'] in ('failed', 'cancelled'):
                    raise RuntimeError(song)
                poll_after = song.get('poll_after_seconds', 30)
            await client.call_tool('cancel_song', {'job_id': job})
            raise TimeoutError('Song did not complete in the qualification deadline; cancelled its job')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8087')
    parser.add_argument('--mode', choices=('auto', 'legacy'), default='auto')
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if bool(args.fixture) != bool(args.output):
        parser.error('--fixture and --output must be supplied together')
    asyncio.run(check(args))
