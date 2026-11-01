# Warm generation speed

Run `20261101T170052Z-846682fc`, revision `bbc19f2-dirty`, NVIDIA GeForce RTX 5070 Ti. Image `sha256:2c8ed04ae8f7960b8bf46b57c06d9017fbcefde66f8f43f79731b1db9eabb53d`. Isolated inference worker; desktop activity may share the device.

One full warmup per language is excluded. Timed calls require zero weight loads and at least three resident modules. Pipeline time includes score planning, semantic generation, eight flow-matching steps and VAE decoding; worker time adds audio encoding/packaging, and client time adds HTTP transfer/polling. ASR is separate.

| Language | N | Audio median s | Pipeline median s | Pipeline p95 s | Worker median s | Client median s | Audio s / generation s | RTF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | 10 | 30.00 | 5.88 | 7.39 | 5.90 | 6.29 | 4.90 | 0.204 |
| zh | 10 | 30.00 | 5.33 | 5.90 | 5.35 | 5.72 | 5.58 | 0.179 |
| es | 10 | 30.00 | 6.97 | 9.33 | 6.99 | 7.38 | 4.41 | 0.227 |
| de | 10 | 30.00 | 5.38 | 6.33 | 5.40 | 5.77 | 5.59 | 0.179 |
