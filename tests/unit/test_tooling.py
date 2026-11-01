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


baseline = load('baseline', 'tests/benchmarks/test1.py')
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


class BaselineValidationTests(unittest.TestCase):
    log = ''.join(f'[NAR] Step {i}/8, 2000 ms\n' for i in range(1, 9))

    def test_sparse_and_explicit_eight_step_replays_are_valid(self):
        for replay in ({}, {'steps': 8}):
            with self.subTest(replay=replay):
                baseline.validate_steps(replay, self.log)

    def test_metadata_cannot_override_a_different_executed_step_count(self):
        for replay, log in (({'steps': 32}, self.log), ({'steps': 8}, self.log.replace('/8,', '/32,'))):
            with self.subTest(replay=replay):
                with self.assertRaisesRegex(ValueError, 'step count'):
                    baseline.validate_steps(replay, log)

    def test_missing_execution_steps_cannot_pass_with_default_metadata(self):
        for log in ('', self.log.split('[NAR] Step 8/8')[0]):
            with self.subTest(log=log):
                with self.assertRaisesRegex(ValueError, 'step count'):
                    baseline.validate_steps({}, log)


class PublicationTests(unittest.TestCase):
    def test_master_publishes_latest_to_both_registries(self):
        result = images.plan('0.1.0-snapshot', 'push', 'refs/heads/master')
        self.assertEqual(result['publish'], 'true')
        self.assertEqual(result['tags'], ['hangrylabs/yue2:latest', 'ghcr.io/hangry-labs/yue2:latest'])

    def test_pull_requests_and_other_branches_do_not_publish(self):
        for event, ref in (('pull_request', 'refs/pull/1/merge'), ('push', 'refs/heads/main'),
                           ('push', 'refs/heads/feature')):
            with self.subTest(event=event, ref=ref):
                result = images.plan('0.1.0-snapshot', event, ref)
                self.assertEqual((result['publish'], result['tags']), ('false', []))

    def test_release_identity_must_match(self):
        with self.assertRaises(ValueError):
            images.plan('0.1.0-snapshot', 'push', 'refs/tags/v0.1.0')
        result = images.plan('0.1.0', 'push', 'refs/tags/v0.1.0')
        self.assertEqual(result['tags'], ['hangrylabs/yue2:v0.1.0', 'ghcr.io/hangry-labs/yue2:v0.1.0'])
        self.assertEqual(result['publish'], 'true')

    def test_manual_defaults_match_master_and_stable_can_promote_latest(self):
        self.assertEqual(images.plan('0.1.0-snapshot', 'workflow_dispatch', '')['tags'],
                         ['hangrylabs/yue2:latest', 'ghcr.io/hangry-labs/yue2:latest'])
        stable = images.plan('0.1.0', 'workflow_dispatch', '', 'v0.1.0', False)
        self.assertEqual(stable['tags'], ['hangrylabs/yue2:v0.1.0', 'ghcr.io/hangry-labs/yue2:v0.1.0'])
        promoted = images.plan('0.1.0', 'workflow_dispatch', '', 'v0.1.0', True)
        self.assertEqual(len(promoted['tags']), 4)
        for version, tag, latest in (('0.1.0', '', False), ('0.1.0', 'tag\nother=value', True),
                                     ('0.1.0-snapshot', 'v0.1.0', True), ('0.1.0', 'latest', True)):
            with self.subTest(version=version, tag=tag):
                with self.assertRaises(ValueError):
                    images.plan(version, 'workflow_dispatch', '', tag, latest)

    def test_stable_tag_must_match_the_checked_out_commit(self):
        publication = images.plan('0.1.0', 'push', 'refs/tags/v0.1.0')
        head = Mock(returncode=0, stdout='a' * 40 + '\n')
        wrong_tag = Mock(returncode=0, stdout='b' * 40 + '\n')
        with patch.object(images, 'run', side_effect=[head, wrong_tag]):
            with self.assertRaisesRegex(ValueError, 'existing Git tag'):
                images.check_checkout(publication)
        with patch.object(images, 'run', side_effect=[head, head]):
            self.assertEqual(images.check_checkout(publication), 'a' * 40)

    def test_stable_registry_tags_cannot_be_overwritten(self):
        publication = images.plan('0.1.0', 'push', 'refs/tags/v0.1.0')
        with patch.object(images, 'run', return_value=Mock(returncode=0)):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                images.check_unpublished(publication)
        with patch.object(images, 'run', return_value=Mock(returncode=1, stderr='network timeout', stdout='')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot confirm'):
                images.check_unpublished(publication)
        with patch.object(images, 'run', return_value=Mock(
                returncode=1, stderr='credential helper executable not found', stdout='')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot confirm'):
                images.check_unpublished(publication)
        with patch.object(images, 'run', return_value=Mock(returncode=1, stderr='manifest unknown', stdout='')):
            images.check_unpublished(publication)

    def test_both_registries_must_match_the_build_index(self):
        publication = images.plan('0.1.0-snapshot', 'push', 'refs/heads/master')
        expected = 'sha256:' + 'a' * 64
        with patch.object(images, 'inspect_digest', return_value=expected) as inspect:
            records = images.verify_publication(publication, expected)
            self.assertEqual([record['image'] for record in records], publication['tags'])
            self.assertEqual(inspect.call_count, 2)
        with patch.object(images, 'inspect_digest', side_effect=lambda ref, env: (
                expected if ref.startswith('hangrylabs/') else 'sha256:' + 'b' * 64)), \
                patch.object(images.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                images.verify_publication(publication, expected)
        with self.assertRaisesRegex(ValueError, 'valid OCI digest'):
            images.verify_publication(publication, '')

    def test_digest_parser_uses_the_top_level_index(self):
        index = 'sha256:' + 'a' * 64
        child = 'sha256:' + 'b' * 64
        output = f'Name: registry/image\nDigest: {index}\nManifests:\n  Digest: {child}\n'
        with patch.object(images, 'run', return_value=Mock(returncode=0, stdout=output)):
            self.assertEqual(images.inspect_digest('registry/image'), index)


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
