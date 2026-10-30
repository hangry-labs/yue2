#!/usr/bin/env python3
"""Plan one GHCR image variant; require stable tags to match VERSION."""
import os
from pathlib import Path
import re


def plan(version, event, ref, requested_tag='', requested_publish=False):
    publish = False
    tag = requested_tag or 'latest'
    if event == 'push' and ref.startswith('refs/tags/'):
        release = ref.removeprefix('refs/tags/')
        if not re.fullmatch(r'v\d+\.\d+\.\d+', release) or release != 'v' + version:
            raise ValueError('Stable Git tag must match the release VERSION (no snapshot suffix)')
        tag, publish = release, True
    elif event == 'workflow_dispatch':
        publish = requested_publish
        if publish and re.fullmatch(r'v\d+\.\d+\.\d+', tag) and tag != 'v' + version:
            raise ValueError('Stable container tag must match VERSION')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', tag):
        raise ValueError('Invalid container tag')
    return {'tags': 'ghcr.io/hangry-labs/yue2:' + tag, 'publish': str(publish).lower()}


def main():
    version = (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
    result = plan(version, os.environ.get('GITHUB_EVENT_NAME', ''),
                  os.environ.get('GITHUB_REF', ''), os.environ.get('INPUT_TAG', ''),
                  os.environ.get('INPUT_PUBLISH', 'false') == 'true')
    output = '\n'.join(key + '=' + value for key, value in result.items()) + '\n'
    print(output, end='')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write(output)


if __name__ == '__main__':
    main()
