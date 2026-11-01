"""Native library sources must be immutable upstream pins, not local forks."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.verify_app_deps import verify

ROOT = Path(__file__).resolve().parents[2]


class NativeDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('docker/app-deps.json', 'vendor/licenses/httplib.txt',
                     'vendor/licenses/yyjson.txt', 'vendor/licenses/minimp3.txt'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_all_sources_verify_without_network_or_vendored_code(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(set(verify(self.root)['packages']), {'httplib', 'yyjson', 'minimp3'})

    def test_source_substitution_or_missing_checksum_is_rejected(self):
        path = self.root / 'docker/app-deps.json'
        original = path.read_text()
        for package in ('httplib', 'yyjson', 'minimp3'):
            for field, value in [('commit', 'master'), ('sha256', ''),
                                 ('url', 'https://example.com/latest.tar.gz'),
                                 ('repository', 'https://example.com/fork')]:
                with self.subTest(package=package, field=field):
                    lock = json.loads(original)
                    lock['packages'][package][field] = value
                    path.write_text(json.dumps(lock))
                    with self.assertRaises(ValueError):
                        verify(self.root)

    def test_notice_changes_are_rejected(self):
        (self.root / 'vendor/licenses/yyjson.txt').write_text('removed upstream notice')
        with self.assertRaisesRegex(ValueError, 'license'):
            verify(self.root)

    def test_upstream_source_cannot_be_silently_vendored_again(self):
        (self.root / 'vendor/cpp-httplib').mkdir()
        with self.assertRaisesRegex(ValueError, 'build cache'):
            verify(self.root)
