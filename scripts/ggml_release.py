#!/usr/bin/env python3
"""Prepare a checksum-pinned GGML release archive as a Docker named context."""
import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

import check_no_weights
import ggml_deps

ROOT = Path(__file__).resolve().parents[1]
MAX_UNPACKED = 2 * 1024 ** 3


def plan(settings=None):
    settings = ggml_deps.config() if settings is None else settings
    result = ggml_deps.plan(settings)
    archive = settings.get('archive')
    if archive:
        url = urllib.parse.urlsplit(archive.get('url', ''))
        if settings.get('image'):
            raise ValueError('Select either a GGML release archive or registry image')
        if settings.get('input_key') != result['key']:
            raise ValueError('GGML release archive lock is stale; rebuild/publish the dependency '
                             'or explicitly clear archive/input_key for a source build')
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.fragment or any(c.isspace() for c in archive['url'])):
            raise ValueError('GGML archive URL must be a public HTTPS download URL')
        if not re.fullmatch(r'[0-9a-f]{64}', archive.get('sha256', '')):
            raise ValueError('GGML archive must have a pinned SHA-256 checksum')
        size = archive.get('size')
        if type(size) is not int or not 0 < size <= MAX_UNPACKED:
            raise ValueError('GGML archive size must be between 1 byte and 2 GiB')
    result['archive'] = archive
    return result


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_download(path, archive):
    if path.stat().st_size != archive['size'] or sha256(path) != archive['sha256']:
        raise ValueError(f'GGML archive size/checksum mismatch: {path}')


def download(archive, cache):
    target = cache / 'dependency.tar.gz'
    if target.exists():
        verify_download(target, archive)
        return target
    request = urllib.request.Request(archive['url'], headers={'User-Agent': 'yue2-build'})
    print(f'Downloading GGML dependency: {archive["url"]}', flush=True)
    # Keep only a fully verified download; a failed transfer cannot become a cache hit.
    with tempfile.NamedTemporaryFile(dir=cache, suffix='.partial', delete=False) as output:
        partial = Path(output.name)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                completed = 0
                while chunk := response.read(1024 * 1024):
                    completed += len(chunk)
                    if completed > archive['size']:
                        raise ValueError('GGML download exceeds its pinned size')
                    output.write(chunk)
            output.close()
            verify_download(partial, archive)
            partial.replace(target)
        finally:
            output.close()
            partial.unlink(missing_ok=True)
    return target


def member_path(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or '..' in path.parts or path.parts[:2] != ('opt', 'ggml')
            or any(not re.fullmatch(r'[A-Za-z0-9._+-]+', part) for part in path.parts)):
        raise ValueError(f'Unsafe GGML archive path: {name}')
    return path


def extract(archive, destination):
    # Never use unrestricted tar extraction. Reject links, special files,
    # duplicate paths and oversized payloads before writing any member.
    with tarfile.open(archive, 'r:gz') as packed:
        members = packed.getmembers()
        if len(members) > 4096:
            raise ValueError('Too many files in GGML archive')
        names = set()
        total = 0
        for item in members:
            name = member_path(item.name).as_posix()
            if name in names or not (item.isdir() or item.type in (tarfile.REGTYPE, tarfile.AREGTYPE)):
                raise ValueError(f'Duplicate, linked or special GGML archive member: {item.name}')
            names.add(name)
            total += item.size
            if item.size < 0 or total > MAX_UNPACKED:
                raise ValueError('GGML archive payload exceeds 2 GiB')
        for item in members:
            target = destination.joinpath(*member_path(item.name).parts)
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with packed.extractfile(item) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o644)


def verify_context(context, key):
    if context.is_symlink():
        raise ValueError('Links are forbidden in the GGML context')
    paths = list(context.rglob('*'))
    for path in paths:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f'Links/special files are forbidden in the GGML context: {path}')
    prefix = context / 'opt/ggml'
    metadata_path = prefix / 'yue2-ggml.json'
    metadata = json.loads(metadata_path.read_text())
    if metadata['input_key'] != key:
        raise ValueError('GGML release metadata does not match the current source/options')
    actual = {}
    for path in paths:
        if path.is_file() and path != metadata_path:
            if not path.is_relative_to(prefix):
                raise ValueError('Unexpected file outside the GGML installation')
            actual[path.relative_to(prefix).as_posix()] = sha256(path)
    if actual != metadata['files']:
        raise ValueError('GGML release files differ from their recorded hashes')
    check_no_weights.check(context)


def prepare(dependency, cache_dir=None, dry=False):
    archive = dependency.get('archive')
    if not archive:
        return None
    cache = (cache_dir or ROOT / 'build/ggml-release') / archive['sha256']
    context = cache / 'root'
    if dry:
        return context
    cache.mkdir(parents=True, exist_ok=True)
    downloaded = download(archive, cache)
    if not context.exists():
        with tempfile.TemporaryDirectory(prefix='.extract-', dir=cache) as directory:
            staging = Path(directory)
            # Verify bounds before the directory rename and temporary-tree cleanup.
            if not staging.resolve().is_relative_to(cache.resolve()):
                raise ValueError('GGML staging directory is outside its cache')
            extract(downloaded, staging)
            verify_context(staging, dependency['key'])
            if not context.exists():
                staging.replace(context)
    verify_context(context, dependency['key'])
    print(f'PASS: verified GGML release archive and installed files ({dependency["key"]})', flush=True)
    return context


def export(output_dir=None, image=None):
    # Source identity stays independent of transport: a new archive does not
    # invalidate the compiled library merely because the downloader changes.
    dependency = ggml_deps.plan()
    key = dependency['key']
    image = image or 'yue2-ggml:' + key[:20]
    output_dir = output_dir or ROOT / 'data/results/build-deps' / key[:20]
    output_dir.mkdir(parents=True, exist_ok=True)
    cuda = re.search(r':(\d+\.\d+)', dependency['cuda_base'])
    name = 'yue2-ggml-linux-amd64-' + ('cuda' + cuda[1] + '-' if cuda else '') + key[:20] + '.tar.gz'
    archive = output_dir / name
    with tempfile.TemporaryDirectory(prefix='.export-', dir=output_dir) as directory:
        staging = Path(directory)
        if not staging.resolve().is_relative_to(output_dir.resolve()):
            raise ValueError('GGML export staging is outside its output directory')
        raw = staging / 'docker-copy.tar'
        container = subprocess.check_output(['docker', 'create', image, '/unused'], text=True).strip()
        try:
            with raw.open('wb') as stream:
                subprocess.run(['docker', 'cp', container + ':/opt/ggml', '-'], stdout=stream, check=True)
        finally:
            subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
        compressed_path = staging / name
        with tarfile.open(raw) as source, compressed_path.open('wb') as stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0, compresslevel=6) as compressed:
                with tarfile.open(fileobj=compressed, mode='w|') as target:
                    for item in source:
                        path = PurePosixPath(item.name)
                        if not path.parts or path.parts[0] != 'ggml':
                            raise ValueError('Unexpected file outside the GGML installation')
                        exported = copy.copy(item)
                        exported.name = member_path('opt/' + path.as_posix()).as_posix()
                        if not (item.isdir() or item.isfile()):
                            raise ValueError('Links/special files cannot be exported')
                        exported.uid = exported.gid = 0
                        exported.uname = exported.gname = 'root'
                        exported.mtime = 0
                        exported.mode = 0o755 if item.isdir() else 0o644
                        target.addfile(exported, source.extractfile(item) if item.isfile() else None)
        context = staging / 'check'
        context.mkdir()
        extract(compressed_path, context)
        verify_context(context, key)
        compressed_path.replace(archive)
    digest = sha256(archive)
    checksum = output_dir / (name + '.sha256')
    checksum.write_text(digest + '  ' + name + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'archive': str(archive), 'checksum': str(checksum),
                      'size': archive.stat().st_size, 'sha256': digest, 'input_key': key}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'prepare', 'export'))
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--image')
    args = parser.parse_args()
    if args.command == 'export':
        export(args.output_dir, args.image)
        return
    dependency = plan()
    context = prepare(dependency, args.cache_dir) if args.command == 'prepare' else None
    print(json.dumps(dependency, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        outputs = {k: dependency[k] for k in ('key', 'image', 'architectures', 'cuda_base')}
        outputs['context'] = 'selected-ggml=' + context.as_posix() if context else ''
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            for key, value in outputs.items():
                stream.write(f'{key}={value}\n')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print(f'ggml-release: {error}', file=sys.stderr)
        sys.exit(1)
