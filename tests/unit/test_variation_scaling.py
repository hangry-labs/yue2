"""Offline scaling analysis must use measured jobs, matched seeds and all decodes."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_variation_scaling import analyze, stages


def log(job, count):
    return (f'[Server] Job {job}: queued synth\n[Server] Job {job}: {{}}\n'
            '[AR] Score: 100 tokens over 1 songs, 100 steps, 4.0 s\n'
            '[AR] Semantic: 3000 tokens over 1 songs, 3000 steps, 9.0 s\n'
            f'[NAR] Song 0 chunk 1/1: 3000 frames, cache 4000 rows, 0 forwarded, {6 if count == 1 else 11}.0 s\n'
            + '[VAE] Tiled decode done: 6 tiles -> T_audio=5760000 (120.00s @ 48kHz), 1000 ms\n' * count
            + f'[Server] Job {job}: done\n')


class ScalingAnalysisTests(unittest.TestCase):
    def fixture(self, folder):
        run = {'suite': 'acoustic_variations', 'status': 'complete', 'run_id': 'test',
               'configuration': {'variations': [1, 2]}, 'matched_conditioning': True,
               'environment': {'image_id': 'same-image', 'gpu': {'name': 'test GPU'}},
               'timing': {'total_seconds': 100}, 'calls': []}
        for count in (1, 2):
            logs = ''
            for seed in (10, 11):
                job = f'{count}{seed:x}'
                logs += log(job, count)
                run['calls'].append({'id': job, 'job_id': job, 'phase': 'measured', 'seed': seed,
                    'variation_count': count, 'server': {'module_loads': 0,
                        'pipeline_seconds': 20 if count == 1 else 26},
                    'gpu': {'peak_mib': 1000 + count * 100, 'peak_delta_mib': 500 + count * 100},
                    'tracks': [{'audio_sha256': str(i), 'quality': {'lyric_accuracy_percent': 80}}
                               for i in range(count)]})
            (folder / f'worker-m{count}.log').write_text(logs, encoding='utf-8')
        return run

    def test_repeated_job_markers_do_not_erase_the_timings(self):
        row = stages(log('aa', 2))['aa']
        self.assertEqual(row['score_seconds'], 4)
        self.assertEqual(row['semantic_seconds'], 9)
        self.assertEqual(row['nar_seconds'], 11)
        self.assertEqual(row['vae_seconds'], 2)
        self.assertEqual(row['decoded_tracks'], 2)

    def test_aggregate_throughput_and_incremental_cost_count_all_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            run = self.fixture(folder)
            before = json.dumps(run, sort_keys=True)
            result = analyze(run, folder)
            one, two = result['groups']
            self.assertEqual(one['mean_seconds_per_track'], 20)
            self.assertEqual(two['mean_seconds_per_track'], 13)
            self.assertAlmostEqual(two['throughput_vs_single'], 20 / 13)
            self.assertEqual(two['extra_batch_seconds_per_added_track'], 6)
            self.assertEqual(two['tracks'], 4)
            self.assertEqual(two['unattributed_seconds'], 0)
            self.assertEqual(json.dumps(run, sort_keys=True), before)

    def test_partial_decode_logs_and_unmatched_seeds_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            run = self.fixture(folder)
            path = folder / 'worker-m2.log'
            path.write_text(log('2a', 1) + log('2b', 2), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Missing stage/track'):
                analyze(run, folder)
            run = self.fixture(folder)
            run['calls'][-1]['seed'] = 999
            with self.assertRaisesRegex(ValueError, 'seed schedule'):
                analyze(run, folder)
