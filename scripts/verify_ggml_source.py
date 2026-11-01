#!/usr/bin/env python3
"""Verify the official GGML source pin and retained license without downloading."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    source = json.loads((root / 'docker/ggml-source.json').read_text(encoding='utf-8'))
    if source.get('schema') != 1 or source.get('repository') != 'https://github.com/ggml-org/ggml':
        raise ValueError('GGML source must identify the official repository')
    commit = source.get('commit', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(r'\d+\.\d+\.\d+', source.get('version', '')):
        raise ValueError('GGML source needs an exact commit and release version')
    if source.get('url') != 'https://codeload.github.com/ggml-org/ggml/tar.gz/' + commit:
        raise ValueError('GGML download URL must be pinned to the official commit')
    if not re.fullmatch(r'[0-9a-f]{64}', source.get('sha256', '')):
        raise ValueError('GGML source needs a SHA-256 archive checksum')
    notice = root / 'vendor/licenses/ggml-MIT.txt'
    if hashlib.sha256(notice.read_bytes()).hexdigest() != source.get('license_sha256'):
        raise ValueError('GGML license differs from the retained upstream notice')
    if (root / 'vendor/ggml').exists():
        raise ValueError('GGML source belongs in the build cache, not vendor/ggml')
    print(f'PASS: official GGML {source["version"]}, immutable source checksum and MIT notice')
    return source


if __name__ == '__main__':
    verify()
