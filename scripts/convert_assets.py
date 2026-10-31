#!/usr/bin/env python3
"""Convert supplied PNG artwork to WebP; remove validated project-local PNGs."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('yue2_logo_horizontal', 'yue2_logo', 'yue2_badge', 'yue2_mascot')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'build/artwork-input',
                        help='Temporary PNG input directory; external originals remain read-only')
    args = parser.parse_args()
    sources = [args.source_dir / (name + '.png') for name in NAMES]
    if any(not source.is_file() for source in sources):
        raise SystemExit('Place all four supplied PNGs in build/artwork-input/, or pass --source-dir.')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('Install FFmpeg with the libwebp encoder to regenerate artwork.')
    output = ROOT / 'web/src/assets'
    for name in NAMES:
        source = args.source_dir / (name + '.png')
        target = output / (name + '.webp')
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(source), '-frames:v', '1', '-c:v', 'libwebp',
                        '-quality', '90', '-compression_level', '6', str(target)], check=True)
        print(f'{target.relative_to(ROOT)}: {target.stat().st_size:,} bytes')
    favicon = output / 'yue2_favicon.webp'
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                    '-i', str(args.source_dir / 'yue2_mascot.png'),
                    '-vf', 'scale=128:128:flags=lanczos', '-frames:v', '1',
                    '-c:v', 'libwebp', '-quality', '90', '-compression_level', '6',
                    str(favicon)], check=True)
    print(f'{favicon.relative_to(ROOT)}: {favicon.stat().st_size:,} bytes')
    # Validate every conversion before removing any supplied project-local file.
    # An external/server source directory is never modified.
    def alpha_hash(path):
        value = subprocess.check_output([ffmpeg, '-hide_banner', '-loglevel', 'error',
                                         '-i', str(path), '-vf', 'alphaextract',
                                         '-f', 'framemd5', '-'], text=True)
        return [line for line in value.splitlines() if not line.startswith('#')][-1].rsplit(',', 1)[-1].strip()

    for source in sources:
        if alpha_hash(source) != alpha_hash(output / (source.stem + '.webp')):
            raise SystemExit(f'Alpha mismatch; PNG inputs retained: {source.name}')
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(favicon),
                    '-f', 'null', '-'], check=True)
    for source in sources:
        if source.resolve().is_relative_to(ROOT.resolve()):
            source.unlink()
            print(f'Removed converted PNG: {source.name}')
    if args.source_dir.resolve().is_relative_to(ROOT.resolve()):
        try:
            args.source_dir.rmdir()
        except OSError:
            pass


if __name__ == '__main__':
    main()
