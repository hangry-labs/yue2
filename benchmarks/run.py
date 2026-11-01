"""Manual, model-resident generation/VRAM/lyric benchmark. No third-party Python packages."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from .metrics import audio_stats, integrity_flags, lyric_score, suite_timing, timing_breakdown, verify_warm
from .runtime import (ROOT, GpuSampler, asr_inventory, command, gpu_info, gpu_workers,
                      http_json, synth, transcribe, worker)

ARTIFACTS = ROOT / 'data/results/benchmarks'
BASELINE_REPEATS = 10


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def corpus(languages=None):
    result = json.loads((ROOT / 'benchmarks/corpus.json').read_text(encoding='utf-8'))['cases']
    selected = (languages or 'en,zh,es,de').split(',')
    if len(selected) != len(set(selected)) or set(selected) - {case['language'] for case in result}:
        raise ValueError('Choose distinct corpus languages: en,zh,es,de')
    return [next(case for case in result if case['language'] == language) for language in selected]


def request(case, round_index=0):
    # Rounds zero and two repeat a seed after intervening languages, detecting
    # cross-request state/carryover. Other rounds use distinct fixed seeds.
    offset = 0 if round_index == 2 else round_index
    return {'style': case['style'], 'lyrics': '[Verse]\n' + case['lyrics'], 'cot': 'full',
            'duration': 30, 'steps': 8, 'lm_seed': case['seed'] + offset, 'seed': case['seed'] + offset,
            'lm_batch_size': 1, 'synth_batch_size': 1, 'output_format': 'wav16', 'cfg_scale': 1.0,
            'peak_clip': 10, 'adapters': [],
            'abc_sampling': {'temperature': .7, 'top_p': .9, 'top_k': 30, 'repetition_penalty': 1.005,
                             'penalty_window': 100, 'min_tokens': 32, 'max_tokens': 4096},
            'semantic_sampling': {'temperature': 1.0, 'top_p': .95, 'top_k': 100, 'repetition_penalty': 1.2,
                                  'penalty_window': 50, 'min_tokens': 200, 'max_tokens': 9000}}


def configuration(cases, repeats, interval):
    sources = sorted((ROOT / 'benchmarks').glob('*.py')) + [ROOT / 'benchmarks/corpus.json']
    harness = hashlib.sha256(b''.join(path.name.encode() + path.read_bytes() for path in sources)).hexdigest()
    return {'schema': 1, 'harness_sha256': harness, 'corpus_sha256': digest(ROOT / 'benchmarks/corpus.json'),
            'cases': [case['id'] for case in cases], 'repeats': repeats, 'gpu_sample_seconds': interval,
            'warmups_per_language': 1, 'keep_loaded': True, 'request_profile': [request(case) for case in cases],
            'context': 24576, 'max_batch': 1, 'vae_core': 512, 'vae_halo': 16,
            'seed_schedule': [0 if i == 2 else i for i in range(repeats)]}


def preflight(args, cases, use_asr=True):
    if not shutil.which('nvidia-smi') or (use_asr and not shutil.which('ffmpeg')):
        raise ValueError('Benchmark requires Docker/nvidia-smi, and FFmpeg for ASR scoring')
    command(['docker', 'version', '--format', '{{.Server.Version}}'])
    image = json.loads(command(['docker', 'image', 'inspect', args.image]))[0]
    models = {}
    for name in ('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf'):
        path = ROOT / 'data/models' / name
        if not path.is_file():
            raise ValueError('Prepare external models first: task models')
        models[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    judge = None
    if use_asr:
        judge = asr_inventory(args.asr_url)
        missing = [case['language_name'] for case in cases if case['language_name'] not in judge['languages']]
        if missing:
            raise ValueError('ASR does not advertise: ' + ', '.join(missing))
    return {'image_id': image['Id'], 'image_revision': (image['Config'].get('Labels') or {}).get(
                'org.opencontainers.image.revision'), 'models': models, 'gpu': gpu_info(args.gpu),
            'other_gpu_containers': gpu_workers(exclude=(args.dev_container,)), 'asr': judge,
            'ffmpeg': command(['ffmpeg', '-version']).splitlines()[0] if shutil.which('ffmpeg') else None}


def generate_call(instance, sampler, case, phase, index, round_index, folder, *, payload=None, timeout=180):
    identity = f'{phase}-{index:02d}-{case["id"]}'
    payload = request(case, round_index) if payload is None else payload
    save(folder / (identity + '.request.json'), payload)
    started = time.perf_counter()
    measurement, audio, replay, latent = synth(instance['url'], payload, timeout=timeout)
    ended = time.perf_counter()
    metrics = measurement['server']
    if phase == 'measured':
        verify_warm(metrics)
    elif metrics.get('schema') != 1 or not metrics.get('keep_loaded'):
        raise ValueError('Build the image with current benchmark metrics support')
    if replay.get('lm_seed') != payload['lm_seed'] or replay.get('seed') != payload['seed']:
        raise ValueError('Replay did not preserve requested seeds')
    if replay.get('lyrics') != payload['lyrics'] or not replay.get('semantic_tokens'):
        raise ValueError('Replay lost lyrics or semantic tokens')
    audio_name = identity + '.wav'
    (folder / audio_name).write_bytes(audio)
    save(folder / (identity + '.replay.json'), replay)
    if latent:
        (folder / (identity + '.vae')).write_bytes(latent)
    gpu = sampler.window(started, ended)
    gpu['peak_delta_mib'] = max(0, gpu['peak_mib'] - float(instance['idle_gpu']['memory.used']))
    result = {'id': identity, 'phase': phase, 'case_id': case['id'], 'language': case['language'],
              'support': case['support'], 'seed': payload['seed'], 'audio': audio_name,
              'audio_sha256': hashlib.sha256(audio).hexdigest(), 'gpu': gpu, **measurement}
    print(f'{identity}: {metrics["audio_seconds"]:.2f}s audio / {metrics["pipeline_seconds"]:.3f}s pipeline, '
          f'{gpu["peak_mib"]:.0f} MiB device peak, {metrics["module_loads"]} loads', flush=True)
    return result


def score_run(run, folder, asr_url):
    if run.get('suite') == 'long_music':
        raise ValueError('Long-music benchmarks do not use ASR scoring')
    cases = {case['id']: case for case in run['cases']}
    judge = asr_inventory(asr_url)
    if judge['model'] != run['environment']['asr']['model']:
        raise ValueError('ASR model changed since benchmark preflight')
    for call in run['calls']:
        if call['phase'] != 'measured':
            continue
        case = cases[call['case_id']]
        try:
            call['audio_metrics'] = audio_stats(folder / call['audio'])
            duration = call['audio_metrics']['duration_seconds']
            if abs(duration - call['server']['audio_seconds']) > .01:
                raise ValueError('Server timing metadata and actual audio length disagree')
            mono = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(folder / call['audio']),
                '-ac', '1', '-ar', '16000', '-f', 'wav', '-acodec', 'pcm_s16le', 'pipe:1'])
            transcript, elapsed = transcribe(asr_url, judge['model'], mono, case['language'])
            call['quality'] = lyric_score(case['lyrics'], transcript['text'], case['language'])
            call['quality'].update(asr_seconds=elapsed, detected_language=transcript.get('language'),
                                   asr_response=transcript)
            call.pop('asr_error', None)
            call['warnings'] = integrity_flags(call['audio_metrics'])
            print(f'{call["id"]}: {call["quality"]["lyric_accuracy_percent"]:.1f}% ASR match '
                  f'({call["quality"]["primary_metric"]}), {duration:.2f}s', flush=True)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            call['asr_error'] = str(error)
            print(f'{call["id"]}: scoring failed: {error}', flush=True)
        save(folder / 'run.json', run)
    errors = [call for call in run['calls'] if call.get('asr_error')]
    run['status'] = 'failed' if errors else ('complete_with_warnings' if any(
        call.get('warnings') for call in run['calls']) else 'complete')
    run['scoring_completed_utc'] = datetime.now(timezone.utc).isoformat()
    save(folder / 'run.json', run)
    return not errors


def execute(args, cases):
    suite_started = time.perf_counter()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    folder = ARTIFACTS / run_id
    run = {'schema': 1, 'run_id': run_id, 'started_utc': datetime.now(timezone.utc).isoformat(),
           'status': 'running', 'languages': [case['language'] for case in cases], 'cases': cases,
           'configuration': configuration(cases, args.repeats, args.sample_interval),
           'preliminary': args.allow_shared_gpu, 'calls': []}
    save(folder / 'run.json', run)
    try:
        run['environment'] = preflight(args, cases)
        save(folder / 'run.json', run)
        with GpuSampler(args.gpu, args.sample_interval) as sampler:
            with worker(run['environment']['image_id'], args.gpu, args.dev_container, args.pause_dev, run_id,
                        args.allow_shared_gpu) as instance:
                run['worker'] = {key: value for key, value in instance.items() if key != 'url'}
                if instance['props'].get('context') != 24576:
                    raise ValueError('Benchmark requires the normal 24576-token context')
                run['dependency'] = json.loads(command(['docker', 'exec', instance['id'], 'cat',
                                                       '/opt/yue/licenses/yue2-ggml.json']))
                for index, case in enumerate(cases):
                    phase = 'cold' if index == 0 else 'warmup'
                    run['calls'].append(generate_call(instance, sampler, case, phase, index, 0, folder))
                    save(folder / 'run.json', run)
                run['warm_idle'] = gpu_info(args.gpu)
                run['measurement_started_utc'] = datetime.now(timezone.utc).isoformat()
                for round_index in range(args.repeats):
                    sequence = cases if round_index % 2 == 0 else list(reversed(cases))
                    for case in sequence:
                        index = sum(call['phase'] == 'measured' for call in run['calls'])
                        run['calls'].append(generate_call(instance, sampler, case, 'measured', index,
                                                         round_index, folder))
                        save(folder / 'run.json', run)
                run['final_idle'] = gpu_info(args.gpu)
                (folder / 'worker.log').write_text(command(['docker', 'logs', instance['id']],
                    stderr=subprocess.STDOUT), encoding='utf-8', newline='\n')
            run['gpu_samples'] = sampler.samples
        # ASR and PCM analysis run after the GPU phase, outside all generation timings.
        success = score_run(run, folder, args.asr_url)
        if configuration(cases, args.repeats, args.sample_interval) != run['configuration']:
            raise ValueError('Benchmark sources changed during execution; preserve this as diagnostic evidence')
        run['finished_utc'] = datetime.now(timezone.utc).isoformat()
        run['timing'] = timing_breakdown(run, time.perf_counter() - suite_started)
        save(folder / 'run.json', run)
    except BaseException as error:
        run.update(status='failed', error=str(error), finished_utc=datetime.now(timezone.utc).isoformat())
        save(folder / 'run.json', run)
        raise
    finally:
        print('Evidence: ' + str(folder), flush=True)
    from .reports import write_reports
    write_reports(run, folder)
    if args.write_reports and success and not args.allow_shared_gpu:
        write_reports(run, ROOT / 'benchmarks', public=True)
    return 0 if success else 1


def main():
    # Task/redirected Windows stdout may otherwise use a legacy code page.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'preflight', 'run', 'score'))
    parser.add_argument('--image', default=os.environ.get('YUE2_TASK_IMAGE', 'yue2:dev'))
    parser.add_argument('--asr-url', default=os.environ.get('YUE2_BENCHMARK_ASR_URL') or os.environ.get('YUE2_ASR_URL', ''))
    parser.add_argument('--gpu', default='0')
    parser.add_argument('--dev-container', default=os.environ.get('YUE2_TASK_CONTAINER', 'yue2-dev'))
    parser.add_argument('--pause-dev', action='store_true')
    parser.add_argument('--languages', default='en,zh,es,de')
    parser.add_argument('--repeats', type=int, default=BASELINE_REPEATS)
    parser.add_argument('--sample-interval', type=float, default=.1)
    parser.add_argument('--allow-shared-gpu', action='store_true')
    parser.add_argument('--write-reports', action='store_true')
    parser.add_argument('--run', type=Path, help='Existing run.json for ASR rescoring without generation')
    args = parser.parse_args()
    if args.repeats < 1 or not .05 <= args.sample_interval <= 1:
        parser.error('Repeats must be positive; sample interval must be between .05 and 1 second')
    if args.allow_shared_gpu and args.write_reports:
        parser.error('Shared-GPU runs cannot update public baseline reports')
    if args.write_reports and (set(args.languages.split(',')) != {'en', 'zh', 'es', 'de'}
                               or args.repeats < BASELINE_REPEATS):
        parser.error('Public baseline reports require all four languages and at least ten repeats')
    try:
        cases = corpus(args.languages)
        if args.command == 'plan':
            print(json.dumps(configuration(cases, args.repeats, args.sample_interval), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'preflight':
            print(json.dumps(preflight(args, cases), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'score':
            if not args.run:
                parser.error('score requires --run path/to/run.json')
            run = json.loads(args.run.read_text(encoding='utf-8'))
            if run.get('error'):
                raise ValueError('Cannot rescore an incomplete GPU run')
            # Rejudging saved audio must not inflate the original benchmark wall time.
            run.setdefault('timing', suite_timing(run))
            success = score_run(run, args.run.parent, args.asr_url)
            from .reports import write_reports
            write_reports(run, args.run.parent)
            return 0 if success else 1
        return execute(args, cases)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Benchmark failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
