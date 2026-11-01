"""Isolated Docker worker, sampled device telemetry and HTTP transports."""
from contextlib import contextmanager
import csv
from email import policy
from email.parser import BytesParser
import io
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://github.com/hangry-labs/yue2'


def command(args, **kwargs):
    return subprocess.check_output(args, text=True, encoding='utf-8', errors='replace', **kwargs).strip()


def http_json(base, path, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(base.rstrip('/') + path, data=data,
                         headers={'Content-Type': 'application/json'}), timeout=timeout) as response:
        return json.load(response)


def multipart(fields, files):
    boundary = 'yue2-benchmark-' + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    for key, (filename, data) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
                     'Content-Type: audio/wav\r\n\r\n'.encode() + data + b'\r\n')
    return b''.join(parts) + f'--{boundary}--\r\n'.encode(), f'multipart/form-data; boundary={boundary}'


def track_parts(content_type, body):
    message = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + content_type.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
    audio, replay, latent = [], [], []
    for part in message.iter_parts():
        kind = part.get_content_type()
        data = part.get_payload(decode=True)
        if kind == 'audio/wav':
            audio.append(data)
        elif kind == 'application/json':
            replay.append(json.loads(data))
        elif kind == 'application/octet-stream':
            latent.append(data)
    if len(audio) != 1 or len(replay) != 1 or not audio[0]:
        raise ValueError('Expected exactly one WAV track and replay request')
    return audio[0], replay[0], latent[0] if latent else b''


def synth(base, payload, timeout=180):
    started = time.perf_counter()
    job = http_json(base, '/synth', payload)['id']
    try:
        while time.perf_counter() - started < timeout:
            status = http_json(base, '/job?id=' + job)
            if status['status'] == 'done':
                break
            if status['status'] in ('failed', 'cancelled'):
                raise RuntimeError(f'Generation {job}: {status["status"]}')
            time.sleep(.02)
        else:
            raise TimeoutError(f'Generation {job} timed out')
        with urlopen(base + '/job?id=' + job + '&result=1', timeout=30) as response:
            audio, replay, latent = track_parts(response.headers['Content-Type'], response.read())
        return {'job_id': job, 'client_seconds': time.perf_counter() - started,
                'server': status.get('metrics', {})}, audio, replay, latent
    except BaseException:
        try:
            http_json(base, '/job?id=' + job + '&cancel=1', {})
        except (OSError, ValueError):
            pass
        raise


def asr_inventory(base):
    if not base.startswith(('http://', 'https://')):
        raise ValueError('Set YUE2_ASR_URL, ASR_URL in Task, or --asr-url to the remote judge')
    health = http_json(base, '/health/ready')
    if health.get('ready') is False or health.get('status') in ('error', 'unavailable'):
        raise RuntimeError('ASR judge is not ready')
    models = http_json(base, '/v1/models')['data']
    if not models:
        raise ValueError('ASR judge has no active model')
    return {'model': models[0]['id'], 'languages': http_json(base, '/v1/audio/supported_languages')['languages'],
            'health': health, 'context_prompt': False}


def transcribe(base, model, audio, language):
    # Deliberately never send expected lyrics as a prompt to the judge.
    body, content_type = multipart({'model': model, 'language': language,
                                    'temperature': '0', 'response_format': 'verbose_json'},
                                   {'file': ('song.wav', audio)})
    started = time.perf_counter()
    with urlopen(Request(base.rstrip('/') + '/v1/audio/transcriptions', data=body,
                         headers={'Content-Type': content_type}), timeout=180) as response:
        result = json.load(response)
    if not isinstance(result.get('text'), str):
        raise ValueError('ASR response has no transcript')
    return result, time.perf_counter() - started


def gpu_info(gpu):
    fields = 'index,uuid,name,driver_version,memory.total,memory.used,utilization.gpu'
    row = next(csv.reader(io.StringIO(command(['nvidia-smi', '--id=' + gpu,
                                              '--query-gpu=' + fields, '--format=csv,noheader,nounits']))))
    return dict(zip(fields.split(','), (value.strip() for value in row)))


def gpu_workers(exclude=()):
    ids = command(['docker', 'ps', '-q']).split()
    if not ids:
        return []
    return [item['Name'].lstrip('/') for item in json.loads(command(['docker', 'inspect', *ids]))
            if item['HostConfig'].get('DeviceRequests') and item['Name'].lstrip('/') not in exclude]


class GpuSampler:
    """Persistent nvidia-smi sampling, not one slow subprocess per observation."""
    def __init__(self, gpu, interval=.1):
        self.gpu, self.interval = gpu, interval
        self.samples = []
        self.lock = threading.Lock()
        self.process = None

    def __enter__(self):
        self.process = subprocess.Popen(['nvidia-smi', '--id=' + self.gpu,
            '--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw',
            '--format=csv,noheader,nounits', '--loop-ms=' + str(round(self.interval * 1000))],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        return self

    def _read(self):
        for line in self.process.stdout:
            fields = next(csv.reader([line]))
            if len(fields) != 4:
                continue
            values = []
            for value in fields:
                try:
                    values.append(float(value))
                except ValueError:
                    values.append(None)
            with self.lock:
                self.samples.append({'time': time.perf_counter(), 'used_mib': values[0],
                    'utilization_percent': values[1], 'temperature_c': values[2], 'power_w': values[3]})

    def window(self, start, end):
        with self.lock:
            values = [dict(row) for row in self.samples if start <= row['time'] <= end]
        if not values or any(row['used_mib'] is None for row in values):
            raise RuntimeError('GPU memory samples unavailable for measured interval')
        memory = [row['used_mib'] for row in values]
        utilization = [row['utilization_percent'] for row in values if row['utilization_percent'] is not None]
        return {'samples': len(values), 'peak_mib': max(memory),
                'median_mib': statistics.median(memory), 'last_mib': memory[-1],
                'mean_utilization_percent': statistics.mean(utilization) if utilization else None}

    def __exit__(self, *_):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.thread.join(timeout=5)
        self.process.stdout.close()
        self.process.stderr.close()


def container_info(name):
    result = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def require_idle_dev(info):
    if (info['Config'].get('Labels') or {}).get('org.opencontainers.image.source') != SOURCE:
        raise ValueError('Refusing to pause a container from another project')
    bindings = info['HostConfig'].get('PortBindings', {}).get('8087/tcp') or []
    if not bindings:
        raise ValueError('Cannot inspect active jobs: development server has no host port')
    base = 'http://127.0.0.1:' + bindings[0]['HostPort']
    logs = command(['docker', 'logs', info['Id']], stderr=subprocess.STDOUT)
    ids = set(re.findall(r'\[Server\] (?:[^\n:]*? )?[Jj]ob ([0-9a-f]+):', logs))
    for identity in ids:
        try:
            if http_json(base, '/job?id=' + identity)['status'] == 'running':
                raise RuntimeError('A development generation is active; finish it before benchmarking')
        except HTTPError as error:
            if error.code != 404:
                raise


@contextmanager
def worker(image, gpu, dev_container, pause_dev, run_id, shared=False):
    """Only the owned idle dev server may be stopped; restore its exact container."""
    paused = identity = None
    info = container_info(dev_container)
    others = gpu_workers(exclude=(dev_container,))
    if others and not shared:
        raise RuntimeError('Other GPU containers are running: ' + ', '.join(others))
    try:
        if info and info['State']['Running']:
            if not pause_dev:
                raise RuntimeError('Stop the development server or select --pause-dev')
            require_idle_dev(info)
            print('Pausing idle development server; its exact container will be restarted.', flush=True)
            command(['docker', 'stop', info['Id']])
            paused = info['Id']
        idle = gpu_info(gpu)
        if float(idle['utilization.gpu']) > 15 and not shared:
            raise RuntimeError('GPU is busy before benchmark startup; finish other GPU work first')
        startup = time.perf_counter()
        name = 'yue2-bench-' + uuid.uuid4().hex[:12]
        identity = command(['docker', 'run', '-d', '--pull=never', '--name', name,
            '--gpus', 'device=' + gpu, '--label', 'io.hangrylabs.project=yue2',
            '--label', 'io.hangrylabs.benchmark=' + run_id, '-p', '127.0.0.1::8087',
            '--mount', f'type=bind,source={ROOT / "data/models"},target=/models,readonly', image,
            '--host', '0.0.0.0', '--port', '8087', '--model', '/models/YuE2-3B-Q8_0.gguf',
            '--vae', '/models/YuE2-Vae-F32.gguf', '--keep-loaded', '--device', 'CUDA0',
            '--max-seq', '24576', '--max-batch', '1', '--vae-core', '512', '--vae-halo', '16'])
        port = container_info(identity)['NetworkSettings']['Ports']['8087/tcp'][0]['HostPort']
        base = 'http://127.0.0.1:' + port
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if http_json(base, '/health', timeout=2).get('status') == 'ok':
                    break
            except (OSError, URLError):
                pass
            if not container_info(identity)['State']['Running']:
                raise RuntimeError('Benchmark worker exited: ' + command(['docker', 'logs', identity], stderr=subprocess.STDOUT))
            time.sleep(.1)
        else:
            raise TimeoutError('Benchmark worker did not become ready')
        yield {'id': identity, 'url': base, 'props': http_json(base, '/props'),
               'idle_gpu': idle, 'startup_seconds': time.perf_counter() - startup,
               'shared_gpu_containers': others}
    finally:
        try:
            if identity:
                current = container_info(identity)
                if current and (current['Config'].get('Labels') or {}).get('io.hangrylabs.benchmark') == run_id:
                    command(['docker', 'stop', '--time', '20', identity])
                    command(['docker', 'rm', identity])
        finally:
            if paused:
                command(['docker', 'start', paused])
