#!/usr/bin/env python3
"""Identify, verify and select the reusable Linux CUDA GGML artifact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'docker/ggml-deps.json'
MARKER = '# Application stages: dependency fingerprint ends here.'


def config():
    return json.loads(CONFIG.read_text())


def fingerprint(root=ROOT, architectures=None, cuda_base=None):
    settings = json.loads((root / 'docker/ggml-deps.json').read_text())
    digest = hashlib.sha256()
    inputs = {
        'schema': settings['schema'], 'platform': 'linux/amd64',
        'cuda_base': cuda_base or settings['cuda_base'],
        'architectures': architectures or settings['architectures'],
    }
    digest.update(json.dumps(inputs, sort_keys=True).encode())
    # Only dependency stages are relevant. App/UI/version edits must not change
    # the key. The source lock pins exact archive bytes verified by CMake.
    dockerfile = (root / 'Dockerfile').read_text().split(MARKER)
    if len(dockerfile) != 2:
        raise ValueError('Dockerfile dependency boundary is missing or duplicated')
    digest.update(dockerfile[0].encode())
    files = [root / 'scripts/ggml_deps.py', root / 'scripts/check_no_weights.py',
             root / 'cmake/ggml-abi.cmake', root / 'cmake/ggml-source.cmake', root / 'cmake/ggml-patches.cmake',
             root / 'docker/ggml-source.json']
    for directory in ('cmake/ggml-deps', 'cmake/ggml-patches'):
        files.extend(p for p in (root / directory).rglob('*') if p.is_file())
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        # Normalize our configuration for Linux/Windows checkout parity.
        data = path.read_bytes().replace(b'\r\n', b'\n')
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def immutable_image(value):
    return bool(re.fullmatch(r'[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}', value or ''))


def plan(settings=None):
    settings = settings or config()
    key = fingerprint(architectures=settings['architectures'], cuda_base=settings['cuda_base'])
    image = settings.get('image')
    if image and (not immutable_image(image) or settings.get('input_key') != key):
        raise ValueError('GGML dependency lock is stale or is not digest-pinned. '
                         'Rebuild and pin it, or clear image/input_key to build from source.')
    return {'key': key, 'image': image or 'ggml-deps',
            'architectures': settings['architectures'], 'cuda_base': settings['cuda_base']}


def toolchain():
    return {name: subprocess.check_output(command, text=True).strip() for name, command in (
        ('cxx', ['c++', '-dumpfullversion', '-dumpversion']),
        ('cuda', ['nvcc', '--version']),
    )}


def artifact_hashes(prefix):
    return {p.relative_to(prefix).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(prefix.rglob('*')) if p.is_file() and p.name != 'yue2-ggml.json'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'record', 'verify', 'pin'))
    parser.add_argument('--architectures')
    parser.add_argument('--cuda-base')
    parser.add_argument('--prefix', type=Path, default=Path('/opt/ggml'))
    parser.add_argument('--image')
    args = parser.parse_args()
    if args.command == 'plan':
        result = plan()
        print(json.dumps(result, indent=2))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                for key, value in result.items():
                    stream.write(f'{key}={value}\n')
        return
    key = fingerprint(architectures=args.architectures, cuda_base=args.cuda_base)
    metadata_path = args.prefix / 'yue2-ggml.json'
    if args.command == 'record':
        metadata = {'schema': 1, 'input_key': key, 'toolchain': toolchain(),
                    'ggml_commit': json.loads((ROOT / 'docker/ggml-source.json').read_text())['commit'],
                    'ggml_source': json.loads((ROOT / 'docker/ggml-source.json').read_text()),
                    'architectures': args.architectures or config()['architectures'],
                    'cuda_base': args.cuda_base or config()['cuda_base'],
                    'files': artifact_hashes(args.prefix)}
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        print(f'Recorded GGML artifact {key}')
    elif args.command == 'verify':
        metadata = json.loads(metadata_path.read_text())
        if metadata['input_key'] != key:
            raise ValueError('GGML artifact source/options mismatch; rebuild the dependency')
        if metadata['toolchain'] != toolchain():
            raise ValueError('GGML artifact compiler/CUDA mismatch; rebuild in this toolchain')
        if metadata['files'] != artifact_hashes(args.prefix):
            raise ValueError('GGML artifact files differ from their recorded hashes')
        print(f'PASS: prebuilt GGML source, options, toolchain and files match {key}')
    else:
        if not immutable_image(args.image):
            raise ValueError('--image must be a registry image pinned with @sha256:...')
        # Fetch only the small metadata file. Do not run code from the artifact.
        container = subprocess.check_output(['docker', 'create', args.image, '/unused'], text=True).strip()
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'metadata.json'
                subprocess.run(['docker', 'cp', f'{container}:/opt/ggml/yue2-ggml.json', str(target)], check=True)
                metadata = json.loads(target.read_text())
        finally:
            subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
        if metadata['input_key'] != key:
            raise ValueError('Published GGML artifact does not match this checkout')
        settings = config()
        settings.update(image=args.image, input_key=key)
        CONFIG.write_text(json.dumps(settings, indent=2) + '\n')
        print(f'Pinned {args.image}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'ggml-deps: {error}', file=sys.stderr)
        sys.exit(1)
