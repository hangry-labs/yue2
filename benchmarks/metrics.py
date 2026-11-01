"""CPU-only measurement/scoring. ASR fidelity is not a musical-quality score."""
import array
from datetime import datetime
import math
import re
import statistics
import sys
import unicodedata
import wave


def normalized(text):
    return unicodedata.normalize('NFKC', text).casefold().replace('’', "'")


def words(text):
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", normalized(text))


def characters(text):
    return [c for c in normalized(text) if unicodedata.category(c)[0] in ('L', 'N')]


def edits(reference, hypothesis):
    """Levenshtein counts: substitutions, deletions and insertions, unbounded ER."""
    previous = [(j, 0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, expected in enumerate(reference, 1):
        row = [(i, 0, i, 0)]
        for j, actual in enumerate(hypothesis, 1):
            if expected == actual:
                row.append(previous[j - 1])
            else:
                candidates = []
                for base, column in ((previous[j - 1], 1), (previous[j], 2), (row[j - 1], 3)):
                    value = list(base)
                    value[0] += 1
                    value[column] += 1
                    candidates.append(tuple(value))
                row.append(min(candidates, key=lambda value: value[0]))
        previous = row
    total, substitution, deletion, insertion = previous[-1]
    return {'errors': total, 'substitutions': substitution, 'deletions': deletion,
            'insertions': insertion, 'reference_units': len(reference),
            'error_rate': total / len(reference) if reference else None}


def lyric_score(reference, transcript, language):
    if not characters(reference):
        raise ValueError('Reference lyrics must contain text')
    cer = edits(characters(reference), characters(transcript))
    # Chinese has no space-delimited word boundaries. Do not invent a WER.
    wer = None if language == 'zh' else edits(words(reference), words(transcript))
    primary = wer or cer
    return {'transcript': transcript, 'wer': wer, 'cer': cer,
            'primary_metric': 'WER' if wer else 'CER',
            'lyric_accuracy_percent': 100 * max(0.0, 1 - primary['error_rate']),
            'exact_normalized': characters(reference) == characters(transcript)}


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def distribution(values):
    values = list(values)
    return {'n': len(values), 'median': statistics.median(values) if values else None,
            'p95': percentile(values, .95), 'min': min(values) if values else None,
            'max': max(values) if values else None}


def audio_stats(path):
    with wave.open(str(path), 'rb') as stream:
        if stream.getsampwidth() != 2 or stream.getcomptype() != 'NONE':
            raise ValueError('Benchmark requires native PCM16 WAV')
        channels, rate, frames = stream.getnchannels(), stream.getframerate(), stream.getnframes()
        samples = array.array('h', stream.readframes(frames))
    if not samples or channels != 2 or rate != 48000:
        raise ValueError('Expected nonempty 48 kHz stereo audio')
    if sys.byteorder != 'little':
        samples.byteswap()
    peak = max(abs(value) for value in samples) / 32768
    squares = sum(value * value for value in samples)
    rms = math.sqrt(squares / len(samples)) / 32768
    hop = rate * channels // 10
    silent = longest = current = 0
    windows = 0
    for offset in range(0, len(samples), hop):
        block = samples[offset:offset + hop]
        level = math.sqrt(sum(value * value for value in block) / len(block)) / 32768
        windows += 1
        if level < .00316227766:  # -50 dBFS, 100 ms windows
            silent += 1
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return {'duration_seconds': frames / rate, 'sample_rate': rate, 'channels': channels,
            'frames': frames, 'peak_dbfs': 20 * math.log10(peak) if peak else None,
            'rms_dbfs': 20 * math.log10(rms) if rms else None,
            'clipping_fraction': sum(abs(v) >= 32767 for v in samples) / len(samples),
            'silent_window_fraction': silent / windows, 'longest_silence_seconds': longest / 10}


def verify_warm(metrics):
    if metrics.get('schema') != 1 or not metrics.get('keep_loaded'):
        raise ValueError('Server must expose metrics schema 1 and use --keep-loaded')
    if metrics.get('module_loads') != 0 or metrics.get('resident_modules', 0) < 3:
        raise ValueError('Measured generation loaded weights or lost model residency')
    if metrics.get('steps') != 8:
        raise ValueError('Benchmark requires eight flow-matching steps')
    for field in ('pipeline_seconds', 'worker_seconds', 'audio_seconds'):
        value = metrics.get(field, 0)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Server returned invalid generation timings')
    if metrics['pipeline_seconds'] > metrics['worker_seconds'] + .000001:
        raise ValueError('Pipeline time exceeds total worker time')


def integrity_flags(info):
    flags = []
    if not 25 <= info['duration_seconds'] <= 31:
        flags.append('duration_outside_25_to_31_seconds')
    if info['silent_window_fraction'] > .5:
        flags.append('mostly_silent_audio')
    if info['clipping_fraction'] > .001:
        flags.append('clipping_above_0_1_percent')
    return flags


def technical_flags(call):
    # Retain original historical run.json evidence, but do not carry forward its
    # retired absolute ASR acceptance rule into current assessments/reports.
    return [flag for flag in call.get('warnings', []) if flag != 'lyric_accuracy_below_80_percent']


def assessed_status(run):
    if run['status'] not in ('complete', 'complete_with_warnings'):
        return run['status']
    if any(call.get('asr_error') for call in run['calls']):
        return 'failed'
    return 'complete_with_warnings' if any(technical_flags(call) for call in run['calls']) else 'complete'


def suite_timing(run):
    """Disjoint suite wall-time breakdown; pipeline time is nested in HTTP calls."""
    if 'timing' in run:
        return dict(run['timing'])
    start, end = run.get('started_utc'), run.get('finished_utc')
    total = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() if start and end else None
    return timing_breakdown(run, total, 'recorded_utc_timestamps')


def timing_breakdown(run, total, source='monotonic_clock'):
    warmup = sum(call['client_seconds'] for call in run['calls'] if call['phase'] != 'measured')
    measured = sum(call['client_seconds'] for call in run['calls'] if call['phase'] == 'measured')
    asr = sum(call.get('quality', {}).get('asr_seconds', 0) for call in run['calls'])
    return {'total_seconds': total, 'warmup_requests_seconds': warmup,
            'measured_requests_seconds': measured, 'asr_requests_seconds': asr,
            'other_seconds': max(0, total - warmup - measured - asr) if total is not None else None,
            'measured_pipeline_seconds': sum(call['server']['pipeline_seconds'] for call in run['calls']
                                             if call['phase'] == 'measured'),
            'source': source, 'scope': 'suite start through scoring; report export excluded'}
