"""Behavioral tests for the baseline parser and development safety rules."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = load('baseline', 'benchmarks/test1.py')
sys.path.insert(0, str(ROOT / 'scripts'))
dev = load('dev', 'scripts/dev.py')
images = load('images', 'scripts/ci_images.py')


class PromptTests(unittest.TestCase):
    def test_presentation_indentation_does_not_change_lyrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / 'prompt.txt'
            prompt.write_text('style=Pop\nlyrics=[Verse]\n       First line\n\n       Second line\n')
            style, lyrics = baseline.parse_prompt(prompt)
            self.assertEqual(style, 'Pop')
            self.assertEqual(lyrics, '[Verse]\nFirst line\n\nSecond line')

    def test_missing_lyrics_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / 'prompt.txt'
            prompt.write_text('style=Pop\n')
            with self.assertRaisesRegex(ValueError, 'lyrics='):
                baseline.parse_prompt(prompt)


class PublicationTests(unittest.TestCase):
    def test_main_build_does_not_publish(self):
        self.assertEqual(images.plan('0.1.0-snapshot', 'push', 'refs/heads/main')['publish'], 'false')

    def test_release_identity_must_match(self):
        with self.assertRaises(ValueError):
            images.plan('0.1.0-snapshot', 'push', 'refs/tags/v0.1.0')
        result = images.plan('0.1.0', 'push', 'refs/tags/v0.1.0')
        self.assertEqual(result['tags'], 'ghcr.io/hangry-labs/yue2:v0.1.0')
        self.assertEqual(result['publish'], 'true')

    def test_manual_publication_requires_explicit_selection(self):
        self.assertEqual(images.plan('0.1.0', 'workflow_dispatch', '', 'latest')['publish'], 'false')
        with self.assertRaises(ValueError):
            images.plan('0.1.0', 'workflow_dispatch', '', 'tag\nother=value', True)
        with self.assertRaises(ValueError):
            images.plan('0.1.0-snapshot', 'workflow_dispatch', '', 'v0.1.0', True)


class LifecycleTests(unittest.TestCase):
    def test_auto_uses_pinned_archive_even_when_local_image_exists(self):
        dependency = {'image': 'ggml-deps', 'key': 'current', 'archive': {'sha256': 'pinned'},
                      'architectures': '86-real;120a-real', 'cuda_base': 'cuda'}
        with patch.dict(dev.os.environ, {'YUE2_TASK_CUDA_ARCHITECTURES': 'auto',
                                         'YUE2_TASK_GGML_DEPS_IMAGE': ''}), \
                patch.object(dev.ggml_release, 'plan', return_value=dependency), \
                patch.object(dev, 'local_dependency', return_value='local-artifact'), \
                patch.object(dev, 'architectures', return_value='120a-real'):
            _, arch, selected = dev.build_dependency()
            self.assertEqual((arch, selected), ('86-real;120a-real', 'release-archive'))

    def test_auto_reuses_distribution_artifact_on_covered_gpu(self):
        dependency = {'image': 'ggml-deps', 'key': 'current',
                      'architectures': '86-real;120a-real', 'cuda_base': 'cuda'}
        with patch.dict(dev.os.environ, {'YUE2_TASK_CUDA_ARCHITECTURES': 'auto',
                                         'YUE2_TASK_GGML_DEPS_IMAGE': ''}), \
                patch.object(dev.ggml_release, 'plan', return_value=dependency), \
                patch.object(dev, 'local_dependency', return_value='local-artifact'), \
                patch.object(dev, 'architectures', return_value='120a-real'):
            _, arch, image = dev.build_dependency()
            self.assertEqual((arch, image), ('86-real;120a-real', 'local-artifact'))

    def test_auto_keeps_target_outside_distribution_artifact(self):
        dependency = {'image': 'registry@sha256:abc', 'key': 'current',
                      'architectures': '86-real;120a-real', 'cuda_base': 'cuda'}
        with patch.dict(dev.os.environ, {'YUE2_TASK_CUDA_ARCHITECTURES': 'auto',
                                         'YUE2_TASK_GGML_DEPS_IMAGE': ''}), \
                patch.object(dev.ggml_release, 'plan', return_value=dependency), \
                patch.object(dev, 'local_dependency', return_value=''), \
                patch.object(dev.ggml_deps, 'fingerprint', return_value='other-gpu'), \
                patch.object(dev, 'architectures', return_value='121a-real'):
            _, arch, image = dev.build_dependency()
            self.assertEqual((arch, image), ('121a-real', ''))

    def test_explicit_gpu_target_does_not_use_different_pinned_artifact(self):
        dependency = {'image': 'registry@sha256:abc', 'key': 'current',
                      'architectures': '86-real;120a-real', 'cuda_base': 'cuda'}
        with patch.dict(dev.os.environ, {'YUE2_TASK_CUDA_ARCHITECTURES': '120a-real',
                                         'YUE2_TASK_GGML_DEPS_IMAGE': ''}), \
                patch.object(dev.ggml_release, 'plan', return_value=dependency), \
                patch.object(dev, 'local_dependency', return_value=''), \
                patch.object(dev.ggml_deps, 'fingerprint', return_value='narrow'), \
                patch.object(dev, 'architectures', return_value='120a-real'):
            _, arch, image = dev.build_dependency()
            self.assertEqual((arch, image), ('120a-real', ''))

    def test_active_job_prevents_replacement(self):
        logs = Mock(stdout='[Server] Job deadbeef: {}\n', stderr='')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'status': 'running'}).encode()
        with patch.object(dev.subprocess, 'run', return_value=logs), \
                patch.object(dev.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'generation is active'):
                dev.active_jobs('yue2-dev', 8087)


if __name__ == '__main__':
    unittest.main()
