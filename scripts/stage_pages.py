"""Stage public Git files for a local Pages build, including unstaged edits.

Git ignore rules and explicit private-file checks apply before Jekyll reads the
tree. Output is always confined to this project's ignored preview directory.
"""
from pathlib import Path, PurePosixPath
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def private_path(name):
    parts = PurePosixPath(name).parts
    private_names = {'.ai', '.idea', 'AGENTS.md', '.env', 'UPSTREAM_ISSUES.md', 'UPSTREAM_PULL_REQUESTS.md'}
    return name.lower().endswith('.cred') or any(part in private_names for part in parts) or any(
        parts[index:index + 2] == ('docs', 'internal') for index in range(len(parts) - 1))


def stage(root=ROOT):
    root = root.resolve()
    preview = root / 'build/pages'
    destination = (preview / 'source').resolve()
    if (not preview.resolve().is_relative_to(root)
            or not destination.is_relative_to(preview.resolve()) or destination == preview.resolve()):
        raise ValueError('The Pages source stage must stay inside its preview directory.')
    names = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root).decode('utf-8').split('\0')
    names = sorted(set(filter(None, names)))
    if any(private_path(name) for name in names):
        raise ValueError('Private files must be untracked and ignored before building Pages.')
    # Resolve/verify all candidates before clearing our previous staged output.
    files = []
    for name in names:
        source = root / name
        if not source.exists():
            continue
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError('Pages inputs must be ordinary files inside the checkout.')
        if source.is_file():
            public_roots = ('docs/', 'assets/', 'examples/', 'site/theme/', 'web/src/assets/')
            public_files = {'README.md', '_config.yml', '404.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'}
            benchmark_doc = name.startswith('benchmarks/') and (
                name.endswith('.md') or name in ('benchmarks/BASELINE.json', 'benchmarks/corpus.json',
                    'benchmarks/long-music/BASELINE.json', 'benchmarks/fixtures/long-music.txt'))
            if name in public_files or name.startswith(public_roots) or benchmark_doc:
                files.append((source, destination / name))
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for source, target in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(f'Staged {len(files)} public files for Pages.')
    return destination


if __name__ == '__main__':
    stage()
