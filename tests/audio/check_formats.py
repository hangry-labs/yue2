"""Exercise real native encoders/decoders and FFmpeg child cleanup, without weights."""
import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile


def run(*args, **kwargs):
    return subprocess.check_output(args, **kwargs)


def probe(path):
    return json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)))


def main():
    binary = str(Path(sys.argv[1]).resolve())
    expected = {'mp3': 'mp3', 'opus': 'opus', 'ogg': 'vorbis', 'flac': 'flac', 'aac': 'aac', 'm4a': 'aac',
                'wav16': 'pcm_s16le', 'wav24': 'pcm_s24le', 'wav32': 'pcm_f32le'}
    with tempfile.TemporaryDirectory(prefix='yue2-codecs-') as temporary:
        folder = Path(temporary) / 'audio with spaces; literal $name'
        folder.mkdir()
        run(binary, 'render', str(folder))
        assert (folder / 'compat.pcm').stat().st_size == 24000 * 2 * 2
        for filename, seconds in [('slow.opus', 8), ('fast.opus', .5)]:
            data = run('ffmpeg', '-v', 'error', '-i', str(folder / filename), '-f', 'f32le', 'pipe:1')
            values = array.array('f', data)
            if sys.byteorder != 'little': values.byteswap()
            assert abs(len(values) / (48000 * 2) - seconds) < .25, filename
            samples = values[0::2]
            samples = samples[len(samples)//4:len(samples)*3//4]
            frequency = sum(a <= 0 < b for a, b in zip(samples, samples[1:])) * 48000 / len(samples)
            assert abs(frequency - 440) < 20, (filename, frequency)
        print('PASS explicit PCM24k/mono and pitch-preserving speed boundaries .25/4.0')
        for name, codec in expected.items():
            path = folder / (name + ('.wav' if name.startswith('wav') else '.' + name))
            info = probe(path)
            stream = info['streams'][0]
            assert stream['codec_name'] == codec, info
            assert int(stream['sample_rate']) == 48000 and stream['channels'] == 2, info
            if name == 'flac':
                assert stream['bits_per_raw_sample'] == '24', info
            decoded = folder / 'decoded.wav'
            run(binary, 'decode', str(path), str(decoded))
            # ADTS AAC has no duration index; probe estimates can drift on VBR
            # content. Check actual decoded samples rather than that estimate.
            actual = probe(decoded)
            assert abs(float(actual['format']['duration']) - 2) < .1, actual
            data = run('ffmpeg', '-v', 'error', '-i', str(decoded), '-f', 'f32le', 'pipe:1')
            values = array.array('f', data)
            if sys.byteorder != 'little':
                values.byteswap()
            # Stereo must retain distinct left/right tones after real round trips.
            def crossings(channel):
                samples = values[channel::2]
                samples = samples[4800:48000]
                return sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
            assert 380 < crossings(0) < 410 and 770 < crossings(1) < 810, name
            print('PASS encode/decode:', name)
        for extension, codec in [('webm', 'libopus'), ('mp4', 'aac')]:
            path = folder / ('upload.' + extension)
            run('ffmpeg', '-v', 'error', '-i', str(folder / 'wav32.wav'), '-c:a', codec, str(path))
            run(binary, 'decode', str(path), str(folder / 'decoded.wav'))
            print('PASS upload:', extension)
        mono = folder / 'mono.flac'
        run('ffmpeg', '-v', 'error', '-i', str(folder / 'wav32.wav'), '-ac', '1', '-ar', '44100', str(mono))
        run(binary, 'decode', str(mono), str(folder / 'decoded.wav'))
        converted = probe(folder / 'decoded.wav')['streams'][0]
        assert converted['channels'] == 2 and int(converted['sample_rate']) == 48000
        invalid = folder / 'invalid.ogg'
        invalid.write_bytes(b'not audio')
        assert subprocess.run([binary, 'decode', str(invalid), str(folder / 'invalid.wav')], capture_output=True).returncode != 0
        for mode in ('cancel', 'timeout'):
            run(binary, mode)
            print('PASS FFmpeg child:', mode)
    print('PASS: all audio formats, stereo/rate/duration, upload decoding and child lifecycle.')


if __name__ == '__main__':
    main()
