"""Verify or refresh the gallery's single Ogg Opus export without inference."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.audio_formats import convert, profile, sha256
from scripts.generate_gallery import publish, waveform


def convert_record(song, gallery):
    previous = song['audio']
    target = gallery / previous['path']
    if sha256(target) != previous['sha256']:
        raise ValueError(f'Published audio changed: {song["id"]}')
    if all(previous.get('encoding', {}).get(key) == value for key, value in profile('opus').items()):
        song['downloads'] = {'opus': previous}
        return song
    source = None
    master = song.get('master')
    if master:
        extension = '.wav' if master['codec'].startswith('pcm_') else '.mp3'
        candidate = ROOT / 'data/results/gallery-masters' / (song['id'] + '-' + song['fingerprint'][:12] + extension)
        if candidate.is_file():
            if sha256(candidate) != master['sha256']:
                raise ValueError(f'Local PCM master changed: {song["id"]}')
            source = candidate
    if source is None:
        raise ValueError(f'Original source unavailable for {song["id"]}; regenerate it to change encoding.')
    info = convert(source, target, 'opus', overwrite=True)
    song['audio'] = {'path': target.relative_to(gallery).as_posix(), **info}
    song['downloads'] = {'opus': song['audio']}
    song['waveform'] = waveform(target)
    return song


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    gallery = ROOT / 'examples'
    manifest = json.loads((gallery / 'assets/manifest.json').read_text(encoding='utf-8'))
    # Validate every recorded source before producing any derivatives.
    for song in manifest['songs']:
        for asset in [song['audio'], song['recipe'], song['replay'], *(song.get('downloads') or {}).values()]:
            if sha256(gallery / asset['path']) != asset['sha256']:
                raise ValueError(f'Changed public asset: {asset["path"]}')
    for song in manifest['songs']:
        song['engine'] = song.get('engine') or manifest['engine']
        convert_record(song, gallery)
        publish(manifest)
        print(f'Ready: {song["title"]}', flush=True)
    manifest['schema'] = 3
    publish(manifest)


if __name__ == '__main__':
    main()
