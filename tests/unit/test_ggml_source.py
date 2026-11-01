"""Dependency pins must remain immutable and retain the upstream license."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.verify_ggml_source import verify

ROOT = Path(__file__).resolve().parents[2]


class SourcePinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('docker/ggml-source.json', 'vendor/licenses/ggml-MIT.txt'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_pin_and_notice_verify_without_downloading_source(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verify(self.root)['version'], '0.28.0')
        self.assertFalse((self.root / 'vendor/ggml').exists())

    def test_mutable_or_unpinned_source_is_rejected(self):
        path = self.root / 'docker/ggml-source.json'
        original = json.loads(path.read_text())
        for field, value in [('url', 'https://example.com/latest.tar.gz'),
                             ('commit', 'master'), ('sha256', ''),
                             ('repository', 'https://example.com/fork')]:
            with self.subTest(field=field):
                path.write_text(json.dumps({**original, field: value}))
                with self.assertRaises(ValueError):
                    verify(self.root)

    def test_modified_license_is_rejected(self):
        (self.root / 'vendor/licenses/ggml-MIT.txt').write_text('missing notice')
        with self.assertRaisesRegex(ValueError, 'license'):
            verify(self.root)

    def test_source_cannot_be_accidentally_vendored_again(self):
        (self.root / 'vendor/ggml').mkdir()
        with self.assertRaisesRegex(ValueError, 'build cache'):
            verify(self.root)
