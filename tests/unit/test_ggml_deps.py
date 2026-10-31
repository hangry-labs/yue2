"""Artifact selection must reject stale dependencies and ignore app-only edits."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ggml_deps', ROOT / 'scripts/ggml_deps.py')
deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deps)


class DependencyIdentityTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        files = {
            'docker/ggml-deps.json': json.dumps({'schema': 1, 'cuda_base': 'cuda@sha256:123',
                                               'architectures': '86-real'}),
            'Dockerfile': 'FROM cuda AS ggml-deps\n' + deps.MARKER + '\nFROM app\n',
            'scripts/ggml_deps.py': '# helper\n',
            'scripts/check_no_weights.py': '# guard\n',
            'cmake/ggml-deps/CMakeLists.txt': '# options\n',
            'cmake/ggml-abi.cmake': '# ABI\n',
            'vendor/ggml/source.cpp': '// exact snapshot bytes\n',
            'vendor/ggml.snapshot.json': '{"commit":"test-snapshot"}\n',
        }
        for name, value in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value.encode())
        return root

    def test_application_and_lock_edits_reuse_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            before = deps.fingerprint(root)
            with (root / 'Dockerfile').open('a') as stream:
                stream.write('COPY changed-ui /web\nARG SOURCE_REVISION=new\n')
            settings = json.loads((root / 'docker/ggml-deps.json').read_text())
            settings.update(image='registry/deps@sha256:' + 'a' * 64, input_key=before)
            (root / 'docker/ggml-deps.json').write_text(json.dumps(settings))
            self.assertEqual(deps.fingerprint(root), before)

    def test_source_options_architecture_and_toolchain_invalidate(self):
        for filename in ('vendor/ggml/source.cpp', 'cmake/ggml-deps/CMakeLists.txt', 'cmake/ggml-abi.cmake',
                         'scripts/ggml_deps.py', 'scripts/check_no_weights.py'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                before = deps.fingerprint(root)
                with (root / filename).open('a') as stream:
                    stream.write('// changed\n')
                self.assertNotEqual(deps.fingerprint(root), before)
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            before = deps.fingerprint(root)
            self.assertNotEqual(deps.fingerprint(root, architectures='89-real'), before)
            self.assertNotEqual(deps.fingerprint(root, cuda_base='other'), before)
            path = root / 'Dockerfile'
            path.write_text(path.read_text().replace('FROM cuda', 'FROM other'))
            self.assertNotEqual(deps.fingerprint(root), before)

    def test_our_text_line_endings_do_not_change_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            before = deps.fingerprint(root)
            for filename in ('Dockerfile', 'scripts/ggml_deps.py', 'cmake/ggml-deps/CMakeLists.txt'):
                path = root / filename
                path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
            self.assertEqual(deps.fingerprint(root), before)

    def test_missing_boundary_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root / 'Dockerfile').write_text('FROM cuda\n')
            with self.assertRaisesRegex(ValueError, 'boundary'):
                deps.fingerprint(root)

    def test_pin_requires_digest_and_matching_inputs(self):
        settings = {'schema': 1, 'architectures': '86-real', 'cuda_base': 'cuda',
                    'image': 'registry/deps:latest', 'input_key': 'current'}
        with patch.object(deps, 'fingerprint', return_value='current'):
            with self.assertRaisesRegex(ValueError, 'digest-pinned'):
                deps.plan(settings)
            settings['image'] = 'registry/deps@sha256:' + 'a' * 64
            settings['input_key'] = 'old'
            with self.assertRaisesRegex(ValueError, 'stale'):
                deps.plan(settings)
            settings['input_key'] = 'current'
            self.assertEqual(deps.plan(settings)['image'], settings['image'])
            settings.update(image=None, input_key=None)
            self.assertEqual(deps.plan(settings)['image'], 'ggml-deps')


if __name__ == '__main__':
    unittest.main()
