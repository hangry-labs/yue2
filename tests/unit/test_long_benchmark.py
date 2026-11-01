"""Long suite preserves original lyrics, keeps five seeds, and cannot require ASR."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.long import GENERATIONS, long_configuration, long_request, prompt, summarize, write_reports
from benchmarks.metrics import integrity_flags
from benchmarks.reports import compare
from benchmarks.run import preflight, score_run
from test_benchmarks import run_fixture


def long_run():
    run = run_fixture()
    run.update(suite='long_music', languages=['en'])
    run['environment']['asr'] = None
    run['configuration'] = {'suite': 'long_music', 'warmup': 'short', 'generation_count': 5}
    template = deepcopy(run['calls'][1])
    run['calls'] = [run['calls'][0]]
    for index in range(5):
        call = deepcopy(template)
        call.update(id='long-' + str(index), seed=831001 + index, client_seconds=61)
        call.pop('quality')
        call['server'].update(audio_seconds=300, pipeline_seconds=60, worker_seconds=60.3)
        run['calls'].append(call)
    return run


class LongPromptTests(unittest.TestCase):
    def test_original_sections_and_five_distinct_seeds_are_preserved(self):
        case = prompt()
        self.assertEqual(GENERATIONS, 5)
        self.assertTrue(case['style'].startswith('Cinematic synth-rock'))
        self.assertTrue(case['lyrics'].startswith('[Intro]'))
        self.assertIn('[Final Chorus]', case['lyrics'])
        self.assertTrue(case['lyrics'].endswith('We are coming home.'))
        for index in range(5):
            payload = long_request(case, index)
            self.assertEqual(payload['lyrics'], case['lyrics'])
            self.assertEqual(payload['duration'], 300)
            self.assertEqual(payload['steps'], 8)
            self.assertEqual(payload['seed'], 831001 + index)
            self.assertEqual(payload['lm_seed'], 831001 + index)
            self.assertNotIn('semantic_tokens', payload)
        config = long_configuration(case, 'short')
        self.assertEqual(config['generation_count'], 5)
        self.assertEqual(config['measured_count'], 5)
        self.assertFalse(config['asr'])
        self.assertEqual(long_configuration(case, 'first')['measured_count'], 4)

    def test_direction_and_style_labels_are_accepted_without_rewriting_words(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'prompt.txt'
            for label in ('direction', 'style'):
                path.write_text(label + ' = Soft pop\nlyrics=[Intro]\nMy original words.\n', encoding='utf-8')
                self.assertEqual(prompt(path)['lyrics'], '[Intro]\nMy original words.')
                self.assertEqual(prompt(path)['style'], 'Soft pop')
            path.write_text('lyrics only', encoding='utf-8')
            with self.assertRaises(ValueError):
                prompt(path)

    def test_long_duration_checks_do_not_apply_the_30_second_range(self):
        info = {'duration_seconds': 286.2, 'silent_window_fraction': 0, 'clipping_fraction': 0}
        self.assertEqual(integrity_flags(info, 250, 301), [])
        info['duration_seconds'] = 100
        self.assertIn('duration_outside_250_to_301_seconds', integrity_flags(info, 250, 301))

    def test_preflight_does_not_contact_asr_or_require_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / 'data/models'
            models.mkdir(parents=True)
            for name in ('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf'):
                (models / name).write_bytes(b'fixture')
            def execute(args, **_):
                if args[:2] == ['docker', 'version']:
                    return 'test'
                if args[:3] == ['docker', 'image', 'inspect']:
                    return json.dumps([{'Id': 'test-image', 'Config': {'Labels': {}}}])
                raise AssertionError(args)
            with patch('benchmarks.run.ROOT', root), \
                 patch('benchmarks.run.shutil.which', side_effect=lambda name: name if name == 'nvidia-smi' else None), \
                 patch('benchmarks.run.command', side_effect=execute), \
                 patch('benchmarks.run.gpu_info', return_value={}), \
                 patch('benchmarks.run.gpu_workers', return_value=[]), \
                 patch('benchmarks.run.asr_inventory', side_effect=AssertionError('ASR must not be contacted')):
                result = preflight(SimpleNamespace(image='image', gpu='0', dev_container='dev'), [prompt()], use_asr=False)
            self.assertIsNone(result['asr'])
            self.assertIsNone(result['ffmpeg'])


class LongReportingTests(unittest.TestCase):
    def test_long_records_cannot_be_sent_to_asr_by_the_rescoring_command(self):
        with patch('benchmarks.run.asr_inventory') as inventory:
            with self.assertRaisesRegex(ValueError, 'do not use ASR'):
                score_run(long_run(), Path('.'), 'http://judge.invalid')
        inventory.assert_not_called()

    def test_warm_long_statistics_exclude_cold_and_have_no_asr_scores(self):
        summary = summarize(long_run())
        self.assertEqual(summary['languages']['en']['calls'], 5)
        self.assertEqual(summary['languages']['en']['pipeline_seconds']['median'], 60)
        self.assertFalse(summary['asr_enabled'])
        self.assertNotIn('lyric_accuracy_percent', summary['languages']['en'])
        with tempfile.TemporaryDirectory() as temporary:
            write_reports(long_run(), temporary, public=True)
            report = (Path(temporary) / 'BENCHMARKS.md').read_text(encoding='utf-8')
            self.assertIn('no ASR requests', report)
            self.assertNotIn('ASR match %', report)

    def test_long_comparisons_do_not_access_asr_and_still_detect_latency_regressions(self):
        before, after = long_run(), long_run()
        self.assertTrue(compare(before, after)['passed'])
        after['calls'][1]['server']['pipeline_seconds'] = 90
        self.assertFalse(compare(before, after)['passed'])
        with self.assertRaises(ValueError):
            compare(before, after, score_drop=5)
        with self.assertRaises(ValueError):
            compare(run_fixture(), after)
