#!/usr/bin/env python3
"""Fail packaging when common model-weight files are present in a filesystem."""
import argparse
import os
from pathlib import Path
import sys


WEIGHT_SUFFIXES = {
    '.gguf', '.ggml', '.safetensors', '.pt', '.pth', '.ckpt', '.bin',
    '.onnx', '.h5', '.hdf5', '.tflite', '.npz',
}
# GGUF and the legacy GGML family, including their little-endian encodings.
WEIGHT_MAGIC = {b'GGUF', b'ggml', b'ggmf', b'ggjt', b'lmgg', b'fmgg', b'tjgg'}


def check(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f'Image filesystem does not exist: {root}')
    violations = []

    def walk_error(error):
        raise error

    for directory, _, files in os.walk(root, onerror=walk_error):
        # Do not follow filesystem links outside the inspected image.
        for name in files:
            path = Path(directory) / name
            if path.suffix.lower() in WEIGHT_SUFFIXES:
                violations.append(str(path.relative_to(root)))
            elif not path.is_symlink() and path.is_file():
                with path.open('rb') as stream:
                    if stream.read(4) in WEIGHT_MAGIC:
                        violations.append(str(path.relative_to(root)))
    if violations:
        raise ValueError('Model weights are forbidden in the image:\n  '
                         + '\n  '.join(sorted(violations))
                         + '\nKeep models external and mount them read-only at runtime.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    try:
        check(args.root)
    except (OSError, ValueError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print('PASS: no model-weight filenames or GGUF/GGML headers in image filesystem')
    return 0


if __name__ == '__main__':
    sys.exit(main())
