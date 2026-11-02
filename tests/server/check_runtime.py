#!/usr/bin/env python3
"""Burst, queue, cancellation, disk streaming and restart tests without model weights."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def request(base, route, body=None, headers=None, method=None):
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode()
    req = Request(base + route, data=body, headers={'Content-Type': 'application/json', **(headers or {})}, method=method)
    try:
        with urlopen(req, timeout=35) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


def get(base, route):
    code, _, body = request(base, route)
    assert code == 200, (route, code, body)
    return json.loads(body)


def until(fn, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(.01)
    raise AssertionError('Timed out waiting for fixture state')


def start(binary, directory):
    process = subprocess.Popen([binary, directory], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base = process.stdout.readline().strip()
    if not base.startswith('http://'):
        raise AssertionError(process.communicate(timeout=5))
    until(lambda: get(base, '/health')['status'] == 'ok')
    return process, base


def stop(process, base):
    try:
        request(base, '/fixture/stop', {})
        _, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def run(binary):
    with tempfile.TemporaryDirectory(prefix='yue2-server-http-') as directory:
        process, base = start(binary, directory)
        try:
            first = json.loads(request(base, '/synth', {})[2])['id']
            until(lambda: get(base, '/job?id=' + first)['status'] == 'running')
            queued = [json.loads(request(base, '/synth', {})[2])['id'] for _ in range(11)]
            assert get(base, '/job?id=' + queued[-1])['queue_position'] == 11
            full = request(base, '/synth', {})
            assert full[0] == 429 and full[1]['Retry-After'] == '5'
            # The actual MCP transport returns a tool execution error, preserving
            # JSON-RPC framing and giving clients structured retry guidance.
            headers = {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-11-25'}
            def rpc(name, args):
                return request(base, '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                             'params': {'name': name, 'arguments': args}}, headers)
            guide = json.loads(rpc('skill', {})[2])['result']['structuredContent']['guide_token']
            refusal = rpc('generate_song', {'guide_token': guide, 'lyrics': '[Verse]\nA full song', 'direction': 'folk'})
            error = json.loads(refusal[2])['result']
            assert error['isError'] and error['structuredContent']['code'] == 'queue_full'
            assert error['structuredContent']['retry_after_seconds'] == 5 and refusal[1]['Retry-After'] == '5'
            for identity in queued:
                assert request(base, '/job?id=' + identity + '&cancel=1', {})[0] == 200
            assert get(base, '/system/queue')['queue']['pending'] == 1
            # Hold eight real synchronous handlers. Additional calls must refuse
            # quickly while control-plane endpoints remain responsive.
            with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
                waits = [pool.submit(request, base, '/v1/audio/' + ('music' if i % 2 else 'speech'), {}) for i in range(8)]
                until(lambda: get(base, '/status')['http']['synchronous_waiters'] == 8)
                burst = [pool.submit(request, base, '/v1/audio/music', {}) for _ in range(32)]
                latencies = []
                for _ in range(20):
                    started = time.monotonic()
                    state = get(base, '/health')
                    latencies.append(time.monotonic() - started)
                    assert state['queue']['active'] == 1 and state['http']['synchronous_waiters'] == 8
                assert all(f.result()[0] == 429 for f in burst)
                assert max(latencies) < 1.0, latencies
                request(base, '/job?id=' + first + '&cancel=1', {})
                until(lambda: get(base, '/job?id=' + first)['status'] == 'cancelled')
                request(base, '/fixture/release', {})
                completed = [f.result() for f in waits]
                # Accepted API calls retain their slot through file delivery;
                # never return retryable 429 after music has been generated.
                assert all(row[0] == 200 for row in completed)
            until(lambda: get(base, '/status')['queue']['pending'] == 0)
            request(base, '/fixture/hold', {})
            timed = request(base, '/v1/audio/music?short=1', {})
            assert timed[0] == 504
            until(lambda: get(base, '/status')['queue']['pending'] == 0)
            # Closing a synchronous connection cancels its own queued/active job.
            address = urlsplit(base)
            sock = socket.create_connection((address.hostname, address.port), timeout=5)
            sock.sendall(b'POST /v1/audio/music HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}')
            until(lambda: get(base, '/status')['queue']['pending'] == 1)
            sock.close()
            until(lambda: get(base, '/status')['queue']['pending'] == 0)
            request(base, '/fixture/release', {})
            saved = json.loads(request(base, '/synth', {})[2])['id']
            until(lambda: get(base, '/job?id=' + saved)['status'] == 'done')
            result = request(base, '/job?id=' + saved + '&result=1')
            expected = hashlib.sha256(b'R' * (4 * 1024 * 1024)).hexdigest()
            assert result[0] == 200 and hashlib.sha256(result[2]).hexdigest() == expected
            partial = request(base, '/job?id=' + saved + '&result=1', headers={'Range': 'bytes=100-199'})
            assert partial[0] == 206 and partial[2] == b'R' * 100
            head = request(base, '/job?id=' + saved + '&result=1', method='HEAD')
            assert head[0] == 200 and int(head[1]['Content-Length']) == 4 * 1024 * 1024 and not head[2]
            assert Path(directory, saved + '.bin').stat().st_size == 4 * 1024 * 1024
        finally:
            stop(process, base)
        process, base = start(binary, directory)
        try:
            restored = get(base, '/job?id=' + saved)
            assert restored['status'] == 'done' and restored['metrics']['fixture']
            result = request(base, '/job?id=' + saved + '&result=1')
            assert hashlib.sha256(result[2]).hexdigest() == expected
        finally:
            stop(process, base)
        print(json.dumps({'status': 'passed', 'burst_requests': 32, 'held_synchronous_requests': 8,
                          'health_probes': len(latencies), 'health_max_ms': round(max(latencies) * 1000, 2),
                          'persisted_bytes': 4 * 1024 * 1024, 'restart_sha256': expected}))


if __name__ == '__main__':
    run(sys.argv[1])
