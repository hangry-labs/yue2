"""Build and preview the public README website without loading inference models."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

from stage_pages import stage

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'yue2:pages'
NAME = 'yue2-pages-preview'
LABEL = 'io.hangrylabs.project'


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def stop():
    found = subprocess.run(['docker', 'inspect', NAME], capture_output=True)
    if found.returncode:
        return
    info = json.loads(found.stdout)[0]
    if info['Config'].get('Labels', {}).get(LABEL) != 'yue2-pages':
        raise ValueError(f'{NAME} belongs to another process; leave it untouched.')
    run(['docker', 'rm', '-f', NAME])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'preview', 'test', 'stop'))
    parser.add_argument('--port', type=int, default=9005)
    args = parser.parse_args()
    if args.action == 'stop':
        stop()
        return
    source = stage()
    output = (ROOT / 'build/pages/output').resolve()
    if not output.is_relative_to((ROOT / 'build/pages').resolve()):
        raise ValueError('Pages output must stay inside build/pages.')
    output.mkdir(parents=True, exist_ok=True)
    run(['docker', 'build', '-f', 'site/Dockerfile', '-t', IMAGE, 'site'])
    run(['docker', 'run', '--rm', '--mount', f'type=bind,source={source},target=/source,readonly',
         '--mount', f'type=bind,source={output},target=/output', IMAGE, 'build',
         '--source', '/source', '--destination', '/output', '--config', '/source/_config.yml', '--safe', '--trace'])
    if args.action == 'test':
        run([sys.executable, 'scripts/verify_gallery.py'])
        run([sys.executable, 'scripts/check_pages.py'])
        run(['docker', 'run', '--rm', '--mount', f'type=bind,source={ROOT},target=/workspace,readonly',
             '--workdir', '/workspace', 'node:24-bookworm-slim', 'node', '--test',
             'tests/site/router.test.mjs', 'tests/site/gallery-localization.test.mjs'])
    if args.action == 'preview':
        stop()
        run(['docker', 'run', '-d', '--name', NAME, '--label', LABEL + '=yue2-pages',
             '-p', f'127.0.0.1:{args.port}:9005', '--mount', f'type=bind,source={output},target=/site,readonly',
             '--mount', f'type=bind,source={ROOT / "scripts/serve_pages.py"},target=/serve_pages.py,readonly',
             'python:3.13-slim', 'python', '/serve_pages.py', '--root', '/site', '--bind', '0.0.0.0'])
        for attempt in range(30):
            try:
                with urlopen(f'http://127.0.0.1:{args.port}/yue2/', timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.3)
        else:
            run(['docker', 'logs', NAME])
            raise RuntimeError('The website preview did not become ready.')
        print(f'Website preview: http://127.0.0.1:{args.port}/yue2/\nStop with task pages-stop.')


if __name__ == '__main__':
    main()
