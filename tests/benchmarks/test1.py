#!/usr/bin/env python3
"""Run the recorded test1 prompt through the Docker inference CLI."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import storage

def parse_prompt(path):
    source = path.read_text(encoding='utf-8-sig')
    style, separator, lyrics = source.partition('\nlyrics=')
    if not style.startswith('style=') or not separator:
        raise ValueError('tests/fixtures/test1.txt must contain style= followed by a lyrics= section')
    first, _, continuation = lyrics.partition('\n')
    lyrics = (first + '\n' + textwrap.dedent(continuation)).strip()
    style = style[len('style='):].strip()
    if not style or not lyrics:
        raise ValueError('Style and lyrics must both be nonempty')
    return style, lyrics


def model_info(path):
    with path.open('rb') as model:
        digest = hashlib.file_digest(model, 'sha256').hexdigest()
    return {'bytes': path.stat().st_size, 'sha256': digest}


def validate_steps(replay, log_text):
    # Sparse replay JSON omits values equal to the CLI defaults (8).
    # Check executed steps too, rather than trusting metadata alone.
    steps = re.findall(r'\[NAR\] Step (\d+)/(\d+),', log_text)
    if replay.get('steps', 8) != 8 or steps != [(str(i), '8') for i in range(1, 9)]:
        raise ValueError('Unexpected flow-matching step count')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='yue2:dev')
    parser.add_argument('--lm-seed', type=int, default=831001)
    parser.add_argument('--seed', type=int, default=831001)
    parser.add_argument('--prepare-only', action='store_true',
                        help='Write the request without starting Docker inference')
    args = parser.parse_args()
    storage.require_migrated()
    if args.lm_seed < 0 or args.seed < 0:
        parser.error('Baseline seeds must be nonnegative for repeatability')

    root = ROOT
    prompt = root / 'tests' / 'fixtures' / 'test1.txt'
    style, lyrics = parse_prompt(prompt)
    request = {
        'style': style, 'lyrics': lyrics, 'cot': 'full', 'duration': 360,
        'steps': 8, 'lm_seed': args.lm_seed, 'seed': args.seed,
        'lm_batch_size': 1, 'synth_batch_size': 1,
        'output_format': 'mp3', 'mp3_bitrate': 128,
    }
    image = None
    if not args.prepare_only:
        for name in ('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf'):
            if not (storage.MODELS / name).is_file():
                raise RuntimeError(f'Missing data/models/{name}; see docs/DOCKER.md')
        inspected = subprocess.run(['docker', 'image', 'inspect', args.image],
                                   capture_output=True, text=True, check=True)
        image = json.loads(inspected.stdout)[0]

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run = storage.RESULTS / 'test1' / (stamp + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    (run / 'prompt.txt').write_bytes(prompt.read_bytes())
    (run / 'request.json').write_text(json.dumps(request, indent=2) + '\n', encoding='utf-8')
    print(f'Results: {run}', flush=True)
    print('Profile: full score, 360-second ceiling, 8 steps, upstream context, '
          f'LM seed {args.lm_seed}, acoustic seed {args.seed}', flush=True)
    if args.prepare_only:
        return 0

    print('Recording model SHA-256 hashes (outside the measured generation time).', flush=True)
    models = {name: model_info(storage.MODELS / name)
              for name in ('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf')}

    command = ['docker', 'run', '--rm', '--pull=never', '--gpus', 'all',
               '--name', 'yue2-test1-' + uuid.uuid4().hex[:12]]
    # Preserve host ownership on Linux. Windows bind mounts are writable by
    # the image's normal non-root user.
    if hasattr(os, 'getuid'):
        command += ['--user', f'{os.getuid()}:{os.getgid()}']
    command += [
        '--mount', f'type=bind,source={storage.MODELS},target=/models,readonly',
        '--mount', f'type=bind,source={run},target=/output',
        '--entrypoint', 'yue-synth', args.image,
        '--model', '/models/YuE2-3B-Q8_0.gguf',
        '--vae', '/models/YuE2-Vae-F32.gguf',
        '--request', '/output/request.json', '--out', '/output/song.mp3',
        '--score', '/output/score.abc', '--tokens', '/output/semantic.csv',
        '--latent', '/output/latents.vae',
    ]
    metadata = {
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'prompt_sha256': hashlib.sha256(prompt.read_bytes()).hexdigest(),
        'image': args.image, 'image_id': image['Id'],
        'image_source_revision': (image['Config'].get('Labels') or {}).get(
            'org.opencontainers.image.revision'),
        'command': command, 'request': request,
        'models': models,
        'status': 'running',
    }
    summary = run / 'summary.json'
    summary.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    started = time.monotonic()
    with (run / 'generation.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   encoding='utf-8', errors='replace', bufsize=1)
        try:
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            code = process.wait()
        except KeyboardInterrupt:
            subprocess.run(['docker', 'stop', '--time', '10', command[command.index('--name') + 1]],
                           capture_output=True)
            process.wait()
            code = 130
    metadata['wall_seconds'] = round(time.monotonic() - started, 3)
    log_text = (run / 'generation.log').read_text(encoding='utf-8')
    timing = re.search(r'\[Pipeline\] Done: (\d+) tracks, ([\d.]+) s of audio in ([\d.]+) s', log_text)
    if timing:
        metadata.update(audio_seconds=float(timing[2]), pipeline_seconds=float(timing[3]))
    device = re.search(r'Device 0: ([^\n]+)', log_text)
    if device:
        metadata['gpu'] = device[1]
    metadata['status'] = 'failed'
    if code == 0:
        try:
            replay = json.loads((run / 'song.json').read_text(encoding='utf-8'))
            if not timing or not (run / 'song.mp3').stat().st_size:
                raise ValueError('Missing generated audio or pipeline completion')
            if not replay.get('abc') or not replay.get('semantic_tokens'):
                raise ValueError('Missing score or semantic replay data')
            validate_steps(replay, log_text)
            metadata['semantic_frames'] = len(replay['semantic_tokens'].split(','))
            metadata['duration_cap_reached'] = 'tokens (truncated)' in log_text
            metadata['status'] = 'passed'
        except (OSError, ValueError) as error:
            metadata['validation_error'] = str(error)
            code = 1
    metadata['exit_code'] = code
    summary.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(f'Baseline {metadata["status"]}: wall {metadata["wall_seconds"]:.1f}s, '
          f'audio {metadata.get("audio_seconds", "unknown")}s. Summary: {summary}', flush=True)
    return code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f'test1: {error}', file=sys.stderr)
        sys.exit(1)
