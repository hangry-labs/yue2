# syntax=docker/dockerfile:1
ARG CUDA_BASE=nvidia/cuda:12.9.1-devel-ubuntu24.04@sha256:020bc241a628776338f4d4053fed4c38f6f7f3d7eb5919fecb8de313bb8ba47c
ARG GGML_DEPS_IMAGE=ggml-deps

# These stages depend only on GGML and its toolchain, never app/UI/revision.
FROM ${CUDA_BASE} AS cuda-toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates cmake ninja-build g++ git ccache python3 \
    && rm -rf /var/lib/apt/lists/*

FROM cuda-toolchain AS ggml-deps-build
WORKDIR /dependency
COPY cmake/ggml-deps/ cmake/ggml-deps/
COPY cmake/ggml-abi.cmake cmake/ggml-source.cmake cmake/
COPY docker/ggml-source.json docker/ggml-source.json
ARG CUDA_ARCHITECTURES="75-virtual;80-virtual;86-real;89-real;120a-real"
ARG BUILD_JOBS=4
RUN --mount=type=cache,id=yue2-ggml-ccache,target=/root/.cache/ccache,sharing=locked \
    cmake -S cmake/ggml-deps -B /ggml-build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/ggml -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHITECTURES" \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CUDA_COMPILER_LAUNCHER=ccache \
    && cmake --build /ggml-build --parallel "$BUILD_JOBS" \
    && cmake --install /ggml-build \
    && rm -rf /ggml-build
# Metadata/checker edits can rerun verification without recompiling CUDA.
COPY Dockerfile /dependency/Dockerfile
COPY docker/ggml-deps.json /dependency/docker/ggml-deps.json
COPY scripts/ggml_deps.py scripts/check_no_weights.py /dependency/scripts/
ARG CUDA_BASE
RUN python3 scripts/ggml_deps.py record --architectures "$CUDA_ARCHITECTURES" --cuda-base "$CUDA_BASE" \
    && python3 scripts/check_no_weights.py /opt/ggml

# Portable artifact: headers, static libraries, CMake exports, metadata, license.
# No compiler, build tree, Python, application or model weights in this image.
FROM scratch AS ggml-deps
COPY --from=ggml-deps-build /opt/ggml /opt/ggml
LABEL org.opencontainers.image.source="https://github.com/hangry-labs/yue2" \
    org.opencontainers.image.title="YuE2 GGML build dependency"

# Application stages: dependency fingerprint ends here.
FROM cuda-toolchain AS app-deps
WORKDIR /dependency
COPY cmake/app-deps.cmake cmake/app-deps.cmake
COPY cmake/app-deps/ cmake/app-deps/
COPY docker/app-deps.json docker/app-deps.json
RUN cmake -S cmake/app-deps -B /app-deps-build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/yue-deps -DCMAKE_INSTALL_LIBDIR=lib \
    && cmake --build /app-deps-build --parallel 4 \
    && cmake --install /app-deps-build \
    && rm -rf /app-deps-build

FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY tests/web/ /tests/web/
COPY VERSION /VERSION
ARG SOURCE_REVISION=unknown
RUN export YUE2_VERSION="$(cat /VERSION) ($SOURCE_REVISION)" \
    && npm run check && npm test && npm run lint && npm run build \
    && mkdir /web-licenses \
    && cp node_modules/svelte/LICENSE.md /web-licenses/svelte-MIT.txt \
    && cp node_modules/@lucide/svelte/LICENSE /web-licenses/lucide.txt \
    && cp node_modules/yaml/LICENSE /web-licenses/yaml-ISC.txt

FROM scratch AS source
COPY CMakeLists.txt VERSION LICENSE THIRD_PARTY_NOTICES.md /
COPY cmake/ /cmake/
COPY docker/ggml-source.json /docker/ggml-source.json
COPY docker/app-deps.json /docker/app-deps.json
COPY src/ /src/
COPY vendor/ /vendor/
COPY tests/ /tests/
COPY web/public/ /web/public/

FROM ubuntu:24.04 AS cpu-checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake ninja-build g++ git python3 ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY --from=source / /src/
COPY scripts/smoke_binaries.py /smoke_binaries.py
ARG SOURCE_REVISION=unknown
RUN --mount=type=cache,id=yue2-native-cpu,target=/build,sharing=locked \
    cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_NATIVE=OFF \
    -DBUILD_SHARED_LIBS=OFF -DYUE2_REVISION="$SOURCE_REVISION" \
    && cmake --build /build --parallel 4 \
    && python3 /smoke_binaries.py /build \
    && python3 tests/audio/check_formats.py /build/audio-formats-check \
    && python3 tests/api/check_requests.py /build/music-api-check \
    && python3 tests/mcp/check_protocol.py /build/mcp-check \
    && python3 tests/server/check_runtime.py /build/server-check

# A digest-pinned registry artifact can replace the source dependency stage.
FROM ${GGML_DEPS_IMAGE} AS selected-ggml
FROM cuda-toolchain AS build
WORKDIR /src
COPY --from=source / /src/
COPY --from=web /web/public/index.html.gz /src/web/public/index.html.gz
COPY --from=selected-ggml /opt/ggml /opt/ggml
COPY --from=app-deps /opt/yue-deps /opt/yue-deps
COPY Dockerfile /src/Dockerfile
COPY docker/ggml-deps.json /src/docker/ggml-deps.json
COPY scripts/ggml_deps.py scripts/check_no_weights.py /src/scripts/
ARG SOURCE_REVISION=unknown
ARG CUDA_BASE
ARG CUDA_ARCHITECTURES="75-virtual;80-virtual;86-real;89-real;120a-real"
ARG BUILD_JOBS=4
RUN --mount=type=cache,id=yue2-native-app,target=/build,sharing=locked \
    --mount=type=cache,id=yue2-ccache,target=/root/.cache/ccache,sharing=locked \
    python3 scripts/ggml_deps.py verify --architectures "$CUDA_ARCHITECTURES" --cuda-base "$CUDA_BASE" \
    && cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DYUE2_GGML_PREFIX=/opt/ggml \
    -DYUE2_APP_DEPS_PREFIX=/opt/yue-deps \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
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
    && cp /opt/ggml/licenses/ggml-MIT.txt /out/licenses/ggml-MIT.txt \
    && cp /opt/ggml/yue2-ggml.json /out/licenses/ \
    && cp /opt/yue-deps/licenses/* /out/licenses/ \
    && cp /opt/yue-deps/share/yue2-app-deps/app-deps.json /out/licenses/

FROM nvidia/cuda:12.9.1-runtime-ubuntu24.04 AS runtime-unchecked
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libstdc++6 curl ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home yue \
    && mkdir -p /models /output /adapters \
    && chown yue:yue /output /adapters \
    && mkdir -p /opt/yue/licenses \
    && cp /usr/share/doc/ffmpeg/copyright /opt/yue/licenses/ffmpeg.txt \
    && ffmpeg -v error -version
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
