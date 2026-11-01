"""Meaningful benchmark regressions: fidelity, isolation, warmness and comparison."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from benchmarks.metrics import (assessed_status, audio_stats, distribution, integrity_flags, lyric_score,
                                percentile, suite_timing, technical_flags, verify_warm)
from benchmarks.reports import compare, summarize, write_reports
from benchmarks.run import BASELINE_REPEATS, configuration, corpus, request, score_run
from benchmarks.runtime import GpuSampler, multipart, track_parts, transcribe, worker


def metric():
    return {'schema': 1, 'keep_loaded': True, 'module_loads': 0, 'resident_modules': 3,
            'resident_weight_bytes': 100 * 2**20, 'steps': 8, 'pipeline_seconds': 6.0,
            'worker_seconds': 6.1, 'audio_seconds': 30.0}


def run_fixture():
    result = {'schema': 1, 'run_id': 'test-run', 'status': 'complete', 'preliminary': False,
              'configuration': {'seed_schedule': [0, 1, 0], 'gpu_sample_seconds': .1},
              'environment': {'image_id': 'sha256:test', 'image_revision': 'test',
                  'gpu': {'name': 'test GPU', 'uuid': 'GPU-PRIVATE', 'driver_version': '1'},
                  'models': {'lm': {'sha256': 'test', 'bytes': 5}},
                  'asr': {'model': 'test-asr', 'url': 'http://private-judge.invalid'},
                  'host_path': 'C:/private/models'},
              'worker': {'startup_seconds': 1}, 'languages': ['en', 'zh', 'es', 'de'],
              'warm_idle': {'memory.used': '200'}, 'final_idle': {'memory.used': '200'}, 'calls': []}
    for language in result['languages']:
        for index, seed in enumerate((1, 2, 1)):
            result['calls'].append({'id': language + str(index), 'phase': 'measured', 'language': language,
                'case_id': language, 'seed': seed, 'audio_sha256': language + str(seed),
                'server': metric(), 'client_seconds': 6.2, 'gpu': {'peak_mib': 300, 'peak_delta_mib': 100},
                'quality': lyric_score('你好' if language == 'zh' else 'hello world',
                                        '你好' if language == 'zh' else 'hello world', language),
                'support': 'experimental' if language in ('es', 'de') else 'upstream-listed', 'warnings': []})
    cold = deepcopy(result['calls'][0])
    cold.update(phase='cold', id='cold')
    cold['server'].update(pipeline_seconds=40, worker_seconds=41, module_loads=3)
    result['calls'].insert(0, cold)
    return result


class LyricScoringTests(unittest.TestCase):
    def test_punctuation_case_and_unicode_width_are_normalized(self):
        score = lyric_score('HELLO, world!', 'Ｈｅｌｌｏ world.', 'en')
        self.assertEqual(score['lyric_accuracy_percent'], 100)
        self.assertTrue(score['exact_normalized'])

    def test_omitted_lyrics_are_penalized_not_accepted_as_a_matching_prefix(self):
        score = lyric_score('one two three four', 'one two', 'en')
        self.assertEqual(score['wer']['deletions'], 2)
        self.assertEqual(score['lyric_accuracy_percent'], 50)

    def test_repeats_insertions_and_empty_asr_are_penalized(self):
        score = lyric_score('hello', 'hello hello hello hello', 'en')
        self.assertEqual(score['wer']['error_rate'], 3)
        self.assertEqual(score['lyric_accuracy_percent'], 0)
        self.assertEqual(lyric_score('hello', '', 'en')['lyric_accuracy_percent'], 0)

    def test_chinese_uses_characters_without_inventing_word_boundaries(self):
        score = lyric_score('你好，世界！', '你好世', 'zh')
        self.assertIsNone(score['wer'])
        self.assertEqual(score['primary_metric'], 'CER')
        self.assertEqual(score['lyric_accuracy_percent'], 75)

    def test_diacritics_are_preserved(self):
        self.assertGreater(lyric_score('tú', 'tu', 'es')['cer']['error_rate'], 0)

    def test_asr_score_has_no_absolute_acceptance_cutoff(self):
        call = {'quality': lyric_score('one two three', '', 'en'),
                'warnings': ['lyric_accuracy_below_80_percent']}
        run = {'status': 'complete_with_warnings', 'calls': [call]}
        self.assertEqual(assessed_status(run), 'complete')
        self.assertEqual(technical_flags(call), [])
        info = {'duration_seconds': 30, 'silent_window_fraction': 0, 'clipping_fraction': 0}
        self.assertEqual(integrity_flags(info), [])
        info['duration_seconds'] = 10
        self.assertIn('duration_outside_25_to_31_seconds', integrity_flags(info))


class MeasurementTests(unittest.TestCase):
    def test_suite_wall_time_and_disjoint_request_breakdown(self):
        run = {'started_utc': '2026-11-01T16:00:00+00:00', 'finished_utc': '2026-11-01T16:02:18+00:00',
               'calls': [{'phase': 'cold', 'client_seconds': 45, 'server': {'pipeline_seconds': 40}},
                         {'phase': 'measured', 'client_seconds': 75, 'server': {'pipeline_seconds': 70},
                          'quality': {'asr_seconds': 2}}]}
        timing = suite_timing(run)
        self.assertEqual(timing['total_seconds'], 138)
        self.assertEqual(timing['other_seconds'], 16)
        self.assertEqual(timing['measured_pipeline_seconds'], 70)
        run['timing'] = timing
        run['finished_utc'] = '2026-11-02T16:00:00+00:00'
        run['calls'][1]['quality']['asr_seconds'] = 50
        self.assertEqual(suite_timing(run), timing)

    def test_percentiles_handle_single_small_and_empty_samples(self):
        self.assertEqual(percentile([1, 3], .95), 2.9)
        self.assertEqual(distribution([5])['median'], 5)
        self.assertIsNone(percentile([], .95))

    def test_zero_weight_loads_residency_and_real_timings_are_required(self):
        verify_warm(metric())
        for key, value in [('module_loads', 1), ('resident_modules', 2), ('keep_loaded', False),
                           ('steps', 32), ('pipeline_seconds', float('nan')), ('worker_seconds', 0)]:
            with self.subTest(key=key):
                changed = metric()
                changed[key] = value
                with self.assertRaises(ValueError):
                    verify_warm(changed)

    def test_device_sampling_filters_request_window_and_keeps_peak(self):
        sampler = GpuSampler('0')
        sampler.samples = [{'time': t, 'used_mib': used, 'utilization_percent': None}
                           for t, used in ((1, 500), (2, 200), (3, 300), (4, 900))]
        self.assertEqual(sampler.window(2, 3)['peak_mib'], 300)
        self.assertIsNone(sampler.window(2, 3)['mean_utilization_percent'])
        with self.assertRaises(RuntimeError):
            sampler.window(5, 6)

    def test_pcm_duration_silence_and_clipping_are_measured(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'test.wav'
            with wave.open(str(target), 'wb') as stream:
                stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
                stream.writeframes(struct.pack('<hh', 32767, -32768) * 24000 + b'\0' * 96000)
            info = audio_stats(target)
            self.assertEqual(info['duration_seconds'], 1)
            self.assertEqual(info['clipping_fraction'], .5)
            self.assertEqual(info['silent_window_fraction'], .5)

    def test_corpus_and_seed_schedule_keep_requests_fresh(self):
        cases = corpus()
        self.assertEqual(len(cases), 4)
        for case in cases:
            first, repeated = request(case), request(case, 2)
            self.assertEqual(first, repeated)
            self.assertEqual(first['duration'], 30)
            self.assertEqual(first['steps'], 8)
            self.assertNotIn('semantic_tokens', first)
            self.assertNotIn('abc', first)
        with self.assertRaises(ValueError):
            corpus('en,unknown')

    def test_default_baseline_has_ten_samples_per_language_and_a_repeat_control(self):
        cases = corpus()
        self.assertEqual(BASELINE_REPEATS, 10)
        config = configuration(cases, BASELINE_REPEATS, .1)
        self.assertEqual(len(cases) * config['repeats'], 40)
        self.assertEqual(config['warmups_per_language'] * len(cases), 4)
        for case in cases:
            seeds = [request(case, round_index)['seed'] for round_index in range(BASELINE_REPEATS)]
            self.assertEqual(len(seeds), 10)
            self.assertEqual(len(set(seeds)), 9)
            self.assertEqual(seeds[0], seeds[2])
            self.assertEqual([seed - case['seed'] for seed in seeds], config['seed_schedule'])

    def test_full_plan_remains_utf8_when_redirected_from_a_legacy_console(self):
        env = dict(os.environ, PYTHONIOENCODING='ascii')
        result = subprocess.run([sys.executable, '-m', 'benchmarks.run', 'plan'],
                                env=env, capture_output=True, check=True)
        plan = json.loads(result.stdout.decode('utf-8'))
        self.assertEqual(plan['repeats'], 10)
        self.assertEqual(len(plan['cases']), 4)
        self.assertIn('阳光', plan['request_profile'][1]['lyrics'])


class TransportTests(unittest.TestCase):
    def test_native_multipart_requires_a_single_audio_track(self):
        boundary = 'test'
        def part(kind, body):
            return f'--{boundary}\r\nContent-Type: {kind}\r\n\r\n'.encode() + body + b'\r\n'
        data = part('audio/wav', b'audio') + part('application/json', b'{"seed":1}')
        ending = b'--test--\r\n'
        self.assertEqual(track_parts('multipart/mixed; boundary=test', data + ending)[:2], (b'audio', {'seed': 1}))
        with self.assertRaises(ValueError):
            track_parts('multipart/mixed; boundary=test', data + part('audio/wav', b'other') + ending)

    def test_asr_never_receives_reference_lyrics(self):
        with patch('benchmarks.runtime.urlopen', return_value=io.BytesIO(b'{"text":"hello"}')) as open_url:
            transcribe('http://judge.invalid', 'test-asr', b'RIFF', 'en')
        body = open_url.call_args.args[0].data
        self.assertNotIn(b'name="prompt"', body)
        self.assertNotIn(b'name="lyrics"', body)
        self.assertIn(b'name="language"', body)

    def test_failed_worker_start_restores_only_the_owned_development_container(self):
        dev = {'Id': 'owned-dev', 'State': {'Running': True}}
        def execute(args, **_):
            if args[:2] == ['docker', 'run']:
                raise RuntimeError('startup failed')
            return ''
        with patch('benchmarks.runtime.container_info', return_value=dev), \
             patch('benchmarks.runtime.gpu_workers', return_value=[]), \
             patch('benchmarks.runtime.require_idle_dev'), \
             patch('benchmarks.runtime.gpu_info', return_value={'utilization.gpu': '0'}), \
             patch('benchmarks.runtime.command', side_effect=execute) as invoked:
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                with worker('image', '0', 'dev', True, 'test'):
                    self.fail('Worker must not become ready')
        self.assertIn((['docker', 'start', 'owned-dev'],), [call.args for call in invoked.call_args_list])

    def test_foreign_gpu_worker_is_never_stopped(self):
        with patch('benchmarks.runtime.container_info', return_value=None), \
             patch('benchmarks.runtime.gpu_workers', return_value=['foreign']), \
             patch('benchmarks.runtime.command') as invoked:
            with self.assertRaises(RuntimeError):
                with worker('image', '0', 'dev', True, 'test'):
                    self.fail('Foreign workload must block qualification')
        invoked.assert_not_called()


class ReportingTests(unittest.TestCase):
    def test_rejudging_saved_audio_preserves_original_finish_time(self):
        run = run_fixture()
        run['calls'] = [run['calls'][1]]
        run['calls'][0]['audio'] = 'existing.wav'
        run['cases'] = [{'id': 'en', 'language': 'en', 'lyrics': 'hello world'}]
        run['finished_utc'] = '2026-11-01T16:02:18+00:00'
        run['timing'] = {'total_seconds': 138}
        expected = deepcopy(run['timing'])
        info = {'duration_seconds': 30, 'silent_window_fraction': 0, 'clipping_fraction': 0}
        with tempfile.TemporaryDirectory() as temporary, \
             patch('benchmarks.run.asr_inventory', return_value={'model': 'test-asr'}), \
             patch('benchmarks.run.audio_stats', return_value=info), \
             patch('benchmarks.run.subprocess.check_output', return_value=b'mono'), \
             patch('benchmarks.run.transcribe', return_value=({'text': 'hello world'}, .2)), \
             patch('benchmarks.run.generate_call', side_effect=AssertionError('Must not regenerate audio')), \
             redirect_stdout(io.StringIO()):
            self.assertTrue(score_run(run, Path(temporary), 'http://judge.invalid'))
        self.assertEqual(run['finished_utc'], '2026-11-01T16:02:18+00:00')
        self.assertEqual(run['timing'], expected)
        self.assertIn('scoring_completed_utc', run)

    def test_cold_calls_do_not_enter_warm_statistics(self):
        summary = summarize(run_fixture())
        self.assertEqual(summary['languages']['en']['pipeline_seconds']['median'], 6)
        self.assertEqual(summary['languages']['en']['repeat_groups_bit_identical'], 1)

    def test_matched_runs_pass_and_speed_memory_quality_regressions_fail(self):
        before, after = run_fixture(), run_fixture()
        self.assertTrue(compare(before, after)['passed'])
        for call in after['calls']:
            if call['phase'] == 'measured':
                call['server']['pipeline_seconds'] = 10
                call['gpu']['peak_delta_mib'] += 512
                call['quality']['lyric_accuracy_percent'] = 50
        result = compare(before, after, score_drop=5)
        self.assertFalse(result['passed'])
        self.assertTrue(any('latency' in reason for reason in result['failures']))
        self.assertTrue(any('VRAM' in reason for reason in result['failures']))
        self.assertTrue(any('fidelity' in reason for reason in result['failures']))

    def test_unmatched_hardware_requests_or_judge_are_rejected(self):
        for field in ('configuration', 'gpu', 'asr', 'models'):
            before, after = run_fixture(), run_fixture()
            target = after if field == 'configuration' else after['environment']
            target[field] = {'changed': True}
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                compare(before, after)

    def test_asr_drop_is_a_review_signal_with_an_optional_calibrated_gate(self):
        before, after = run_fixture(), run_fixture()
        after['calls'][1]['quality']['lyric_accuracy_percent'] = 30
        result = compare(before, after)
        self.assertTrue(result['passed'])
        self.assertTrue(result['review_signals'])
        self.assertFalse(compare(before, after, score_drop=5)['passed'])

    def test_public_reports_omit_private_endpoints_paths_and_gpu_uuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            write_reports(run_fixture(), temporary, public=True)
            body = '\n'.join(path.read_text(encoding='utf-8') for path in Path(temporary).rglob('*') if path.is_file())
            for private in ('private-judge.invalid', 'C:/private', 'GPU-PRIVATE'):
                self.assertNotIn(private, body)
