"""Matched two-minute acoustic-variation benchmark; one GPU request at a time."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from .metrics import audio_stats, distribution, integrity_flags, lyric_score, verify_warm
from .run import ARTIFACTS, configuration, digest, preflight, request, save
from .runtime import (ROOT, GpuSampler, asr_inventory, command, gpu_info,
                      paused_development_server, synth_many, transcribe, worker)

FIXTURE = ROOT / 'benchmarks/fixtures/variations-en.json'


def fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def reference(lyrics):
    # Section labels structure the music; they are not words to transcribe.
    return '\n'.join(line for line in lyrics.splitlines() if not re.fullmatch(r'\s*\[[^\]]+\]\s*', line)).strip()


def variation_request(case, count, index):
    if count not in range(1, 10):
        raise ValueError('Choose between one and nine acoustic variations')
    payload = request(case)
    payload.update(duration=120, lyrics=case['lyrics'], synth_batch_size=count,
                   lm_seed=case['seed'] + index, seed=case['seed'] + index)
    return payload


def settings(case, counts, repeats):
    if repeats < 1 or len(set(counts)) != len(counts) or 1 not in counts:
        raise ValueError('Require distinct variation counts including one, and at least one repeat')
    config = configuration([case], repeats, .1)
    config.update(suite='acoustic_variations', target_seconds=120, minimum_seconds=100,
                  fixture_sha256=digest(FIXTURE), variations=counts, asr=True,
                  warmup='one full 120-second request per variation count, excluded',
                  worker_isolation='fresh worker per variation count; resident weights',
                  request_profile=[variation_request(case, count, i) for count in counts for i in range(repeats)],
                  seed_schedule=[case['seed'] + i for i in range(repeats)])
    return config


def generate(instance, sampler, case, count, phase, index, folder):
    identity = f'm{count}-{phase}-{index:02d}'
    payload = variation_request(case, count, index)
    save(folder / (identity + '.request.json'), payload)
    started = time.perf_counter()
    measurement, outputs = synth_many(instance['url'], payload)
    ended = time.perf_counter()
    if len(outputs) != count:
        raise ValueError(f'Expected {count} tracks; received {len(outputs)}')
    metrics = measurement['server']
    if phase == 'measured':
        verify_warm(metrics)
    elif metrics.get('schema') != 1 or not metrics.get('keep_loaded'):
        raise ValueError('Worker lacks resident benchmark metrics')
    tracks = []
    for index, (audio, replay, latent) in enumerate(outputs):
        if replay.get('lyrics') != payload['lyrics'] or not replay.get('abc') or not replay.get('semantic_tokens'):
            raise ValueError('Replay lost supplied lyrics, score or generated semantic tokens')
        if replay.get('lm_seed') != payload['lm_seed'] or replay.get('seed') != payload['seed'] + index:
            raise ValueError('Replay variation seeds do not match the request')
        stem = identity + f'-v{index + 1}'
        (folder / (stem + '.wav')).write_bytes(audio)
        (folder / (stem + '.vae')).write_bytes(latent)
        save(folder / (stem + '.replay.json'), replay)
        tracks.append({'id': stem, 'audio': stem + '.wav', 'replay': stem + '.replay.json',
                       'audio_sha256': hashlib.sha256(audio).hexdigest(), 'seed': replay['seed'],
                       'abc_sha256': hashlib.sha256(replay.get('abc', '').encode()).hexdigest(),
                       'semantic_sha256': hashlib.sha256(json.dumps(replay['semantic_tokens']).encode()).hexdigest()})
    if len({(t['abc_sha256'], t['semantic_sha256']) for t in tracks}) != 1:
        raise ValueError('Acoustic variations did not share composition and semantic tokens')
    gpu = sampler.window(started, ended)
    gpu['peak_delta_mib'] = max(0, gpu['peak_mib'] - float(instance['idle_gpu']['memory.used']))
    call = {'id': identity, 'phase': phase, 'variation_count': count, 'seed': payload['seed'],
            'tracks': tracks, 'gpu': gpu, **measurement}
    print(f'{identity}: {count} tracks, {metrics["pipeline_seconds"]:.2f}s pipeline, '
          f'{gpu["peak_mib"]:.0f} MiB device peak, {metrics["module_loads"]} loads', flush=True)
    return call


def validate_audio(run, folder):
    for call in run['calls']:
        total = 0
        for track in call['tracks']:
            info = audio_stats(folder / track['audio'])
            track['audio_metrics'] = info
            track['warnings'] = integrity_flags(info, 100, 121)
            total += info['duration_seconds']
        if abs(total - call['server']['audio_seconds']) > .01:
            raise ValueError('Native total audio duration disagrees with decoded tracks')
    groups = {}
    for call in run['calls']:
        if call['phase'] != 'measured':
            continue
        groups.setdefault(call['seed'], set()).add((call['tracks'][0]['abc_sha256'], call['tracks'][0]['semantic_sha256']))
    run['matched_conditioning'] = all(len(values) == 1 for values in groups.values())
    if not run['matched_conditioning']:
        raise ValueError('Matched seeds produced different compositions or semantic streams across batch sizes')


def score(run, folder, base):
    judge = asr_inventory(base)
    if judge['model'] != run['environment']['asr']['model']:
        raise ValueError('ASR model changed since preflight')
    expected = reference(run['case']['lyrics'])
    for call in run['calls']:
        if call['phase'] != 'measured':
            continue
        for track in call['tracks']:
            try:
                mono = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(folder / track['audio']),
                    '-ac', '1', '-ar', '16000', '-f', 'wav', '-acodec', 'pcm_s16le', 'pipe:1'])
                transcript, elapsed = transcribe(base, judge['model'], mono, 'en')
                track['quality'] = lyric_score(expected, transcript['text'], 'en')
                track['quality'].update(asr_seconds=elapsed, response=transcript)
                track.pop('asr_error', None)
                print(f'{track["id"]}: {track["quality"]["lyric_accuracy_percent"]:.1f}% ASR match', flush=True)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                track['asr_error'] = str(error)
            save(folder / 'run.json', run)
    errors = any(t.get('asr_error') for c in run['calls'] for t in c['tracks'])
    warnings = any(t.get('warnings') for c in run['calls'] if c['phase'] == 'measured' for t in c['tracks'])
    run['status'] = 'failed' if errors else 'complete_with_warnings' if warnings else 'complete'
    run['scoring_completed_utc'] = datetime.now(timezone.utc).isoformat()
    save(folder / 'run.json', run)
    return not errors


def summarize(run):
    groups = {}
    for count in run['configuration']['variations']:
        calls = [c for c in run['calls'] if c['phase'] == 'measured' and c['variation_count'] == count]
        tracks = [t for c in calls for t in c['tracks']]
        elapsed = sum(c['server']['pipeline_seconds'] for c in calls)
        audio = sum(t['audio_metrics']['duration_seconds'] for t in tracks)
        groups[str(count)] = {'requests': len(calls), 'tracks': len(tracks),
            'pipeline_seconds': distribution(c['server']['pipeline_seconds'] for c in calls),
            'worker_seconds': distribution(c['server']['worker_seconds'] for c in calls),
            'client_seconds': distribution(c['client_seconds'] for c in calls),
            'seconds_per_track': elapsed / len(tracks) if tracks else None,
            'audio_seconds_per_generation_second': audio / elapsed if elapsed else None,
            'peak_device_mib': max((c['gpu']['peak_mib'] for c in calls), default=None),
            'peak_delta_mib': max((c['gpu']['peak_delta_mib'] for c in calls), default=None),
            'resident_weights_mib': max((c['server']['resident_weight_bytes'] / 2**20 for c in calls), default=None),
            'module_loads': sum(c['server']['module_loads'] for c in calls),
            'asr_match': distribution(t['quality']['lyric_accuracy_percent'] for t in tracks if t.get('quality')),
            'warnings': sum(bool(t.get('warnings')) for t in tracks),
            'asr_errors': sum(bool(t.get('asr_error')) for t in tracks)}
        info = next((w for w in run.get('workers', []) if w['variation_count'] == count), None)
        if info and 'final_idle' in info:
            groups[str(count)]['retained_growth_mib'] = float(info['final_idle']['memory.used']) - float(info['warm_idle']['memory.used'])
    return {'schema': 1, 'suite': 'acoustic_variations', 'run_id': run['run_id'], 'status': run['status'],
            'image_id': run['environment']['image_id'], 'revision': run['environment']['image_revision'],
            'gpu': run['environment']['gpu']['name'], 'asr_model': run['environment']['asr']['model'],
            'matched_conditioning': run.get('matched_conditioning'), 'timing': run.get('timing'), 'groups': groups}


def write_reports(run, folder):
    summary = summarize(run)
    save(folder / 'BASELINE.json', summary)
    body = ('# Two-minute acoustic variations\n\n'
        f'Run `{run["run_id"]}`; image `{summary["image_id"]}`; revision `{summary["revision"]}`. '
        f'{summary["gpu"]}. Status: **{summary["status"]}**.\n\n'
        'English, 120-second ceiling, eight steps, context 24576. Each variation count gets a fresh '
        'isolated worker and one excluded full-length warmup. Measured requests must load zero weight '
        'modules. The same seeds, lyrics, score and semantic stream are compared across counts. '
        'GPU requests remain serial; acoustic variations solve together inside each request.\n\n'
        '| Variations | Requests / tracks | Median pipeline s | Pipeline s / track | Audio s / generation s | Device peak MiB | Peak above idle MiB | Median ASR match |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n')
    for count, row in summary['groups'].items():
        match = row['asr_match']['median']
        body += (f'| {count} | {row["requests"]} / {row["tracks"]} | {row["pipeline_seconds"]["median"]:.2f} | '
                 f'{row["seconds_per_track"]:.2f} | {row["audio_seconds_per_generation_second"]:.2f} | '
                 f'{row["peak_device_mib"]:.0f} | {row["peak_delta_mib"]:.0f} | '
                 + (f'{match:.1f}%' if match is not None else 'unavailable') + ' |\n')
    body += ('\nDevice memory is sampled every 100 ms and includes desktop/driver allocations; '
        'sampled peaks are lower bounds, not per-process allocator measurements. Warmup and ASR are '
        'excluded from pipeline timing. Models stay resident; normal Studio eviction is unchanged.\n\n'
        'Each complete rendition is sent to the remote ASR judge after GPU generation. Reference lyrics '
        'are never sent as a prompt. ASR match is comparative evidence, not a music-quality grade or '
        'an absolute pass/fail threshold. Duration is a ceiling; tracks shorter than 100 seconds are '
        'flagged, never padded. Batching need not reproduce single-track waveform bytes.\n\n'
        '| Seed | Variations | Track seconds | Pipeline s | Device peak MiB |\n'
        '| --- | --- | --- | --- | --- |\n')
    for call in run['calls']:
        if call['phase'] == 'measured':
            lengths = ', '.join(f'{t["audio_metrics"]["duration_seconds"]:.2f}' for t in call['tracks'])
            body += f'| {call["seed"]} | {call["variation_count"]} | {lengths} | {call["server"]["pipeline_seconds"]:.2f} | {call["gpu"]["peak_mib"]:.0f} |\n'
    body += '\n| Track | ASR match | Technical flags |\n| --- | --- | --- |\n'
    for call in run['calls']:
        if call['phase'] == 'measured':
            for track in call['tracks']:
                quality = track.get('quality')
                match = f'{quality["lyric_accuracy_percent"]:.1f}%' if quality else 'ASR error'
                body += f'| {track["id"]} | {match} | {", ".join(track.get("warnings", [])) or "none"} |\n'
    if run.get('timing'):
        body += f'\nTotal suite wall time: {run["timing"]["total_seconds"]:.2f} seconds, including setup, warmups, audio checks and ASR.\n'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'BENCHMARKS.md').write_text(body, encoding='utf-8', newline='\n')


def execute(args, case):
    started = time.perf_counter()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    folder = ARTIFACTS / 'variations' / run_id
    config = settings(case, args.variations, args.repeats)
    run = {'schema': 1, 'suite': 'acoustic_variations', 'run_id': run_id, 'status': 'running',
           'configuration': config, 'case': case, 'calls': [], 'workers': [],
           'started_utc': datetime.now(timezone.utc).isoformat()}
    save(folder / 'run.json', run)
    try:
        run['environment'] = preflight(args, [case])
        with paused_development_server(args.dev_container, args.pause_dev), GpuSampler(args.gpu, .1) as sampler:
            for count in args.variations:
                with worker(run['environment']['image_id'], args.gpu, args.dev_container, False,
                            run_id + f'-m{count}') as instance:
                    info = {k: v for k, v in instance.items() if k != 'url'}
                    info['variation_count'] = count
                    info['dependency'] = json.loads(command(['docker', 'exec', instance['id'], 'cat', '/opt/yue/licenses/yue2-ggml.json']))
                    run['workers'].append(info)
                    maximum = instance['props'].get('limits', {}).get('synth_batch_size_max')
                    if maximum is not None and max(args.variations) > maximum:
                        raise ValueError(f'Selected image supports at most {maximum} variations. '
                            'Use the retained pre-cap qualification image to reproduce the historical four-variation test.')
                    if instance['props'].get('context') != 24576:
                        raise ValueError('Variation suite requires normal context 24576')
                    try:
                        run['calls'].append(generate(instance, sampler, case, count, 'warmup', 99, folder))
                        info['warm_idle'] = gpu_info(args.gpu)
                        for index in range(args.repeats):
                            run['calls'].append(generate(instance, sampler, case, count, 'measured', index, folder))
                            save(folder / 'run.json', run)
                        info['final_idle'] = gpu_info(args.gpu)
                    finally:
                        (folder / f'worker-m{count}.log').write_text(command(['docker', 'logs', instance['id']],
                            stderr=subprocess.STDOUT), encoding='utf-8', newline='\n')
            run['gpu_samples'] = sampler.samples
        validate_audio(run, folder)
        success = score(run, folder, args.asr_url)
        if settings(case, args.variations, args.repeats) != config:
            raise ValueError('Benchmark inputs changed during execution')
        run['timing'] = {'total_seconds': time.perf_counter() - started,
            'scope': 'setup through generation, cleanup, audio analysis and ASR; report export excluded',
            'warmup_client_seconds': sum(c['client_seconds'] for c in run['calls'] if c['phase'] == 'warmup'),
            'measured_client_seconds': sum(c['client_seconds'] for c in run['calls'] if c['phase'] == 'measured'),
            'asr_seconds': sum(t.get('quality', {}).get('asr_seconds', 0) for c in run['calls'] for t in c['tracks'])}
        run['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save(folder / 'run.json', run)
        write_reports(run, folder)
        if args.write_reports and success:
            write_reports(run, ROOT / 'benchmarks/variations')
        print(f'Evidence: {folder}; total {run["timing"]["total_seconds"]:.2f}s', flush=True)
        return 0 if success else 1
    except BaseException as error:
        run.update(status='failed', error=str(error), finished_utc=datetime.now(timezone.utc).isoformat())
        if 'sampler' in locals():
            run['gpu_samples'] = sampler.samples
        save(folder / 'run.json', run)
        print('Failed-run evidence: ' + str(folder), flush=True)
        raise


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'preflight', 'run', 'score'))
    parser.add_argument('--image', default=os.environ.get('YUE2_TASK_IMAGE', 'yue2:dev'))
    parser.add_argument('--gpu', default='0')
    parser.add_argument('--dev-container', default=os.environ.get('YUE2_TASK_CONTAINER', 'yue2-dev'))
    parser.add_argument('--pause-dev', action='store_true')
    parser.add_argument('--asr-url', default=os.environ.get('YUE2_BENCHMARK_ASR_URL', os.environ.get('YUE2_ASR_URL', '')))
    parser.add_argument('--variations', type=lambda s: [int(v) for v in s.split(',')], default=[1, 2])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--write-reports', action='store_true')
    args = parser.parse_args()
    try:
        case = fixture()
        config = settings(case, args.variations, args.repeats)
        if args.command == 'plan':
            print(json.dumps(config, indent=2))
            return 0
        if args.command == 'preflight':
            print(json.dumps(preflight(args, [case]), indent=2))
            return 0
        if args.command == 'score':
            if not args.run:
                raise ValueError('Specify --run path/to/run.json')
            run = json.loads(args.run.read_text(encoding='utf-8'))
            if run.get('suite') != 'acoustic_variations':
                raise ValueError('Choose an acoustic-variations run')
            success = score(run, args.run.parent, args.asr_url)
            write_reports(run, args.run.parent)
            if args.write_reports and success:
                write_reports(run, ROOT / 'benchmarks/variations')
            return 0 if success else 1
        return execute(args, case)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Variation benchmark failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
