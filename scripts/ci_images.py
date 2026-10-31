#!/usr/bin/env python3
"""Plan and verify one image published to Docker Hub and GHCR."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'build/publication'
REGISTRIES = ('hangrylabs/yue2', 'ghcr.io/hangry-labs/yue2')
STABLE_TAG = re.compile(r'v\d+\.\d+\.\d+\Z')
DIGEST = re.compile(r'sha256:[a-f0-9]{64}\Z')


def plan(version, event, ref, requested_tag='', push_latest=True):
    release = ''
    moving = False
    if event == 'push':
        if ref == 'refs/heads/master':
            moving = True
        elif ref.startswith('refs/tags/'):
            release = ref.removeprefix('refs/tags/')
    elif event == 'workflow_dispatch':
        release = requested_tag
        moving = push_latest
        if not release and not moving:
            raise ValueError('No image tags selected; choose a stable tag or enable push_latest')
    if release and (not STABLE_TAG.fullmatch(release) or release != 'v' + version):
        raise ValueError('Stable Git tag must match the release VERSION (no snapshot suffix)')
    tags = []
    if moving:
        tags.extend(repo + ':latest' for repo in REGISTRIES)
    if release:
        tags.extend(repo + ':' + release for repo in REGISTRIES)
    return {'tags': tags, 'release_tag': release, 'publish': str(bool(tags)).lower()}


def run(*args, env=None):
    return subprocess.run(args, text=True, capture_output=True, check=False, env=env)


def check_checkout(publication):
    head = run('git', 'rev-parse', 'HEAD')
    if head.returncode or not re.fullmatch(r'[a-f0-9]{40}', head.stdout.strip()):
        raise ValueError('Cannot determine the checked-out source commit')
    if publication['release_tag']:
        tagged = run('git', 'rev-parse', '--verify', f"refs/tags/{publication['release_tag']}^{{commit}}")
        if tagged.returncode or tagged.stdout.strip() != head.stdout.strip():
            raise ValueError('Stable publication must build the commit of its existing Git tag')
    return head.stdout.strip()


def check_unpublished(publication):
    if not publication['release_tag']:
        return
    for ref in publication['tags']:
        if ref.endswith(':latest'):
            continue
        result = run('docker', 'buildx', 'imagetools', 'inspect', ref)
        if result.returncode == 0:
            raise ValueError(f'Immutable release tag already exists: {ref}')
        message = (result.stderr + result.stdout).lower()
        missing_manifest = any(token in message for token in ('manifest unknown', 'manifest_unknown'))
        missing_ref = ref.lower() + ': not found' in message
        if not (missing_manifest or missing_ref):
            raise RuntimeError(f'Cannot confirm that {ref} is absent; check registry access')


def inspect_digest(ref, env=None):
    result = run('docker', 'buildx', 'imagetools', 'inspect', ref, env=env)
    if result.returncode:
        raise RuntimeError(f'Cannot inspect published image: {ref}')
    match = re.search(r'^Digest:\s+(sha256:[a-f0-9]{64})\s*$', result.stdout, re.M)
    if not match:
        raise RuntimeError(f'No top-level OCI digest reported for {ref}')
    return match[1]


def verify_publication(publication, expected, env=None):
    if not DIGEST.fullmatch(expected):
        raise ValueError('Build action did not report a valid OCI digest')
    records = []
    for ref in publication['tags']:
        actual = ''
        for attempt in range(4):
            try:
                actual = inspect_digest(ref, env)
                if actual == expected:
                    break
            except RuntimeError:
                if attempt == 3:
                    raise
            if attempt < 3:
                time.sleep(2 ** attempt)
        if actual != expected:
            raise RuntimeError(f'Registry digest differs from the build result: {ref}')
        records.append({'image': ref, 'digest': actual, 'pinned': f'{ref}@{actual}'})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-existing', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--verify-public', action='store_true')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    plan_file = OUTPUT / 'image-plan.json'
    if args.check_existing:
        check_unpublished(json.loads(plan_file.read_text(encoding='utf-8')))
        return
    if args.verify or args.verify_public:
        publication = json.loads(plan_file.read_text(encoding='utf-8'))
        expected = os.environ.get('IMAGE_DIGEST', '')
        if args.verify_public:
            # Check public pull access without the logins used for publication.
            with tempfile.TemporaryDirectory(prefix='anonymous-', dir=OUTPUT) as directory:
                if not Path(directory).resolve().is_relative_to(OUTPUT.resolve()):
                    raise ValueError('Registry-check configuration is outside its output directory')
                try:
                    records = verify_publication(publication, expected, dict(os.environ, DOCKER_CONFIG=directory))
                except RuntimeError as error:
                    raise RuntimeError('Public pull verification failed. Check registry visibility/connectivity; '
                                       'a newly created GHCR package defaults to private and must be made public '
                                       'in its package settings. ' + str(error)) from error
        else:
            records = verify_publication(publication, expected)
        name = 'public-images.json' if args.verify_public else 'published-images.json'
        (OUTPUT / name).write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
        summary = '\n'.join(f'- `{record["pinned"]}`' for record in records)
        print(summary)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
                heading = 'Public pull access verified' if args.verify_public else 'Published container indexes verified'
                stream.write('## ' + heading + '\n\n' + summary + '\n')
        return
    version = (ROOT / 'VERSION').read_text().strip()
    result = plan(version, os.environ.get('GITHUB_EVENT_NAME', ''),
                  os.environ.get('GITHUB_REF', ''), os.environ.get('INPUT_IMAGE_TAG', ''),
                  os.environ.get('INPUT_PUSH_LATEST', 'true') == 'true')
    result['revision'] = check_checkout(result)
    plan_file.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('tags<<YUE2_IMAGE_TAGS\n' + '\n'.join(result['tags']) + '\nYUE2_IMAGE_TAGS\n')
            for key in ('publish', 'release_tag', 'revision'):
                stream.write(f'{key}={result[key]}\n')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f'container-publication: {error}', file=sys.stderr)
        raise SystemExit(1)
