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

import ggml_deps
import ggml_release
import storage

ROOT = Path(__file__).resolve().parents[1]
API_ENV_KEYS = ('YUE2_API_KEY', 'YUE2_API_TIMEOUT_SECONDS', 'YUE2_MCP_PUBLIC_URL', 'YUE2_MCP_OUTPUT_DIR')


def api_environment(existing=None):
    """Keep configured API access across image updates; explicit host values win."""
    environment = os.environ.copy()
    previous = dict(item.split('=', 1) for item in (existing or {}).get('Config', {}).get('Env', []) if '=' in item)
    for key in API_ENV_KEYS:
        if key not in environment and key in previous:
            environment[key] = previous[key]
    return environment


def api_env_flags(environment):
    # Docker reads values from its environment. Never put keys in printed argv.
    return [value for key in API_ENV_KEYS if key in environment for value in ('--env', key)]


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


def local_dependency(key, dry=False):
    name = 'yue2-ggml:' + key[:20]
    if not dry and subprocess.run(['docker', 'image', 'inspect', name],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL).returncode == 0:
        return name
    return ''


def build_dependency(dry=False):
    dependency = ggml_release.plan()
    requested = setting('CUDA_ARCHITECTURES', 'auto')
    selected = setting('GGML_DEPS_IMAGE', '')
    arch = requested if dry else architectures()
    # A distribution artifact already covers the local GPU. Prefer reusing it
    # over recompiling a narrower library when the user left targeting on auto.
    if requested == 'auto' and not selected:
        available = {value.split('-')[0] for value in dependency['architectures'].split(';')}
        detected = {value.split('-')[0] for value in (arch or '').split(';') if value}
        if dry or not detected or detected <= available:
            selected = ('release-archive' if dependency.get('archive') else
                        dependency['image'] if dependency['image'] != 'ggml-deps'
                        else local_dependency(dependency['key'], dry))
            if selected:
                arch = dependency['architectures']
    if not arch or arch == 'auto':
        arch = dependency['architectures']
    if not selected:
        if arch == dependency['architectures'] and dependency.get('archive'):
            selected = 'release-archive'
        elif arch == dependency['architectures'] and dependency['image'] != 'ggml-deps':
            selected = dependency['image']
        else:
            selected = local_dependency(ggml_deps.fingerprint(architectures=arch), dry)
    return dependency, arch, selected


def active_jobs(container, port):
    """Do not replace a live server while it is computing or has queued work."""
    logs = subprocess.run(['docker', 'logs', container], capture_output=True,
                          encoding='utf-8', errors='replace', check=True)
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
                                          'cpu-check', 'web-check', 'web-build', 'verify-vendor', 'deps-build'))
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
        run([sys.executable, 'scripts/verify_ggml_source.py'], args.dry_run)
        run([sys.executable, 'scripts/verify_app_deps.py'], args.dry_run)
    elif args.command == 'deps-build':
        dependency = ggml_deps.plan()
        tag = 'yue2-ggml:' + dependency['key'][:20]
        run(['docker', 'build', '--platform', 'linux/amd64', '--progress=plain',
             '--target', 'ggml-deps', '--build-arg', 'CUDA_BASE=' + dependency['cuda_base'],
             '--build-arg', 'CUDA_ARCHITECTURES=' + dependency['architectures'],
             '--build-arg', 'BUILD_JOBS=' + setting('BUILD_JOBS', '4'), '-t', tag, '.'], args.dry_run)
        print(f'Dependency artifact: {tag}; input key: {dependency["key"]}')
    elif args.command in ('build', 'cpu-check'):
        command = ['docker', 'build', '--progress=plain', '--build-arg', 'SOURCE_REVISION=' + revision()]
        if args.command == 'build':
            dependency, arch, selected = build_dependency(args.dry_run)
            command += ['--build-arg', 'CUDA_ARCHITECTURES=' + arch,
                        '--platform', 'linux/amd64', '--build-arg', 'CUDA_BASE=' + dependency['cuda_base']]
            if selected == 'release-archive':
                context = ggml_release.prepare(dependency, dry=args.dry_run)
                command += ['--build-context', 'selected-ggml=' + str(context)]
            elif selected and selected != 'ggml-deps':
                command += ['--build-arg', 'GGML_DEPS_IMAGE=' + selected]
            command += ['--build-arg', 'BUILD_JOBS=' + setting('BUILD_JOBS', '4'), '-t', image]
        else:
            command += ['--target', 'cpu-checks', '-t', 'yue2:cpu-checks']
        run(command + ['.'], args.dry_run)
    elif args.command in ('web-check', 'web-build'):
        script = 'npm ci --no-audit --no-fund && npm run check && npm test && npm run lint'
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
        server_env = api_environment()
        if not server_env.get('YUE2_MCP_PUBLIC_URL'):
            server_env['YUE2_MCP_PUBLIC_URL'] = f'http://localhost:{port}'
        models = storage.MODELS
        adapters = storage.ADAPTERS
        output = storage.RESULTS / 'studio'
        for filename in ('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf'):
            if not (models / filename).is_file() and not args.dry_run:
                raise RuntimeError('Models missing in data/models/. Run task data:migrate for an old checkout, or task models to download.')
        if not args.dry_run:
            storage.require_migrated()
            adapters.mkdir(parents=True, exist_ok=True)
            output.mkdir(parents=True, exist_ok=True)
            image_info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]
            existing = subprocess.run(['docker', 'inspect', container], capture_output=True, text=True)
            if existing.returncode == 0:
                info = json.loads(existing.stdout)[0]
                server_env = api_environment(info)
                if not server_env.get('YUE2_MCP_PUBLIC_URL'):
                    server_env['YUE2_MCP_PUBLIC_URL'] = f'http://localhost:{port}'
                labels = info['Config'].get('Labels') or {}
                if labels.get('org.opencontainers.image.source') != 'https://github.com/hangry-labs/yue2':
                    raise RuntimeError('Container name belongs to another project; choose CONTAINER explicitly')
                bindings = info['HostConfig'].get('PortBindings', {}).get('8087/tcp') or []
                if info['State']['Running']:
                    active_jobs(container, int(bindings[0]['HostPort']) if bindings else port)
                binding = {'HostIp': setting('BIND_ADDRESS', '127.0.0.1'), 'HostPort': str(port)}
                mounted = {m['Destination']: os.path.normcase(m['Source']) for m in info.get('Mounts', [])}
                correct_mounts = all(mounted.get(target) == os.path.normcase(str(source))
                                     for target, source in (('/models', models), ('/adapters', adapters), ('/output', output)))
                requests = info['HostConfig'].get('DeviceRequests') or []
                selected = setting('GPU_DEVICE', 'all')
                correct_gpu = any((r.get('Count') == -1 if selected == 'all'
                                   else r.get('DeviceIDs') == selected.split(',')) for r in requests)
                configured = dict(item.split('=', 1) for item in info['Config'].get('Env', []) if '=' in item)
                correct_api = all(configured.get(key, default) == server_env.get(key, default)
                                  for key, default in (('YUE2_API_KEY', ''), ('YUE2_API_TIMEOUT_SECONDS', '600'),
                                                       ('YUE2_MCP_PUBLIC_URL', ''), ('YUE2_MCP_OUTPUT_DIR', '')))
                if (info['Image'] == image_info['Id'] and info['State']['Running']
                        and info['Config']['Cmd'] == image_info['Config']['Cmd']
                        and bindings == [binding] and correct_mounts and correct_gpu and correct_api):
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
             '--mount', f'type=bind,source={adapters},target=/adapters,readonly',
             '--mount', f'type=bind,source={output},target=/output', *api_env_flags(server_env), image], args.dry_run, env=server_env)
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
