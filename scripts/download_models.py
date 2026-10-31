#!/usr/bin/env python3
"""Fetch the two pinned inference GGUFs into external model storage."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import urllib.request

import storage


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def download(directory, manifest, name, spec):
    target = directory / name
    if target.exists():
        if target.stat().st_size != spec['size'] or sha256(target) != spec['sha256']:
            raise RuntimeError(f'Integrity mismatch: {target}. Move it aside before downloading again.')
        print(f'Verified {name}', flush=True)
        return
    staging = directory / '.downloads'
    staging.mkdir(exist_ok=True)
    partial = staging / (name + '.partial')
    url = f'https://huggingface.co/{manifest["repository"]}/resolve/{manifest["revision"]}/{name}'
    for attempt in range(5):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == spec['size']:
            break
        request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if offset and response.status != 206:
                    offset = 0
                completed = offset
                next_report = completed + 256 * 1024 * 1024
                with partial.open('ab' if offset else 'wb') as output:
                    while chunk := response.read(8 * 1024 * 1024):
                        output.write(chunk)
                        completed += len(chunk)
                        if completed >= next_report:
                            print(f'{name}: {completed / spec["size"]:.0%}', flush=True)
                            next_report += 256 * 1024 * 1024
            if completed != spec['size']:
                raise RuntimeError('Incomplete response')
            break
        except Exception as error:
            print(f'{name}: attempt {attempt + 1} failed ({type(error).__name__})', flush=True)
            if attempt == 4:
                raise RuntimeError(f'Download failed: {name}') from None
            time.sleep(2 ** attempt)
    if partial.stat().st_size != spec['size'] or sha256(partial) != spec['sha256']:
        raise RuntimeError(f'Download integrity mismatch: {partial}')
    partial.replace(target)
    print(f'Downloaded and verified {name}', flush=True)


def main():
    storage.require_migrated()
    directory = storage.MODELS
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(storage.MODEL_MANIFEST.read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(download, directory, manifest, name, spec)
                   for name, spec in manifest['files'].items()]
        for future in futures:
            future.result()


if __name__ == '__main__':
    main()
