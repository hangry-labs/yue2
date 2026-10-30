#!/usr/bin/env python3
"""Cross-platform development commands for the Docker-first Yue2 checkout."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def setting(name, default):
    return os.environ.get('YUE2_TASK_' + name, default)


def run(command, dry=False, **kwargs):
    print(subprocess.list2cmdline([str(value) for value in command]), flush=True)
    if dry:
        return None
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def revision():
    value = subprocess.run(['git', 'describe', '--always', '--dirty'], cwd=ROOT,
                           capture_output=True, text=True)
    return value.stdout.strip() if value.returncode == 0 else 'unknown'


def architectures():
    chosen = setting('CUDA_ARCHITECTURES', 'auto')
    if chosen != 'auto':
        return chosen
    if not shutil.which('nvidia-smi'):
        return None
    value = subprocess.run(['nvidia-smi', '--query-gpu=compute_cap', '--format=csv,noheader'],
                           capture_output=True, text=True)
    if value.returncode:
        return None
    caps = value.stdout.splitlines()
    device = setting('GPU_DEVICE', 'all')
    if device.isdigit():
        caps = [caps[int(device)]]
    result = []
    for cap in caps:
        cap = cap.strip()
        if re.fullmatch(r'\d+\.\d+', cap):
            result.append('120a-real' if cap == '12.0' else cap.replace('.', '') + '-real')
    return ';'.join(sorted(set(result))) or None


def active_jobs(container, port):
    """Do not replace a live server while it is computing or has queued work."""
    logs = subprocess.run(['docker', 'logs', container], capture_output=True, text=True, check=True)
    ids = dict.fromkeys(re.findall(r'\[Server\] (?:[^\n:]*? )?[Jj]ob ([0-9a-f]+):', logs.stdout + logs.stderr))
    for job in ids:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/job?id={job}', timeout=5) as response:
                if json.load(response)['status'] == 'running':
                    raise RuntimeError('A generation is active; finish or cancel it before task start')
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('doctor', 'build', 'start', 'stop', 'status', 'logs',
                                          'cpu-check', 'web-check', 'web-build', 'verify-vendor'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    image = setting('IMAGE', 'yue2:dev')
    container = setting('CONTAINER', 'yue2-dev')
    port = int(setting('PORT', '8087'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', container):
        raise ValueError('Invalid Docker container name')
    if args.command == 'doctor':
        print(f'Python {sys.version.split()[0]}; checkout {ROOT}')
        run(['docker', 'version', '--format', '{{.Server.Os}} {{.Server.Version}}'], args.dry_run)
        run(['docker', 'buildx', 'version'], args.dry_run)
        if shutil.which('nvidia-smi'):
            run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv'], args.dry_run)
        else:
            print('Host nvidia-smi unavailable; verify Docker GPU access separately.')
    elif args.command == 'verify-vendor':
        run([sys.executable, 'scripts/verify_vendor.py'], args.dry_run)
    elif args.command in ('build', 'cpu-check'):
        command = ['docker', 'build', '--progress=plain', '--build-arg', 'SOURCE_REVISION=' + revision()]
        if args.command == 'build':
            arch = setting('CUDA_ARCHITECTURES', 'auto') if args.dry_run else architectures()
            if arch and arch != 'auto':
                command += ['--build-arg', 'CUDA_ARCHITECTURES=' + arch]
            command += ['--build-arg', 'BUILD_JOBS=' + setting('BUILD_JOBS', '4'), '-t', image]
        else:
            command += ['--target', 'cpu-checks', '-t', 'yue2:cpu-checks']
        run(command + ['.'], args.dry_run)
    elif args.command in ('web-check', 'web-build'):
        script = 'npm ci --no-audit --no-fund && npm run check && npm run lint'
        if args.command == 'web-build':
            version = (ROOT / 'VERSION').read_text().strip() + ' (' + revision() + ')'
            script += ' && npm run build'
        else:
            version = ''
        command = ['docker', 'run', '--rm', '--mount', f'type=bind,source={ROOT},target=/workspace',
                   '--mount', 'type=volume,source=yue2_web_node_modules,target=/workspace/web/node_modules',
                   '--workdir', '/workspace/web', '--env', 'YUE2_VERSION=' + version,
                   'node:24-bookworm-slim', 'sh', '-c', script]
        run(command, args.dry_run)
    elif args.command == 'start':
        models = ROOT / 'models'
        for filename in ('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf'):
            if not (models / filename).is_file() and not args.dry_run:
                raise RuntimeError('Models missing. Run task models first.')
        if not args.dry_run:
            image_info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]
            existing = subprocess.run(['docker', 'inspect', container], capture_output=True, text=True)
            if existing.returncode == 0:
                info = json.loads(existing.stdout)[0]
                labels = info['Config'].get('Labels') or {}
                if labels.get('org.opencontainers.image.source') != 'https://github.com/hangry-labs/yue2':
                    raise RuntimeError('Container name belongs to another project; choose CONTAINER explicitly')
                bindings = info['HostConfig'].get('PortBindings', {}).get('8087/tcp') or []
                if info['State']['Running']:
                    active_jobs(container, int(bindings[0]['HostPort']) if bindings else port)
                binding = {'HostIp': setting('BIND_ADDRESS', '127.0.0.1'), 'HostPort': str(port)}
                mounted = {m['Destination']: os.path.normcase(m['Source']) for m in info.get('Mounts', [])}
                correct_mounts = all(mounted.get(target) == os.path.normcase(str(source))
                                     for target, source in (('/models', models), ('/adapters', ROOT / 'adapters')))
                requests = info['HostConfig'].get('DeviceRequests') or []
                selected = setting('GPU_DEVICE', 'all')
                correct_gpu = any((r.get('Count') == -1 if selected == 'all'
                                   else r.get('DeviceIDs') == selected.split(',')) for r in requests)
                if (info['Image'] == image_info['Id'] and info['State']['Running']
                        and info['Config']['Cmd'] == image_info['Config']['Cmd']
                        and bindings == [binding] and correct_mounts and correct_gpu):
                    print(f'Already running: http://localhost:{port}')
                    return 0
                run(['docker', 'stop', container])
                run(['docker', 'rm', container])
        gpu = setting('GPU_DEVICE', 'all')
        gpu = 'all' if gpu == 'all' else 'device=' + gpu
        run(['docker', 'run', '-d', '--name', container, '--gpus', gpu,
             '--label', 'io.hangrylabs.project=yue2',
             '-p', setting('BIND_ADDRESS', '127.0.0.1') + f':{port}:8087',
             '--mount', f'type=bind,source={models},target=/models,readonly',
             '--mount', f'type=bind,source={ROOT / "adapters"},target=/adapters,readonly', image], args.dry_run)
        print(f'UI: http://localhost:{port}')
    elif args.command == 'stop':
        if not args.dry_run:
            info = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
            labels = info['Config'].get('Labels') or {}
            if labels.get('org.opencontainers.image.source') != 'https://github.com/hangry-labs/yue2':
                raise RuntimeError('Refusing to stop a container owned by another project')
        run(['docker', 'stop', container], args.dry_run)
    elif args.command == 'logs':
        run(['docker', 'logs', '--follow', container], args.dry_run)
    elif args.command == 'status':
        run(['docker', 'inspect', '--format', '{{json .State}}', container], args.dry_run)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'yue2: {error}', file=sys.stderr)
        sys.exit(1)
