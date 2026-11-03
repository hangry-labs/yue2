"""Check rendered Pages routes, public output boundaries and real Markdown rendering."""
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from check_no_weights import check as check_weights

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/yue2'
ORIGIN = 'https://hangry-labs.github.io'


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.links, self.ids, self.scripts, self.tags = [], set(), {}, {}
        self.script = None
        self.page_source = None
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'body':
            self.page_source = attrs.get('data-page-path')
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag == 'script' and attrs.get('id'):
            self.script = attrs['id']
            self.scripts[self.script] = ''
        for key in ('href', 'src'):
            if attrs.get(key):
                self.links.append((tag, attrs[key]))

    def handle_data(self, value):
        if self.script:
            self.scripts[self.script] += value

    def handle_endtag(self, tag):
        if tag == 'script':
            self.script = None


def verify(root=ROOT):
    output = root / 'build/pages/output'
    required = ['index.html', 'docs/index.html', 'docs/DOCKER.html', 'docs/WEBSITE.html',
                'benchmarks/index.html', 'benchmarks/BENCHMARKS.html',
                'benchmarks/speed/BENCHMARKS.html', 'benchmarks/memory/BENCHMARKS.html',
                'benchmarks/lyrics/BENCHMARKS.html',
                'benchmarks/long-music/BENCHMARKS.html',
                'examples/index.html', 'examples/guide/index.html', '404.html']
    for name in required:
        if not (output / name).is_file():
            raise ValueError(f'Missing rendered route: {name}')
    for code in ('nb', 'pl', 'ja', 'zh', 'es'):
        for route in (f'README.{code}.html', f'docs/{code}/index.html'):
            path = output / route
            if not path.is_file() or Document(path.read_text(encoding='utf-8')).language != code:
                raise ValueError(f'Missing translated page or incorrect HTML language: {route}')
    forbidden = {'.ai', '.git', '.idea', 'AGENTS.md', 'data', 'node_modules', '__pycache__',
                 'Gemfile', 'Gemfile.lock', 'Dockerfile', 'Taskfile.yml', 'CMakeLists.txt'}
    for path in output.rglob('*'):
        relative = path.relative_to(output)
        if any(part in forbidden for part in relative.parts) or path.suffix in ('.cred', '.pyc', '.py'):
            raise ValueError(f'Private/build input leaked into Pages: {relative}')
        if path.is_symlink():
            raise ValueError('Published files must not link outside the output.')
    check_weights(output)
    manifest = json.loads((root / 'examples/assets/manifest.json').read_text(encoding='utf-8'))
    music = output / 'examples/assets/music'
    expected_music = {output / 'examples' / song['audio']['path'] for song in manifest['songs']}
    if {path for path in music.rglob('*') if path.is_file()} != expected_music:
        raise ValueError('Published gallery must contain only the referenced Opus files.')
    for song in manifest['songs']:
        assets = [song[key] for key in ('audio', 'recipe', 'replay')] + list((song.get('downloads') or {}).values())
        for asset in assets:
            path = output / 'examples' / asset['path']
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != asset['sha256']:
                    raise ValueError(f'Published copy differs from its gallery manifest: {path}')
    documents = {p: Document(p.read_text(encoding='utf-8')) for p in output.rglob('*.html')}
    problems = []
    for path, document in documents.items():
        if document.tags.get('main') != 1 or document.tags.get('header', 0) < 1:
            problems.append(f'{path.relative_to(output)} needs one main and the shared header')
        page_map = json.loads(document.scripts.get('hangry-page-map', '{}'))
        source_paths = json.loads(document.scripts.get('hangry-source-paths', '[]'))
        location = ORIGIN + PREFIX + '/' + path.relative_to(output).as_posix()
        if location.endswith('index.html'):
            location = location[:-10]
        for tag, href in document.links:
            if href.startswith(('mailto:', 'data:', 'tel:', 'javascript:')):
                continue
            relative = not href.startswith(('/', '#', '?')) and not urlsplit(href).scheme
            base = ORIGIN + document.page_source if relative and tag == 'a' and document.page_source else location
            target = urlsplit(urljoin(base, href))
            if target.netloc != urlsplit(ORIGIN).netloc:
                continue
            if not target.path.startswith(PREFIX + '/'):
                problems.append(f'{path.relative_to(output)}: incorrect project path {href}')
                continue
            route = unquote(page_map.get(target.path, target.path))[len(PREFIX) + 1:]
            excluded = any(route.startswith(p) if p.endswith('/') else route == p for p in source_paths)
            destination = output / route
            if excluded:
                if not (root / route).exists():
                    problems.append(f'{path.relative_to(output)}: missing source file {href}')
                continue
            if destination.is_dir():
                destination /= 'index.html'
            if not destination.is_file():
                problems.append(f'{path.relative_to(output)}: missing {href} -> {route}')
            elif target.fragment and destination in documents and unquote(target.fragment) not in documents[destination].ids:
                problems.append(f'{path.relative_to(output)}: missing fragment {href}')
    overview = documents[output / 'index.html']
    if not all(overview.tags.get(tag) for tag in ('pre', 'code', 'table', 'details')):
        problems.append('Overview Markdown must render code, tables and release details.')
    gallery = documents[output / 'examples/index.html']
    if 'song-card-template' not in gallery.ids or gallery.tags.get('template') != 1:
        problems.append('The gallery must render its player template as HTML, not a Markdown code block.')
    if problems:
        raise ValueError('\n'.join(problems))
    print(f'PASS: {len(documents)} rendered pages, local links, Markdown and public output boundaries.')


if __name__ == '__main__':
    verify()
