"""Convert local audio with explicit, verified FFmpeg encoding profiles."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

PROFILES = {
    'opus': {'extension': '.opus', 'codec': 'opus', 'container': 'ogg', 'mime': 'audio/ogg; codecs=opus',
             'lossy': True, 'bitrate': 96000, 'vbr': True, 'application': 'audio', 'compression_level': 10,
             'arguments': ['-c:a', 'libopus', '-b:a', '96000', '-vbr', 'on', '-application', 'audio', '-compression_level', '10']},
    'ogg': {'extension': '.ogg', 'codec': 'vorbis', 'container': 'ogg', 'mime': 'audio/ogg; codecs=vorbis',
            'lossy': True, 'quality': 5, 'arguments': ['-c:a', 'libvorbis', '-q:a', '5']},
    'mp3': {'extension': '.mp3', 'codec': 'mp3', 'container': 'mp3', 'mime': 'audio/mpeg',
            'lossy': True, 'bitrate': 128000, 'arguments': ['-c:a', 'libmp3lame', '-b:a', '128k']},
    'flac': {'extension': '.flac', 'codec': 'flac', 'container': 'flac', 'mime': 'audio/flac',
             'lossy': False, 'bits': 24, 'arguments': ['-c:a', 'flac', '-sample_fmt', 's32', '-bits_per_raw_sample', '24']},
    'wav16': {'extension': '.wav', 'codec': 'pcm_s16le', 'container': 'wav', 'mime': 'audio/wav',
              'lossy': False, 'bits': 16, 'arguments': ['-c:a', 'pcm_s16le']},
    'wav24': {'extension': '.wav', 'codec': 'pcm_s24le', 'container': 'wav', 'mime': 'audio/wav',
              'lossy': False, 'bits': 24, 'arguments': ['-c:a', 'pcm_s24le']},
    'wav32': {'extension': '.wav', 'codec': 'pcm_f32le', 'container': 'wav', 'mime': 'audio/wav',
              'lossy': False, 'bits': 32, 'arguments': ['-c:a', 'pcm_f32le']},
    'aac': {'extension': '.aac', 'codec': 'aac', 'container': 'adts', 'mime': 'audio/aac',
            'lossy': True, 'bitrate': 192000, 'arguments': ['-c:a', 'aac', '-b:a', '192k']},
    'm4a': {'extension': '.m4a', 'codec': 'aac', 'container': 'ipod', 'mime': 'audio/mp4',
            'lossy': True, 'bitrate': 192000, 'arguments': ['-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart']},
}
LOSSY_CODECS = {'mp3', 'vorbis', 'opus', 'aac', 'wmav2', 'ac3'}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                             'format=duration:stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample',
                             '-of', 'json', str(path)], check=True, capture_output=True, encoding='utf-8')
    value = json.loads(result.stdout)
    if not value.get('streams'):
        raise ValueError('The input does not contain an audio stream.')
    stream = value['streams'][0]
    return {'codec': stream['codec_name'], 'sample_rate': int(stream['sample_rate']),
            'channels': int(stream['channels']), 'seconds': round(float(value['format']['duration']), 3),
            'bits': int(stream.get('bits_per_raw_sample') or 0) or int(stream.get('bits_per_sample') or 0)}


def profile(name):
    if name not in PROFILES:
        raise ValueError(f'Unknown audio format: {name}')
    return {key: value for key, value in PROFILES[name].items() if key != 'arguments'}


def convert(source, destination, name, overwrite=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Input and output paths must be different.')
    if destination.exists() and not overwrite:
        raise FileExistsError(f'Output already exists: {destination}; use --overwrite explicitly.')
    if not source.is_file():
        raise FileNotFoundError(source)
    settings = profile(name)
    if destination.suffix.lower() != settings['extension']:
        raise ValueError(f'{name} output must use {settings["extension"]}.')
    original = probe(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-map', '0:a:0', '-vn',
                        '-map_metadata', '-1', *PROFILES[name]['arguments'], '-f', settings['container'],
                        str(temporary)], check=True, capture_output=True)
        measured = probe(temporary)
        if measured['codec'] != settings['codec'] or measured['channels'] != original['channels']:
            raise ValueError(f'Unexpected encoded audio: {measured}')
        if abs(measured['seconds'] - original['seconds']) > 0.15:
            raise ValueError('Conversion changed the recording duration unexpectedly.')
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(temporary), '-f', 'null', '-'],
                       check=True, capture_output=True)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    version = subprocess.check_output(['ffmpeg', '-version']).decode('utf-8').splitlines()[0]
    return {**measured, 'bytes': destination.stat().st_size, 'sha256': sha256(destination),
            'mime': settings['mime'], 'encoding': {**settings, 'ffmpeg': version},
            'source': {**original, 'sha256': sha256(source), 'bytes': source.stat().st_size,
                       'lossy': original['codec'] in LOSSY_CODECS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--format', choices=PROFILES, required=True)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    for command in ('ffmpeg', 'ffprobe'):
        if not shutil.which(command):
            parser.error(f'{command} is required.')
    print(json.dumps(convert(args.input, args.output, args.format, args.overwrite), indent=2))


if __name__ == '__main__':
    main()
