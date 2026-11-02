"""Batch accounting, matching and ASR must cover every complete rendition."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.runtime import batch_parts, paused_development_server
from benchmarks.variations import fixture, reference, score, settings, summarize, variation_request, validate_audio


class VariationBenchmarkTests(unittest.TestCase):
    @patch('benchmarks.runtime.command')
    @patch('benchmarks.runtime.require_idle_dev')
    @patch('benchmarks.runtime.container_info', return_value={'Id': 'exact-dev', 'State': {'Running': True}})
    def test_one_pause_restores_exact_dev_even_when_later_worker_fails(self, info, idle, command):
        with self.assertRaisesRegex(RuntimeError, 'second worker'):
            with paused_development_server('dev', True):
                self.assertEqual(command.call_args.args[0], ['docker', 'stop', 'exact-dev'])
                raise RuntimeError('second worker failed')
        self.assertEqual([call.args[0] for call in command.call_args_list],
                         [['docker', 'stop', 'exact-dev'], ['docker', 'start', 'exact-dev']])
        idle.assert_called_once()

    def test_full_length_fresh_matched_requests(self):
        case = fixture()
        single, batch = [variation_request(case, n, 1) for n in (1, 2)]
        self.assertEqual(single['duration'], 120)
        self.assertEqual(single['lyrics'], case['lyrics'])
        self.assertNotIn('abc', single)
        self.assertNotIn('semantic_tokens', single)
        self.assertEqual({**single, 'synth_batch_size': 2}, batch)
        self.assertEqual(single['lm_batch_size'], 1)
        self.assertEqual(single['steps'], 8)
        self.assertNotIn('[Chorus]', reference(case['lyrics']))
        self.assertIn('Keep a lantern', reference(case['lyrics']))

    def test_counts_and_repeats_are_explicit(self):
        for counts, repeats in [([2], 3), ([1, 1], 3), ([1, 0], 3), ([1, 10], 3), ([1, 2], 0)]:
            with self.subTest(counts=counts, repeats=repeats), self.assertRaises(ValueError):
                settings(fixture(), counts, repeats)
        config = settings(fixture(), [1, 2], 3)
        self.assertEqual(len(config['request_profile']), 6)
        self.assertTrue(config['asr'])
        self.assertEqual(config['context'], 24576)

    def test_native_multipart_keeps_replay_audio_latents_paired(self):
        body = b''
        for index in range(2):
            for mime, data in [('application/json', json.dumps({'seed': index}).encode()),
                               ('audio/wav', b'WAV' + bytes([index])),
                               ('application/octet-stream', b'latent' + bytes([index]))]:
                body += b'--test\r\nContent-Type: ' + mime.encode() + b'\r\n\r\n' + data + b'\r\n'
        body += b'--test--\r\n'
        tracks = batch_parts('multipart/mixed; boundary=test', body)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[1], (b'WAV\x01', {'seed': 1}, b'latent\x01'))
        with self.assertRaises(ValueError):
            batch_parts('multipart/mixed; boundary=test', body.replace(b'application/octet-stream', b'text/plain'))

    def run_fixture(self):
        metric = {'pipeline_seconds': 10, 'worker_seconds': 11, 'audio_seconds': 240,
                  'resident_weight_bytes': 2**20, 'module_loads': 0}
        call = {'id': 'm2', 'phase': 'measured', 'variation_count': 2, 'seed': 12,
                'server': metric, 'client_seconds': 12, 'gpu': {'peak_mib': 100, 'peak_delta_mib': 50},
                'tracks': [{'id': f'v{i}', 'audio': f'v{i}.wav', 'abc_sha256': 'abc',
                            'semantic_sha256': 'codes', 'warnings': []} for i in range(2)]}
        return {'run_id': 'test', 'status': 'running', 'configuration': {'variations': [2]},
                'case': fixture(), 'environment': {'asr': {'model': 'judge'}, 'image_id': 'test',
                    'image_revision': 'test', 'gpu': {'name': 'test'}}, 'calls': [call]}

    @patch('benchmarks.variations.transcribe', return_value=({'text': 'Keep a lantern by the road'}, .5))
    @patch('benchmarks.variations.subprocess.check_output', return_value=b'full song')
    @patch('benchmarks.variations.asr_inventory', return_value={'model': 'judge'})
    def test_every_track_is_judged_and_failures_can_be_rescored(self, inventory, ffmpeg, transcribe):
        run = self.run_fixture()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.assertTrue(score(run, folder, 'http://judge'))
            self.assertEqual(transcribe.call_count, 2)
            self.assertTrue(all('-t' not in args.args[0] for args in ffmpeg.call_args_list))
            transcribe.side_effect = OSError('judge unavailable')
            self.assertFalse(score(run, folder, 'http://judge'))
            self.assertEqual(run['status'], 'failed')
            transcribe.side_effect = None
            self.assertTrue(score(run, folder, 'http://judge'))
            self.assertTrue(all('asr_error' not in t for t in run['calls'][0]['tracks']))

    @patch('benchmarks.variations.audio_stats', return_value={'duration_seconds': 120, 'rms': .1,
            'clipping_fraction': 0, 'silent_fraction': 0, 'peak': .5})
    @patch('benchmarks.variations.integrity_flags', return_value=[])
    def test_duration_accounting_and_conditioning_are_verified(self, flags, stats):
        run = self.run_fixture()
        validate_audio(run, Path('.'))
        self.assertTrue(run['matched_conditioning'])
        row = summarize(run)['groups']['2']
        self.assertEqual(row['seconds_per_track'], 5)
        self.assertEqual(row['audio_seconds_per_generation_second'], 24)
        other = deepcopy(run['calls'][0])
        other['tracks'][0]['semantic_sha256'] = 'different'
        run['calls'].append(other)
        with self.assertRaisesRegex(ValueError, 'different compositions'):
            validate_audio(run, Path('.'))
