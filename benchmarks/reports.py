"""Separate speed, device-memory and ASR-fidelity reports and matched regression gates."""
import argparse
from collections import defaultdict
import html
import json
from pathlib import Path
import statistics
import sys

from .metrics import assessed_status, distribution, suite_timing, technical_flags


def summarize(run):
    if run.get('suite') == 'long_music':
        from .long import summarize as summarize_long
        return summarize_long(run)
    measured = [call for call in run['calls'] if call['phase'] == 'measured']
    result = {'schema': 1, 'run_id': run['run_id'], 'status': assessed_status(run),
              'assessment_policy': 'relative_asr_v2', 'timing': suite_timing(run),
              'preliminary': run['preliminary'], 'image_id': run['environment']['image_id'],
              'revision': run['environment']['image_revision'], 'gpu': run['environment']['gpu']['name'],
              'asr_model': run['environment']['asr']['model'], 'languages': {}}
    for language in run['languages']:
        calls = [call for call in measured if call['language'] == language]
        judged = [call for call in calls if call.get('quality') and not call.get('asr_error')]
        groups = defaultdict(list)
        for call in calls:
            groups[(call['case_id'], call['seed'])].append(call['audio_sha256'])
        repeated = [values for values in groups.values() if len(values) > 1]
        duration = sum(call['server']['audio_seconds'] for call in calls)
        elapsed = sum(call['server']['pipeline_seconds'] for call in calls)
        result['languages'][language] = {
            'calls': len(calls), 'support': calls[0]['support'] if calls else None,
            'pipeline_seconds': distribution(call['server']['pipeline_seconds'] for call in calls),
            'worker_seconds': distribution(call['server']['worker_seconds'] for call in calls),
            'client_seconds': distribution(call['client_seconds'] for call in calls),
            'audio_seconds': distribution(call['server']['audio_seconds'] for call in calls),
            'audio_seconds_per_generation_second': duration / elapsed if elapsed else None,
            'rtf': elapsed / duration if duration else None,
            'peak_device_mib': max((call['gpu']['peak_mib'] for call in calls), default=None),
            'peak_delta_mib': max((call['gpu']['peak_delta_mib'] for call in calls), default=None),
            'resident_weight_mib': max((call['server']['resident_weight_bytes'] / 2**20 for call in calls), default=None),
            'module_loads': sum(call['server']['module_loads'] for call in calls),
            'judged': len(judged),
            'lyric_accuracy_percent': distribution(call['quality']['lyric_accuracy_percent'] for call in judged),
            'mean_wer': statistics.mean(call['quality']['wer']['error_rate'] for call in judged
                                       if call['quality']['wer']) if judged and language != 'zh' else None,
            'mean_cer': statistics.mean(call['quality']['cer']['error_rate'] for call in judged) if judged else None,
            'repeat_groups': len(repeated), 'repeat_groups_bit_identical': sum(len(set(group)) == 1 for group in repeated),
            'warnings': sum(bool(technical_flags(call)) for call in calls),
            'audio_integrity_warnings': sum(any(flag in technical_flags(call) for flag in
                ('mostly_silent_audio', 'clipping_above_0_1_percent')) for call in calls),
            'duration_warnings': sum('duration_outside_25_to_31_seconds' in technical_flags(call) for call in calls)}
    result['resident_growth_mib'] = float(run['final_idle']['memory.used']) - float(run['warm_idle']['memory.used'])
    return result


def number(value, digits=2):
    return 'n/a' if value is None else f'{value:.{digits}f}'


def text(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', '<br>')


def sections(run, summary):
    intro = (f'Run `{run["run_id"]}`, revision `{summary["revision"]}`, {text(summary["gpu"])}. '
             f'Image `{summary["image_id"]}`. {"Preliminary shared-GPU run." if run["preliminary"] else "Isolated inference worker; desktop activity may share the device."}\n\n')
    cold = next(call for call in run['calls'] if call['phase'] == 'cold')
    overview = ('# YuE2 benchmark results\n\n' + intro +
        'Four areas remain distinct: cold startup, warm generation, sampled GPU memory and lyric fidelity. '
        'Model weights stay external and read-only.\n\n'
        f'Assessment status: **{summary["status"]}**. ASR scores are comparative observations without an absolute acceptance cutoff.\n\n'
        '| Suite wall time, through scoring | Seconds |\n| --- | --- |\n'
        f'| Total | {number(summary["timing"]["total_seconds"])} |\n'
        f'| Cold/warmup requests, including downloads | {number(summary["timing"]["warmup_requests_seconds"])} |\n'
        f'| Measured requests, including downloads | {number(summary["timing"]["measured_requests_seconds"])} |\n'
        f'| ASR requests | {number(summary["timing"]["asr_requests_seconds"])} |\n'
        f'| Other setup, cleanup and CPU analysis | {number(summary["timing"]["other_seconds"])} |\n\n'
        'Speed, VRAM and lyric scores use the same measured songs. ASR runs afterward on their saved WAVs; '
        'warmup songs are excluded from lyric scoring. Report export is outside this wall-time scope.\n\n'
        '| Cold phase | Result |\n| --- | --- |\n'
        f'| Worker startup (before first generation) | {run["worker"]["startup_seconds"]:.3f} s |\n'
        f'| First generation, including weight loads | {cold["server"]["pipeline_seconds"]:.3f} s |\n'
        f'| Successful weight-module loads | {cold["server"]["module_loads"]} |\n'
        f'| Cold sampled device peak | {cold["gpu"]["peak_mib"]:.0f} MiB |\n\n'
        'Cold GPU weights do not imply a cold filesystem cache: checksum verification reads model files first.\n\n'
        'See [speed](speed/BENCHMARKS.md), [memory](memory/BENCHMARKS.md), '
        '[lyrics](lyrics/BENCHMARKS.md), and [methodology](README.md).\n')
    speed = ('# Warm generation speed\n\n' + intro +
        'One full warmup per language is excluded. Timed calls require zero weight loads and at least three resident modules. '
        'Pipeline time includes score planning, semantic generation, eight flow-matching steps and VAE decoding; '
        'worker time adds audio encoding/packaging, and client time adds HTTP transfer/polling. ASR is separate.\n\n'
        '| Language | N | Audio median s | Pipeline median s | Pipeline p95 s | Worker median s | Client median s | Audio s / generation s | RTF |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n')
    memory = ('# Sampled GPU memory\n\n' + intro +
        f'Requested device sampling interval: {run["configuration"]["gpu_sample_seconds"]:.3f} s. '
        'These are whole-device nvidia-smi observations, not allocator or per-process peaks. '
        'A sampled peak is a lower bound; display/driver/background allocations remain included. '
        'Delta subtracts the idle device reading after the development server stopped and before the worker started. '
        'Weight buffers come from the compute worker and exclude KV cache, activations and workspaces.\n\n'
        '| Language | Sampled device peak MiB | Peak above idle MiB | Resident weights MiB | Timed module loads |\n'
        '| --- | --- | --- | --- | --- |\n')
    quality = ('# ASR lyric fidelity\n\n' + intro +
        f'Judge: `{summary["asr_model"]}`, full music mix converted to mono 16 kHz. '
        'Expected lyrics are never supplied to ASR as a prompt. Unicode NFKC/case normalization preserves accents; '
        'punctuation is ignored. WER/CER count insertions, substitutions and deletions and may exceed 100%. '
        'Lyric accuracy = max(0, 1 − WER) × 100 for space-delimited languages and CER for Chinese. '
        'The ASR judge is imperfect on music, and an expected acceptance range has not been calibrated. '
        'Scores are reference observations for matched regression review; no absolute score produces a warning. '
        'Spanish/German are experimental model coverage.\n\n'
        '| Language | Judged | Mean WER | Mean CER | Median ASR match % | Minimum % | Identical repeat groups |\n'
        '| --- | --- | --- | --- | --- | --- | --- |\n')
    for language, row in summary['languages'].items():
        speed += (f'| {language} | {row["calls"]} | {number(row["audio_seconds"]["median"])} | '
                  f'{number(row["pipeline_seconds"]["median"])} | {number(row["pipeline_seconds"]["p95"])} | '
                  f'{number(row["worker_seconds"]["median"])} | {number(row["client_seconds"]["median"])} | '
                  f'{number(row["audio_seconds_per_generation_second"])} | {number(row["rtf"], 3)} |\n')
        memory += (f'| {language} | {number(row["peak_device_mib"], 0)} | {number(row["peak_delta_mib"], 0)} | '
                   f'{number(row["resident_weight_mib"], 0)} | {row["module_loads"]} |\n')
        quality += (f'| {language} | {row["judged"]}/{row["calls"]} | {number(row["mean_wer"], 3)} | '
                    f'{number(row["mean_cer"], 3)} | {number(row["lyric_accuracy_percent"]["median"])} | '
                    f'{number(row["lyric_accuracy_percent"]["min"])} | '
                    f'{row["repeat_groups_bit_identical"]}/{row["repeat_groups"]} |\n')
    memory += (f'\nRetained whole-device memory changed by {summary["resident_growth_mib"]:.0f} MiB '
               'from the end of all warmups to the end of measured calls; background changes can affect this value.\n')
    quality += '\n## Transcripts\n\n'
    for call in run['calls']:
        if call['phase'] == 'measured':
            quality += f'**{call["id"]}, seed {call["seed"]}**\n\n'
            quality += text(call.get('quality', {}).get('transcript', call.get('asr_error', 'Not scored'))) + '\n\n'
            if technical_flags(call):
                quality += 'Technical flags: ' + ', '.join(technical_flags(call)) + '.\n\n'
    return overview, speed, memory, quality


def write_reports(run, folder, public=False):
    if run.get('suite') == 'long_music':
        from .long import write_reports as write_long_reports
        return write_long_reports(run, folder, public)
    summary = summarize(run)
    overview, speed, memory, quality = sections(run, summary)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if public:
        if run['preliminary'] or run['status'] not in ('complete', 'complete_with_warnings'):
            raise ValueError('Only a complete dedicated-worker run can update public reports')
        outputs = {'BENCHMARKS.md': overview, 'speed/BENCHMARKS.md': speed,
                   'memory/BENCHMARKS.md': memory, 'lyrics/BENCHMARKS.md': quality}
        # Summary contains no private endpoint, host paths, UUID, raw device processes or audio.
        outputs['BASELINE.json'] = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
    else:
        overview = overview.replace('[methodology](README.md)', 'the repository benchmark methodology')
        outputs = {'RESULTS.md': overview + '\n' + speed + '\n' + memory + '\n' + quality,
                   'speed/BENCHMARKS.md': speed, 'memory/BENCHMARKS.md': memory, 'lyrics/BENCHMARKS.md': quality,
                   'summary.json': json.dumps(summary, ensure_ascii=False, indent=2) + '\n'}
    for name, body in outputs.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8', newline='\n')


def compare(before, after, latency_limit=.15, vram_limit=256, score_drop=None):
    suite = before.get('suite', 'short_music')
    if suite != after.get('suite', 'short_music'):
        raise ValueError('Cannot compare short and long benchmark suites')
    judge_enabled = suite != 'long_music'
    if not judge_enabled and score_drop is not None:
        raise ValueError('Long music benchmarks have no ASR score gate')
    for run in (before, after):
        if run['status'] not in ('complete', 'complete_with_warnings') or run['preliminary']:
            raise ValueError('Comparison requires two complete dedicated-worker runs')
    if before['configuration'] != after['configuration']:
        raise ValueError('Harness, corpus, requests, seeds or sampling configuration changed')
    for field in ('models',):
        if before['environment'][field] != after['environment'][field]:
            raise ValueError('Model bytes changed; prepare a separate workload comparison')
    for key in ('uuid', 'driver_version', 'name'):
        if before['environment']['gpu'][key] != after['environment']['gpu'][key]:
            raise ValueError('GPU or driver changed')
    if judge_enabled and before['environment']['asr']['model'] != after['environment']['asr']['model']:
        raise ValueError('ASR judge changed')
    a, b = summarize(before), summarize(after)
    failures, changes, review_signals = [], {}, []
    for language, old in a['languages'].items():
        new = b['languages'][language]
        if new['calls'] != old['calls'] or (judge_enabled and new['judged'] != new['calls']):
            failures.append(language + ': incomplete measured/scored calls')
        if new['module_loads']:
            failures.append(language + ': weight reload during timed generation')
        delta = {}
        for statistic in ('median', 'p95'):
            old_time, new_time = old['pipeline_seconds'][statistic], new['pipeline_seconds'][statistic]
            delta[statistic + '_latency_percent'] = 100 * (new_time / old_time - 1)
            if new_time > old_time * (1 + latency_limit):
                failures.append(f'{language}: {statistic} latency increased beyond {latency_limit:.0%}')
        delta['peak_delta_mib'] = new['peak_delta_mib'] - old['peak_delta_mib']
        if delta['peak_delta_mib'] > vram_limit:
            failures.append(language + ': peak VRAM increase beyond allowance')
        if judge_enabled:
            delta['lyric_score_points'] = new['lyric_accuracy_percent']['median'] - old['lyric_accuracy_percent']['median']
            delta['minimum_lyric_score_points'] = new['lyric_accuracy_percent']['min'] - old['lyric_accuracy_percent']['min']
            if min(delta['lyric_score_points'], delta['minimum_lyric_score_points']) < 0:
                review_signals.append(language + ': ASR match decreased; review judge variability and paired samples')
            if score_drop is not None and min(delta['lyric_score_points'], delta['minimum_lyric_score_points']) < -score_drop:
                failures.append(language + ': lyric fidelity dropped beyond allowance')
        if new['duration_warnings'] > old['duration_warnings']:
            failures.append(language + ': additional duration failures')
        if new['audio_integrity_warnings'] > old['audio_integrity_warnings']:
            failures.append(language + ': additional silence/clipping failures')
        if new['repeat_groups_bit_identical'] < old['repeat_groups_bit_identical']:
            failures.append(language + ': fixed-seed repeatability degraded')
        changes[language] = delta
    if b['resident_growth_mib'] > max(vram_limit, a['resident_growth_mib'] + vram_limit):
        failures.append('Retained GPU memory grew beyond allowance')
    return {'schema': 1, 'before': before['run_id'], 'after': after['run_id'], 'passed': not failures,
            'thresholds': {'latency_fraction': latency_limit, 'peak_vram_mib': vram_limit,
            'lyric_score_points': score_drop}, 'changes': changes, 'review_signals': review_signals, 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-latency-increase', type=float, default=.15)
    parser.add_argument('--max-vram-increase-mib', type=float, default=256)
    parser.add_argument('--max-score-drop', type=float,
                        help='Opt-in calibrated ASR score-drop gate; default is comparative review only')
    args = parser.parse_args()
    try:
        if min(args.max_latency_increase, args.max_vram_increase_mib,
               args.max_score_drop if args.max_score_drop is not None else 0) < 0:
            raise ValueError('Regression allowances must be nonnegative')
        result = compare(json.loads(args.before.read_text(encoding='utf-8')),
                         json.loads(args.after.read_text(encoding='utf-8')), args.max_latency_increase,
                         args.max_vram_increase_mib, args.max_score_drop)
        body = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(body, encoding='utf-8', newline='\n')
        print(body)
        return 0 if result['passed'] else 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
