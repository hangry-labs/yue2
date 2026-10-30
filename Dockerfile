# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY VERSION /VERSION
ARG SOURCE_REVISION=unknown
RUN export YUE2_VERSION="$(cat /VERSION) ($SOURCE_REVISION)" \
    && npm run check && npm run lint && npm run build \
    && mkdir /web-licenses \
    && cp node_modules/svelte/LICENSE.md /web-licenses/svelte-MIT.txt \
    && cp node_modules/@lucide/svelte/LICENSE /web-licenses/lucide.txt \
    && cp node_modules/yaml/LICENSE /web-licenses/yaml-ISC.txt

FROM scratch AS source
COPY CMakeLists.txt VERSION LICENSE THIRD_PARTY_NOTICES.md /
COPY cmake/ /cmake/
COPY src/ /src/
COPY vendor/ /vendor/
COPY tests/ /tests/
COPY web/public/ /web/public/

FROM ubuntu:24.04 AS cpu-checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake ninja-build g++ git python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY --from=source / /src/
COPY scripts/smoke_binaries.py /smoke_binaries.py
ARG SOURCE_REVISION=unknown
RUN --mount=type=cache,id=yue2-native-cpu,target=/build,sharing=locked \
    cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_NATIVE=OFF \
    -DBUILD_SHARED_LIBS=OFF -DYUE2_REVISION="$SOURCE_REVISION" \
    && cmake --build /build --parallel 4 \
    && python3 /smoke_binaries.py /build

FROM nvidia/cuda:12.9.1-devel-ubuntu24.04 AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates cmake ninja-build g++ git ccache \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY --from=source / /src/
COPY --from=web /web/public/index.html.gz /src/web/public/index.html.gz
ARG SOURCE_REVISION=unknown
ARG CUDA_ARCHITECTURES="75-virtual;80-virtual;86-real;89-real;120a-real"
ARG BUILD_JOBS=4
RUN --mount=type=cache,id=yue2-native-cuda,target=/build,sharing=locked \
    --mount=type=cache,id=yue2-ccache,target=/root/.cache/ccache,sharing=locked \
    cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHITECTURES" \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CUDA_COMPILER_LAUNCHER=ccache \
    -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_CUDA=ON -DGGML_VULKAN=OFF \
    -DYUE2_REVISION="$SOURCE_REVISION" \
    && cmake --build /build --parallel "$BUILD_JOBS" --target \
    yue-server yue-synth yue-plan yue-transcribe yue-tokenize \
    neural-codec mp3-codec quantize \
    && mkdir -p /out/bin /out/licenses \
    && cp /build/yue-server /build/yue-synth /build/yue-plan \
    /build/yue-transcribe /build/yue-tokenize /build/neural-codec \
    /build/mp3-codec /build/quantize /out/bin/ \
    && cp LICENSE /out/licenses/yue2-MIT.txt \
    && cp THIRD_PARTY_NOTICES.md /out/licenses/ \
    && cp vendor/ggml/LICENSE /out/licenses/ggml-MIT.txt \
    && cp vendor/cpp-httplib/LICENSE /out/licenses/cpp-httplib-MIT.txt \
    && cp vendor/yyjson/yyjson.h /out/licenses/yyjson.h \
    && cp vendor/minimp3/minimp3.h /out/licenses/minimp3.h

FROM nvidia/cuda:12.9.1-runtime-ubuntu24.04 AS runtime-unchecked
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libstdc++6 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home yue \
    && mkdir -p /models /output /adapters \
    && chown yue:yue /output /adapters
COPY --from=build /out/ /opt/yue/
COPY --from=web /web-licenses/ /opt/yue/licenses/web/
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Hangry Labs YuE2" \
    org.opencontainers.image.source="https://github.com/hangry-labs/yue2" \
    org.opencontainers.image.revision="$SOURCE_REVISION"
ENV PATH="/opt/yue/bin:$PATH"
USER yue
WORKDIR /output
EXPOSE 8087
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8087/health || exit 1
ENTRYPOINT ["yue-server"]
CMD ["--host", "0.0.0.0", "--port", "8087", "--model", "/models/YuE2-3B-Q8_0.gguf", "--vae", "/models/YuE2-Vae-F32.gguf", "--adapters", "/adapters"]

# Inspect the assembled filesystem without adding Python to the shipped image.
FROM python:3.13-slim AS weights-check
COPY scripts/check_no_weights.py /check_no_weights.py
RUN --mount=type=bind,from=runtime-unchecked,source=/,target=/image \
    python /check_no_weights.py /image \
    && printf 'Model-weight packaging check passed\n' > /weights-check.txt

# This dependency makes the check mandatory for default and --target runtime builds.
FROM runtime-unchecked AS runtime
COPY --from=weights-check /weights-check.txt /opt/yue/licenses/weights-check.txt
