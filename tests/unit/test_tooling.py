"""Behavioral tests for the baseline parser and development safety rules."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = load('baseline', 'benchmarks/test1.py')
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
