#!/bin/bash

set -eo pipefail
cd "$(dirname "$0")"

for backend in CUDA0 CPU; do
    python3 test-tokenizer.py --device $backend 2>&1 | tee ${backend}-tokenizer.log
done
