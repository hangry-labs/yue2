"""Reject altered downloads and unsafe archives before handing files to Docker."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import ggml_release as release


class ReleaseArchiveTests(unittest.TestCase):
    def test_small_exported_recipe_reproduces_the_dependency_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            key = release.ggml_deps.fingerprint()
            path = release.export_recipe(Path(directory), key)
            extracted = Path(directory) / 'recipe'
            with tarfile.open(path) as packed:
                names = packed.getnames()
                self.assertTrue(all(not name.startswith(('data/', '.ai/', 'vendor/ggml/')) for name in names))
                packed.extractall(extracted, filter='data')
            settings = json.loads((extracted / 'docker/ggml-deps.json').read_text())
            self.assertIsNone(settings['archive'])
            self.assertIsNone(settings['image'])
            self.assertIsNone(settings['input_key'])
            self.assertEqual(release.ggml_deps.fingerprint(extracted), key)
            first = path.read_bytes()
            release.export_recipe(Path(directory), key)
            self.assertEqual(path.read_bytes(), first)

    def fixture(self, directory, changed=False, metadata_key='current'):
        payload = b'// tested GGML header\n'
        metadata = {'input_key': metadata_key,
                    'files': {'include/ggml.h': hashlib.sha256(payload).hexdigest()}}
        archive = Path(directory) / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as packed:
            for name, data in (('opt/ggml/include/ggml.h', b'changed' if changed else payload),
                               ('opt/ggml/yue2-ggml.json', json.dumps(metadata).encode())):
                item = tarfile.TarInfo(name)
                item.size = len(data)
                packed.addfile(item, io.BytesIO(data))
        dependency = {'key': 'current', 'archive': {
            'url': 'https://example.com/dependency.tar.gz',
            'sha256': release.sha256(archive), 'size': archive.stat().st_size}}
        return archive, dependency

    def test_download_extract_verify_and_reuse_offline(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            archive, dependency = self.fixture(directory)
            cache = Path(directory) / 'cache'
            with patch.object(release.urllib.request, 'urlopen', return_value=io.BytesIO(archive.read_bytes())):
                context = release.prepare(dependency, cache)
            self.assertEqual((context / 'opt/ggml/include/ggml.h').read_bytes(), b'// tested GGML header\n')
            with patch.object(release.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected download')):
                self.assertEqual(release.prepare(dependency, cache), context)
            (context / 'opt/ggml/include/ggml.h').write_text('accidentally changed')
            with self.assertRaisesRegex(ValueError, 'recorded hashes'):
                release.prepare(dependency, cache)

    def test_corrupt_download_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            archive, dependency = self.fixture(directory)
            data = bytearray(archive.read_bytes())
            data[-1] ^= 1
            cache = Path(directory) / 'cache'
            with patch.object(release.urllib.request, 'urlopen', return_value=io.BytesIO(data)):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    release.prepare(dependency, cache)
            self.assertFalse(list(cache.rglob('dependency.tar.gz')))
            self.assertFalse(list(cache.rglob('root')))
            self.assertFalse(list(cache.rglob('*.partial')))

    def test_download_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            archive, dependency = self.fixture(directory)
            with patch.object(release.urllib.request, 'urlopen', return_value=io.BytesIO(archive.read_bytes() + b'extra')):
                with self.assertRaisesRegex(ValueError, 'exceeds its pinned size'):
                    release.prepare(dependency, Path(directory) / 'cache')

    def test_manifest_mismatch_and_wrong_key_are_rejected(self):
        for options, error in (({'changed': True}, 'recorded hashes'),
                               ({'metadata_key': 'old'}, 'source/options')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                archive, dependency = self.fixture(directory, **options)
                target = Path(directory) / 'unpacked'
                target.mkdir()
                release.extract(archive, target)
                with self.assertRaisesRegex(ValueError, error):
                    release.verify_context(target, dependency['key'])

    def test_unsafe_paths_and_links_are_rejected_before_extraction(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('/opt/ggml/file', tarfile.REGTYPE),
                           ('opt/ggml/../../escape', tarfile.REGTYPE),
                           ('opt/ggml/a\\b', tarfile.REGTYPE), ('opt/ggml/a:stream', tarfile.REGTYPE),
                           ('opt/ggml/link', tarfile.SYMTYPE), ('opt/ggml/hard', tarfile.LNKTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / 'unsafe.tar.gz'
                with tarfile.open(archive, 'w:gz') as packed:
                    item = tarfile.TarInfo(name)
                    item.type = kind
                    item.linkname = '../../escape'
                    packed.addfile(item)
                target = Path(directory) / 'unpacked'
                target.mkdir()
                with self.assertRaises(ValueError):
                    release.extract(archive, target)
                self.assertEqual(list(target.iterdir()), [])
                self.assertFalse((Path(directory) / 'escape').exists())

    def test_duplicate_files_and_oversized_payload_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'duplicate.tar.gz'
            with tarfile.open(archive, 'w:gz') as packed:
                packed.addfile(tarfile.TarInfo('opt/ggml/file'))
                packed.addfile(tarfile.TarInfo('opt/ggml/file'))
            target = Path(directory) / 'unpacked'
            target.mkdir()
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                release.extract(archive, target)
            archive, _ = self.fixture(directory)
            with patch.object(release, 'MAX_UNPACKED', 1):
                with self.assertRaisesRegex(ValueError, 'payload exceeds'):
                    release.extract(archive, target)

    def test_stale_or_unpinned_release_configuration_fails_early(self):
        base = {'image': None, 'input_key': 'current', 'archive': {
            'url': 'https://example.com/dependency.tar.gz', 'sha256': 'a' * 64, 'size': 1}}
        computed = {'key': 'current', 'image': 'ggml-deps'}
        with patch.object(release.ggml_deps, 'plan', return_value=computed):
            self.assertTrue(release.plan(base)['archive'])
            for field, value in (('input_key', 'old'), ('image', 'registry/image')):
                settings = dict(base, **{field: value})
                with self.assertRaises(ValueError):
                    release.plan(settings)
            for field, value in (('url', 'http://example.com/file'), ('sha256', ''), ('size', -1)):
                settings = dict(base, archive=dict(base['archive'], **{field: value}))
                with self.assertRaises(ValueError):
                    release.plan(settings)


if __name__ == '__main__':
    unittest.main()
