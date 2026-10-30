#!/usr/bin/env python3
"""Verify the committed GGML snapshot against its recorded file hashes."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'vendor/ggml.snapshot.json').read_text())
    directory = ROOT / 'vendor/ggml'
    expected = manifest['sha256']
    failures = []
    for name, digest in expected.items():
        path = directory / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            failures.append(name)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    unexpected = actual - set(expected) - {'UPSTREAM.md'}
    if failures or unexpected:
        print('GGML snapshot differs: ' + ', '.join(failures + sorted(unexpected)), file=sys.stderr)
        return 1
    print(f'PASS: {len(expected)} GGML files match {manifest["commit"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
