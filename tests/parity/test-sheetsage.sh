#!/bin/bash

set -eo pipefail
cd "$(dirname "$0")"

for backend in CUDA0 CPU; do
    python3 test-sheetsage.py --device $backend 2>&1 | tee ${backend}-sheetsage.log
done
