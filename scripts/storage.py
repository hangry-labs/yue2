#!/usr/bin/env python3
"""Local runtime data paths and migration from the original checkout layout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
MODELS = DATA / 'models'
ADAPTERS = DATA / 'adapters'
CHECKPOINTS = DATA / 'checkpoints'
RESULTS = DATA / 'results'
MODEL_MANIFEST = ROOT / 'docker/models.json'
LEGACY = ('models', 'adapters', 'checkpoints', 'results')


def require_migrated():
    if any((ROOT / name).exists() for name in LEGACY):
        raise RuntimeError('Legacy local data detected. Finish active work, then run task stop, task data:migrate and task start. See docs/DEVELOPMENT.md#local-data.')


def migration_plan(root=ROOT):
    root = root.resolve()
    data = root / 'data'
    if data.is_symlink() or data.resolve() != data or not data.resolve().is_relative_to(root):
        raise RuntimeError('Refusing migration through a redirected data directory')
    plan = []
    for name in LEGACY:
        source, target = root / name, data / name
        if not source.exists():
            continue
        if source.is_symlink() or source.resolve() != source or not source.is_dir():
            raise RuntimeError(f'Refusing migration of redirected/non-directory storage: {source}')
        if target.exists() or target.is_symlink():
            raise RuntimeError(f'Both storage locations exist; reconcile manually without overwriting: {source}, {target}')
        if not target.resolve().is_relative_to(root) or target.resolve() == root:
            raise RuntimeError(f'Migration destination escapes the checkout: {target}')
        plan.append((source, target))
    return plan


def running_mounts():
    ids = subprocess.check_output(['docker', 'ps', '-q'], text=True).split()
    if not ids:
        return []
    containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True))
    return [(item['Name'].lstrip('/'), mount['Source'])
            for item in containers for mount in item.get('Mounts', [])
            if mount['Type'] == 'bind']


def migrate(root=ROOT):
    plan = migration_plan(root)
    if not plan:
        print('Storage already uses data/; nothing to migrate.')
        return
    # A running container can hold the old bind mount open. Check every proposed
    # move before renaming any directory, including mounts owned by other projects.
    for container, mounted in running_mounts():
        mounted = Path(os.path.normcase(mounted)).resolve()
        for source, _ in plan:
            normalized = Path(os.path.normcase(str(source))).resolve()
            if mounted == normalized or mounted.is_relative_to(normalized):
                raise RuntimeError(f'{container} still mounts {source}. Stop it before task data:migrate.')
    (root / 'data').mkdir(exist_ok=True)
    moved = []
    try:
        for source, target in plan:
            source.rename(target)
            moved.append((source, target))
    except OSError:
        for source, target in reversed(moved):
            target.rename(source)
        raise
    for source, target in moved:
        print(f'Moved {source.name}/ to data/{target.name}/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'migrate'))
    args = parser.parse_args()
    if args.command == 'migrate':
        migrate()
    else:
        for name in LEGACY:
            print(f'{name}: {DATA / name}')
        for source, target in migration_plan():
            print(f'Legacy directory: {source}; task data:migrate moves it to {target}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'yue2 storage: {error}', file=sys.stderr)
        sys.exit(1)
