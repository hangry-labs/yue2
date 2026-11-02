#!/usr/bin/env python3
"""Analyze completed variation runs without regenerating audio or rewriting evidence."""
import argparse
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]


def stages(log):
    """Keep repeated queued/started job markers together; reject partial timings."""
    blocks = {}
    parts = re.split(r'^\[Server\] Job ([0-9a-f]+):', log, flags=re.MULTILINE)
    for index in range(1, len(parts), 2):
        blocks.setdefault(parts[index], []).append(parts[index + 1])
    result = {}
    for job, body in blocks.items():
        body = ''.join(body)
        row = {}
        for name in ('Score', 'Semantic'):
            matches = re.findall(r'\[AR\] ' + name + r': \d+ tokens over \d+ songs, \d+ steps, ([\d.]+) s', body)
            row[name.lower() + '_seconds'] = sum(map(float, matches)) if matches else None
        nar = re.findall(r'\[NAR\] Song \d+ chunk \d+/\d+: .*?, ([\d.]+) s', body)
        vae = re.findall(r'\[VAE\] Tiled decode done: .*?, ([\d.]+) ms', body)
        row.update(nar_seconds=sum(map(float, nar)) if nar else None,
                   vae_seconds=sum(map(float, vae)) / 1000 if vae else None,
                   decoded_tracks=len(vae))
        result[job] = row
    return result


def analyze(run, folder):
    if run.get('suite') != 'acoustic_variations' or run.get('status') not in ('complete', 'complete_with_warnings'):
        raise ValueError('Choose a completed acoustic-variations run')
    rows = []
    groups = []
    stage_keys = ('score_seconds', 'semantic_seconds', 'nar_seconds', 'vae_seconds')
    reference_seeds = None
    for count in sorted(run['configuration']['variations']):
        calls = [c for c in run['calls'] if c['phase'] == 'measured' and c['variation_count'] == count]
        seeds = sorted(c['seed'] for c in calls)
        if not calls or (reference_seeds is not None and seeds != reference_seeds):
            raise ValueError('Variation counts must have the same measured seed schedule')
        reference_seeds = seeds
        by_job = stages((folder / f'worker-m{count}.log').read_text(encoding='utf-8'))
        matched = []
        for call in calls:
            values = by_job.get(call['job_id'])
            if not values or any(values[k] is None for k in stage_keys) or values['decoded_tracks'] != count:
                raise ValueError(f'Missing stage/track timings for {call["id"]}')
            if call['server']['module_loads'] != 0:
                raise ValueError('Measured weights must remain resident')
            if len(call['tracks']) != count or len({t['audio_sha256'] for t in call['tracks']}) != count:
                raise ValueError('Expected distinct acoustic renditions for every variation')
            matched.append(values)
            rows.append({'id': call['id'], 'job_id': call['job_id'], 'variations': count, **values})
        pipeline = statistics.mean(c['server']['pipeline_seconds'] for c in calls)
        group = {'variations': count, 'requests': len(calls), 'tracks': len(calls) * count,
                 'mean_batch_seconds': pipeline, 'mean_seconds_per_track': pipeline / count,
                 'peak_device_mib': max(c['gpu']['peak_mib'] for c in calls),
                 'peak_above_idle_mib': max(c['gpu']['peak_delta_mib'] for c in calls),
                 'stages': {k: statistics.mean(s[k] for s in matched) for k in stage_keys}}
        group['unattributed_seconds'] = pipeline - sum(group['stages'].values())
        scores = [t['quality']['lyric_accuracy_percent'] for c in calls for t in c['tracks'] if t.get('quality')]
        group['asr_judged_tracks'] = len(scores)
        group['asr_median_match'] = statistics.median(scores) if scores else None
        if groups:
            previous = groups[-1]
            group['extra_batch_seconds_per_added_track'] = (pipeline - previous['mean_batch_seconds']) / (count - previous['variations'])
            group['throughput_gain_percent_vs_previous'] = (previous['mean_seconds_per_track'] / group['mean_seconds_per_track'] - 1) * 100
        groups.append(group)
    if not groups or groups[0]['variations'] != 1 or not run.get('matched_conditioning'):
        raise ValueError('Require a matched single-variation control')
    for group in groups:
        group['throughput_vs_single'] = groups[0]['mean_seconds_per_track'] / group['mean_seconds_per_track']
    return {'schema': 1, 'run_id': run['run_id'], 'image_id': run['environment']['image_id'],
            'gpu': run['environment']['gpu']['name'], 'suite_seconds': run['timing']['total_seconds'],
            'groups': groups, 'per_call_stages': rows}


def markdown(result):
    body = ('# Acoustic-variation scaling\n\n'
        f'Run `{result["run_id"]}`; {result["gpu"]}; image `{result["image_id"]}`. '
        'Matched two-minute English songs, fixed seeds per count, eight steps, resident models. '
        'Every count uses a fresh worker and a full-length excluded warmup.\n\n'
        '| Variations | Mean batch s | Mean s / rendition | Throughput vs one | Extra batch s / added rendition | Throughput gain over previous | Device peak MiB |\n'
        '| --- | --- | --- | --- | --- | --- | --- |\n')
    for row in result['groups']:
        extra = row.get('extra_batch_seconds_per_added_track')
        gain = row.get('throughput_gain_percent_vs_previous')
        body += (f'| {row["variations"]} | {row["mean_batch_seconds"]:.2f} | {row["mean_seconds_per_track"]:.2f} | '
                 f'{row["throughput_vs_single"]:.2f}x | ' + (f'{extra:.2f}' if extra is not None else 'n/a') + ' | '
                 + (f'{gain:.1f}%' if gain is not None else 'n/a') + f' | {row["peak_device_mib"]:.0f} |\n')
    body += ('\nStage means below come from rounded native log summaries, matched to measured job IDs. '
        'They are explanatory timings, not GPU kernel profiles. NAR includes acoustic chunk setup/solve; '
        'VAE sums all renditions, which decode separately. The residual includes rounding and unlogged work.\n\n'
        '| Variations | Score s | Semantic s | Acoustic NAR s | All VAE decodes s | Residual s |\n'
        '| --- | --- | --- | --- | --- | --- |\n')
    for row in result['groups']:
        body += f'| {row["variations"]} | ' + ' | '.join(f'{row["stages"][k]:.2f}' for k in
            ('score_seconds', 'semantic_seconds', 'nar_seconds', 'vae_seconds')) + f' | {row["unattributed_seconds"]:.2f} |\n'
    body += ('\nThroughput is based on aggregate pipeline time divided by rendered track count. '
        'It excludes ASR, cold/warmup requests, encoding and HTTP delivery. Memory peaks are sampled '
        'whole-device observations including desktop/driver allocations. More variations share a composition '
        'and semantic stream, but have distinct waveform hashes.\n\n'
        'Small differences need repetition before being treated as a '
        'stable hardware limit. These measurements do not establish memory requirements for five-minute '
        'songs, other prompts, or larger batches. ASR remains an imperfect comparative judge. '
        f'Total original suite wall time, including warmups and ASR: {result["suite_seconds"]:.2f} seconds. '
        'This offline analysis does not alter captured requests, audio, timings or the original run manifest.\n')
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--write-report', action='store_true', help='Also update the public scaling Markdown')
    args = parser.parse_args()
    result = analyze(json.loads(args.run.read_text(encoding='utf-8')), args.run.parent)
    (args.run.parent / 'scaling.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    body = markdown(result)
    (args.run.parent / 'SCALING.md').write_text(body, encoding='utf-8', newline='\n')
    if args.write_report:
        (ROOT / 'benchmarks/variations/SCALING.md').write_text(body, encoding='utf-8', newline='\n')
    print(body)


if __name__ == '__main__':
    main()
