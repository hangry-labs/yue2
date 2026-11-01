"""Validate small native dependency source pins and retained upstream notices."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {'httplib': 'yhirose/cpp-httplib', 'yyjson': 'ibireme/yyjson', 'minimp3': 'lieff/minimp3'}


def verify(root=ROOT):
    lock = json.loads((root / 'docker/app-deps.json').read_text(encoding='utf-8'))
    if lock.get('schema') != 1 or set(lock.get('packages', {})) != set(REPOSITORIES):
        raise ValueError('Native dependency lock must identify the three expected packages')
    for name, repo in REPOSITORIES.items():
        package = lock['packages'][name]
        commit = package.get('commit', '')
        if package.get('repository') != 'https://github.com/' + repo or not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError(f'{name}: expected official repository and exact commit')
        if package.get('url') != 'https://codeload.github.com/' + repo + '/tar.gz/' + commit:
            raise ValueError(f'{name}: source URL must be pinned to the official commit')
        if not re.fullmatch(r'[a-f0-9]{64}', package.get('sha256', '')):
            raise ValueError(f'{name}: source archive needs a SHA-256 checksum')
        notice = root / 'vendor/licenses' / (name + '.txt')
        if hashlib.sha256(notice.read_bytes()).hexdigest() != package.get('license_sha256'):
            raise ValueError(f'{name}: retained upstream license changed')
        folder = root / 'vendor' / ('cpp-httplib' if name == 'httplib' else name)
        if folder.exists():
            raise ValueError(f'{name}: upstream source belongs in the build cache')
    print('PASS: HTTP/JSON/MP3 decoder source pins and upstream notices')
    return lock


if __name__ == '__main__':
    verify()
