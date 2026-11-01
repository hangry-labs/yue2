"""English long-music inference benchmark: five songs, warm weights, no ASR."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from .metrics import audio_stats, assessed_status, distribution, integrity_flags, suite_timing, technical_flags, timing_breakdown
from .run import ARTIFACTS, configuration, corpus, digest, generate_call, preflight, request, save
from .runtime import ROOT, GpuSampler, command, gpu_info, worker

FIXTURE = ROOT / 'benchmarks/fixtures/long-music.txt'
GENERATIONS = 5


def prompt(path=FIXTURE):
    source = Path(path).read_text(encoding='utf-8-sig')
    match = re.fullmatch(r'\s*(?:direction|style)\s*=\s*(.*?)\r?\nlyrics\s*=(.*)', source, re.DOTALL)
    if not match or not match[1].strip() or not match[2].strip():
        raise ValueError('Long prompt must contain direction/style = ... followed by lyrics=...')
    return {'id': 'beyond-the-static-en', 'language': 'en', 'language_name': 'English',
            'support': 'upstream-listed', 'seed': 831001, 'style': match[1].strip(), 'lyrics': match[2].strip()}


def long_request(case, index):
    payload = request(case)
    # Preserve the author's Intro/Verse/etc. tags exactly; do not prepend [Verse].
    payload.update(duration=300, lyrics=case['lyrics'], lm_seed=case['seed'] + index, seed=case['seed'] + index)
    return payload


def long_configuration(case, warmup):
    config = configuration([case], GENERATIONS, .1)
    config.update(suite='long_music', fixture_sha256=digest(FIXTURE), target_seconds=300,
                  generation_count=GENERATIONS, warmup=warmup,
                  measured_count=GENERATIONS if warmup == 'short' else GENERATIONS - 1,
                  asr=False, request_profile=[long_request(case, i) for i in range(GENERATIONS)],
                  seed_schedule=[case['seed'] + i for i in range(GENERATIONS)])
    return config


def summarize(run):
    calls = [call for call in run['calls'] if call['phase'] == 'measured']
    duration = sum(call['server']['audio_seconds'] for call in calls)
    elapsed = sum(call['server']['pipeline_seconds'] for call in calls)
    row = {'calls': len(calls), 'judged': 0,
           'pipeline_seconds': distribution(call['server']['pipeline_seconds'] for call in calls),
           'worker_seconds': distribution(call['server']['worker_seconds'] for call in calls),
           'client_seconds': distribution(call['client_seconds'] for call in calls),
           'audio_seconds': distribution(call['server']['audio_seconds'] for call in calls),
           'audio_seconds_per_generation_second': duration / elapsed if elapsed else None,
           'rtf': elapsed / duration if duration else None,
           'peak_device_mib': max(call['gpu']['peak_mib'] for call in calls),
           'peak_delta_mib': max(call['gpu']['peak_delta_mib'] for call in calls),
           'resident_weight_mib': max(call['server']['resident_weight_bytes'] / 2**20 for call in calls),
           'module_loads': sum(call['server']['module_loads'] for call in calls),
           'warnings': sum(bool(technical_flags(call)) for call in calls),
           'duration_warnings': sum(any(flag.startswith('duration_outside_') for flag in technical_flags(call)) for call in calls),
           'audio_integrity_warnings': sum(any(flag in technical_flags(call) for flag in
               ('mostly_silent_audio', 'clipping_above_0_1_percent')) for call in calls),
           'repeat_groups': 0, 'repeat_groups_bit_identical': 0}
    return {'schema': 1, 'suite': 'long_music', 'run_id': run['run_id'], 'status': assessed_status(run),
            'timing': suite_timing(run), 'preliminary': False, 'image_id': run['environment']['image_id'],
            'revision': run['environment']['image_revision'], 'gpu': run['environment']['gpu']['name'],
            'asr_enabled': False, 'languages': {'en': row},
            'resident_growth_mib': float(run['final_idle']['memory.used']) - float(run['warm_idle']['memory.used'])}


def write_reports(run, folder, public=False):
    from .reports import number
    summary = summarize(run)
    row, timing = summary['languages']['en'], summary['timing']
    body = ('# Long-music inference benchmark\n\n'
        f'Run `{run["run_id"]}`, revision `{summary["revision"]}`, {summary["gpu"]}. '
        f'Image `{summary["image_id"]}`. Assessment: **{summary["status"]}**.\n\n'
        'English, original [long prompt](../fixtures/long-music.txt), 300-second duration ceiling, '
        'eight steps and normal 24576 context. Models remain resident; every timed call requires zero '
        'weight loads. This suite makes **no ASR requests** and produces no lyric-quality score.\n\n'
        f'Warmup mode: `{run["configuration"]["warmup"]}`. '
        f'{row["calls"]} warm measured long songs. The first long request after a short warmup can '
        'include allocation/graph setup for the longer shapes; these costs remain in its timing. '
        'Duration is a ceiling; actual output lengths are measured rather than padded or stretched.\n\n'
        '| Seed | Audio s | Pipeline s | Worker s | Client s | Audio s / generation s | Device peak MiB | Loads |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n')
    for call in run['calls']:
        if call['phase'] != 'measured':
            continue
        metrics = call['server']
        body += (f'| {call["seed"]} | {metrics["audio_seconds"]:.2f} | {metrics["pipeline_seconds"]:.2f} | '
                 f'{metrics["worker_seconds"]:.2f} | {call["client_seconds"]:.2f} | '
                 f'{metrics["audio_seconds"] / metrics["pipeline_seconds"]:.2f} | '
                 f'{call["gpu"]["peak_mib"]:.0f} | {metrics["module_loads"]} |\n')
    body += ('\n| Summary | Result |\n| --- | --- |\n'
        f'| Pipeline median / p95 | {number(row["pipeline_seconds"]["median"])} / {number(row["pipeline_seconds"]["p95"])} s |\n'
        f'| Worker median / client median | {number(row["worker_seconds"]["median"])} / {number(row["client_seconds"]["median"])} s |\n'
        f'| Aggregate audio s / generation s | {number(row["audio_seconds_per_generation_second"])} |\n'
        f'| Sampled device peak / peak above idle | {number(row["peak_device_mib"], 0)} / {number(row["peak_delta_mib"], 0)} MiB |\n'
        f'| Retained weight buffers | {number(row["resident_weight_mib"], 0)} MiB |\n'
        f'| Total suite wall time | {number(timing["total_seconds"])} s |\n'
        f'| Cold/warmup requests | {number(timing["warmup_requests_seconds"])} s |\n'
        f'| Measured client requests | {number(timing["measured_requests_seconds"])} s |\n'
        f'| Other setup/cleanup/audio analysis | {number(timing["other_seconds"])} s |\n\n'
        'Pipeline excludes output encoding/packaging and HTTP transfer. Worker adds encoding/packaging; '
        'client includes the complete download. Sampled nvidia-smi peaks are device-wide lower bounds, '
        'including desktop/driver allocations, not exact process/allocator peaks. Total ends after '
        'audio integrity analysis; report export is excluded.\n\n'
        'Five samples are a controlled local reference, not statistical proof or a before/after speedup claim. '
        'This profile is separate from the [30-second multilingual suite](../README.md).\n')
    for call in run['calls']:
        if technical_flags(call):
            body += f'\nTechnical flags for {call["id"]}: ' + ', '.join(technical_flags(call)) + '.\n'
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if not public:
        (folder / 'prompt.txt').write_bytes(FIXTURE.read_bytes())
        body = body.replace('../fixtures/long-music.txt', 'prompt.txt').replace(
            '[30-second multilingual suite](../README.md)', '30-second multilingual suite in the repository guide')
    (folder / ('BENCHMARKS.md' if public else 'RESULTS.md')).write_text(body, encoding='utf-8', newline='\n')
    save(folder / ('BASELINE.json' if public else 'summary.json'), summary)


def execute(args):
    started = time.perf_counter()
    case = prompt()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    folder = ARTIFACTS / 'long-music' / run_id
    run = {'schema': 1, 'suite': 'long_music', 'run_id': run_id, 'status': 'running', 'preliminary': False,
           'started_utc': datetime.now(timezone.utc).isoformat(), 'cases': [case], 'languages': ['en'],
           'configuration': long_configuration(case, args.warmup), 'calls': []}
    save(folder / 'run.json', run)
    try:
        run['environment'] = preflight(args, [case], use_asr=False)
        with GpuSampler(args.gpu, .1) as sampler:
            with worker(run['environment']['image_id'], args.gpu, args.dev_container, args.pause_dev, run_id) as instance:
                run['worker'] = {key: value for key, value in instance.items() if key != 'url'}
                if instance['props'].get('context') != 24576:
                    raise ValueError('Long benchmark requires normal context24576')
                run['dependency'] = json.loads(command(['docker', 'exec', instance['id'], 'cat', '/opt/yue/licenses/yue2-ggml.json']))
                try:
                    if args.warmup == 'short':
                        warmup_case = corpus('en')[0]
                        print('Running one excluded 30-second warmup before five measured long songs.', flush=True)
                        run['calls'].append(generate_call(instance, sampler, warmup_case, 'cold', 0, 0, folder))
                    else:
                        print('Exactly five long generations: first cold, followed by four warm measurements.', flush=True)
                    for index in range(GENERATIONS):
                        phase = 'cold' if args.warmup == 'first' and index == 0 else 'measured'
                        if index == 0 and args.warmup == 'short':
                            run['warm_idle'] = gpu_info(args.gpu)
                        print(f'Starting long generation {index + 1}/{GENERATIONS}, seed {case["seed"] + index}.', flush=True)
                        run['calls'].append(generate_call(instance, sampler, case, phase, index, index, folder,
                            payload=long_request(case, index), timeout=900))
                        if index == 0 and args.warmup == 'first':
                            run['warm_idle'] = gpu_info(args.gpu)
                        save(folder / 'run.json', run)
                    run['final_idle'] = gpu_info(args.gpu)
                finally:
                    (folder / 'worker.log').write_text(command(['docker', 'logs', instance['id']],
                        stderr=subprocess.STDOUT), encoding='utf-8', newline='\n')
            run['gpu_samples'] = sampler.samples
        for call in run['calls']:
            if call['phase'] == 'measured':
                info = audio_stats(folder / call['audio'])
                if abs(info['duration_seconds'] - call['server']['audio_seconds']) > .01:
                    raise ValueError('Audio length and native timing metadata disagree')
                call['audio_metrics'] = info
                call['warnings'] = integrity_flags(info, 250, 301)
        run['status'] = 'complete_with_warnings' if any(technical_flags(c) for c in run['calls']) else 'complete'
        if long_configuration(case, args.warmup) != run['configuration']:
            raise ValueError('Long benchmark sources changed during execution')
        run['finished_utc'] = datetime.now(timezone.utc).isoformat()
        run['timing'] = timing_breakdown(run, time.perf_counter() - started)
        run['timing']['scope'] = 'suite start through audio integrity analysis; report export excluded'
        save(folder / 'run.json', run)
        write_reports(run, folder)
        write_reports(run, ROOT / 'benchmarks/long-music', public=True)
        print(f'Long benchmark complete: {run["timing"]["total_seconds"]:.1f}s total. Evidence: {folder}', flush=True)
        return 0
    except BaseException as error:
        run.update(status='failed', error=str(error), finished_utc=datetime.now(timezone.utc).isoformat())
        save(folder / 'run.json', run)
        print('Failed run evidence: ' + str(folder), flush=True)
        raise


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'preflight', 'run'))
    parser.add_argument('--image', default=os.environ.get('YUE2_TASK_IMAGE', 'yue2:dev'))
    parser.add_argument('--gpu', default='0')
    parser.add_argument('--dev-container', default=os.environ.get('YUE2_TASK_CONTAINER', 'yue2-dev'))
    parser.add_argument('--pause-dev', action='store_true')
    parser.add_argument('--warmup', choices=('short', 'first'), default='short',
                        help='short: 30s warmup + five measured long songs; first: five total, first cold')
    args = parser.parse_args()
    try:
        case = prompt()
        if args.command == 'plan':
            print(json.dumps(long_configuration(case, args.warmup), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'preflight':
            print(json.dumps(preflight(args, [case], use_asr=False), indent=2))
            return 0
        return execute(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Long benchmark failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
