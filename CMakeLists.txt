cmake_minimum_required(VERSION 3.19...3.28)
project(yue2-ggml LANGUAGES C CXX)

# Keep source-built dependencies aligned with their existing C++17 artifacts.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

file(STRINGS "${CMAKE_SOURCE_DIR}/VERSION" YUE2_APP_VERSION LIMIT_COUNT 1)
set(YUE2_REVISION "" CACHE STRING "Source revision for builds without Git metadata")

# version.h: embed git commit hash into all binaries.
# runs on every build, only rewrites if the hash changed.
set(VERSION_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/version.h")
add_custom_target(version ALL
    COMMAND "${CMAKE_COMMAND}" "-DSRC_DIR=${CMAKE_CURRENT_SOURCE_DIR}" "-DOUTPUT=${VERSION_OUTPUT}"
            "-DAPP_VERSION=${YUE2_APP_VERSION}" "-DREVISION=${YUE2_REVISION}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/version.cmake"
    BYPRODUCTS "${VERSION_OUTPUT}"
    COMMENT "Checking git version"
)

# pthread: required explicitly on older glibc (< 2.34) where libpthread
# is not merged into libc. Modern distros link it implicitly but aarch64
# and older x86_64 toolchains need the explicit dependency.
find_package(Threads REQUIRED)

# Suppress MSVC fopen/sprintf deprecation warnings
if(MSVC)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
endif()

# Put executables and backend .so in the same directory (build root).
# Without this, ggml defaults to bin/ for .so but executables stay in root,
# and ggml_backend_load_all() can't find the backends at runtime.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

include(cmake/ggml-abi.cmake)

# CUDA architectures: cover Turing to Blackwell for distributed binaries.
# Users can override with -DCMAKE_CUDA_ARCHITECTURES=native for local builds.
if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
    find_package(CUDAToolkit QUIET)
    if(CUDAToolkit_FOUND AND CUDAToolkit_VERSION VERSION_GREATER_EQUAL "12.8")
        set(CMAKE_CUDA_ARCHITECTURES "75-virtual;80-virtual;86-real;89-real;120a-real;121a-real")
    else()
        set(CMAKE_CUDA_ARCHITECTURES "75-virtual;80-virtual;86-real;89-real")
    endif()
endif()

# Source builds fetch the pinned official release; prebuilt builds need no source.
# CUDA graphs default on: standalone ggml ships them off. Overridable with
# -DGGML_CUDA_GRAPHS=OFF or at runtime with GGML_CUDA_DISABLE_GRAPHS=1.
if(NOT DEFINED GGML_CUDA_GRAPHS)
    set(GGML_CUDA_GRAPHS_DEFAULT ON)
endif()
set(YUE2_GGML_PREFIX "" CACHE PATH "Prebuilt Yue2 GGML dependency installation")
if(YUE2_GGML_PREFIX)
    find_package(Yue2GGML CONFIG REQUIRED PATHS "${YUE2_GGML_PREFIX}/lib/cmake/Yue2GGML" NO_DEFAULT_PATH)
    foreach(component ggml ggml-base ggml-cpu ggml-cuda)
        add_library(${component} ALIAS Yue2::${component})
    endforeach()
    set(GGML_CUDA ON)
    message(STATUS "Using prebuilt Yue2 GGML: ${YUE2_GGML_PREFIX}")
else()
    include(cmake/ggml-source.cmake)
    yue2_fetch_ggml(GGML_SOURCE_DIR)
    add_subdirectory(${GGML_SOURCE_DIR} ggml)
endif()

# HTTP, JSON and MP3 decoding from pinned upstream sources or installed targets.
include(cmake/app-deps.cmake)

# Application tools and parity harnesses use C++20; dependencies keep C++17.
set(CMAKE_CXX_STANDARD 20)
message(STATUS "YuE2 application C++ standard: ${CMAKE_CXX_STANDARD}")

# Shared compile options and ggml linkage
macro(link_ggml_backends target)
    target_include_directories(${target} PRIVATE
        ${CMAKE_SOURCE_DIR}/src
        ${CMAKE_SOURCE_DIR}
        ${CMAKE_BINARY_DIR}
    )
    # Imported GGML targets propagate their installed include directory.
    if(NOT YUE2_GGML_PREFIX)
        target_include_directories(${target} SYSTEM PRIVATE ${GGML_SOURCE_DIR}/include)
    endif()
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /wd4100 /wd4505)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wshadow -Wconversion
                              -Wno-unused-parameter -Wno-unused-function -Wno-sign-conversion)
    endif()
    target_link_libraries(${target} PRIVATE ggml Threads::Threads minimp3)
    if(TARGET ggml-base)
        target_link_libraries(${target} PRIVATE ggml-base)
    endif()
    foreach(backend cpu blas cuda metal vulkan sycl)
        if(TARGET ggml-${backend})
            get_target_property(CURRENT_BACKEND_TYPE ggml-${backend} TYPE)
            if (CURRENT_BACKEND_TYPE STREQUAL "MODULE_LIBRARY")
                # DL mode: backend is loaded at runtime via dlopen,
                # skip all link-time deps.
                continue()
            endif()
            target_link_libraries(${target} PRIVATE ggml-${backend})
        endif()
    endforeach()

    # SYCL links its runtime PRIVATE, consumers need -fsycl to resolve libsycl.so
    if(TARGET ggml-sycl AND GGML_SYCL)
        target_link_options(${target} PRIVATE -fsycl)
    endif()
    add_dependencies(${target} version)
endmacro()

# yue-plan: symbolic planning stage (request -> ABC score)
add_executable(yue-plan src/cli/yue-plan.cpp src/request.cpp)
target_link_libraries(yue-plan PRIVATE yyjson)
link_ggml_backends(yue-plan)

# yue-transcribe: audio to score (SheetSage2 transcriber)
add_executable(yue-transcribe src/cli/yue-transcribe.cpp)
target_link_libraries(yue-transcribe PRIVATE yyjson)
link_ggml_backends(yue-transcribe)

# yue-tokenize: audio to semantic codes (audio tokenizer)
add_executable(yue-tokenize src/cli/yue-tokenize.cpp)
target_link_libraries(yue-tokenize PRIVATE yyjson)
link_ggml_backends(yue-tokenize)

# yue-synth: full pipeline (score -> semantic -> flow matching -> VAE -> audio)
add_executable(yue-synth src/cli/yue-synth.cpp src/request.cpp src/model-store.cpp)
target_link_libraries(yue-synth PRIVATE yyjson)
link_ggml_backends(yue-synth)

# webui: convert web/public/index.html.gz to a C header for embedding.
# the .gz is committed to git so the C++ build works without npm.
# to update: cd web && npm ci && npm run build, then rebuild yue-server.
set(WEBUI_INPUT "${CMAKE_CURRENT_SOURCE_DIR}/web/public/index.html.gz")
set(WEBUI_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/index.html.gz.hpp")
add_custom_command(
    OUTPUT "${WEBUI_OUTPUT}"
    COMMAND "${CMAKE_COMMAND}" "-DINPUT=${WEBUI_INPUT}" "-DOUTPUT=${WEBUI_OUTPUT}" -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/xxd.cmake"
    DEPENDS "${WEBUI_INPUT}"
    COMMENT "Embedding webui into index.html.gz.hpp"
)
set_source_files_properties(${WEBUI_OUTPUT} PROPERTIES GENERATED TRUE)

# yue-server: HTTP server (single slot job queue + embedded webui)
set(OPENAPI_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/openapi.json.hpp")
add_custom_command(OUTPUT "${OPENAPI_OUTPUT}"
    COMMAND "${CMAKE_COMMAND}" "-DINPUT=${CMAKE_SOURCE_DIR}/src/api/openapi.json" "-DOUTPUT=${OPENAPI_OUTPUT}"
            -P "${CMAKE_SOURCE_DIR}/cmake/xxd.cmake"
    DEPENDS "${CMAKE_SOURCE_DIR}/src/api/openapi.json" "${CMAKE_SOURCE_DIR}/cmake/xxd.cmake")
set_source_files_properties(${OPENAPI_OUTPUT} PROPERTIES GENERATED TRUE)
set(SKILL_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/songwriting-skill.hpp")
add_custom_command(OUTPUT "${SKILL_OUTPUT}"
    COMMAND "${CMAKE_COMMAND}" "-DINPUT=${CMAKE_SOURCE_DIR}/src/agent/skills/songwriting/SKILL.md" "-DOUTPUT=${SKILL_OUTPUT}"
            -P "${CMAKE_SOURCE_DIR}/cmake/xxd.cmake"
    DEPENDS "${CMAKE_SOURCE_DIR}/src/agent/skills/songwriting/SKILL.md" "${CMAKE_SOURCE_DIR}/cmake/xxd.cmake")
set_source_files_properties(${SKILL_OUTPUT} PROPERTIES GENERATED TRUE)
add_executable(yue-server src/cli/yue-server.cpp src/request.cpp src/model-store.cpp src/system-gpu.cpp ${WEBUI_OUTPUT} ${OPENAPI_OUTPUT} ${SKILL_OUTPUT})
target_include_directories(yue-server PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(yue-server PRIVATE yyjson httplib ${CMAKE_DL_LIBS})
if(WIN32)
    target_link_libraries(yue-server PRIVATE bcrypt)
endif()
if(GGML_CUDA AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
    find_package(CUDAToolkit REQUIRED)
    target_include_directories(yue-server PRIVATE ${CUDAToolkit_INCLUDE_DIRS})
    target_compile_definitions(yue-server PRIVATE YUE2_NVML=1)
endif()
link_ggml_backends(yue-server)

# neural-codec: Oobleck VAE neural audio codec (audio <-> latent)
add_executable(neural-codec src/cli/neural-codec.cpp)
link_ggml_backends(neural-codec)

# mp3-codec: MP3 encoder/decoder (standalone, no ggml needed)
# The inherited MP3 encoder is project source under src/codecs/mp3/.
add_executable(mp3-codec src/cli/mp3-codec.cpp)
target_include_directories(mp3-codec PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_BINARY_DIR}
)
add_dependencies(mp3-codec version)
if(MSVC)
    target_compile_options(mp3-codec PRIVATE /W4 /wd4100 /wd4505)
else()
    target_compile_options(mp3-codec PRIVATE -Wall -Wextra -Wconversion
                          -Wno-unused-parameter -Wno-unused-function -Wno-sign-conversion)
    target_link_libraries(mp3-codec PRIVATE m)
endif()
target_link_libraries(mp3-codec PRIVATE Threads::Threads minimp3)

# quantize: GGUF requantizer (BF16 -> K-quants)
add_executable(quantize src/cli/quantize.cpp)
link_ggml_backends(quantize)

add_subdirectory(tests)

add_executable(music-api-check tests/api/translate.cpp src/request.cpp)
target_include_directories(music-api-check PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(music-api-check PRIVATE yyjson)

add_executable(mcp-check tests/mcp/server.cpp src/request.cpp ${SKILL_OUTPUT})
target_include_directories(mcp-check PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(mcp-check PRIVATE yyjson httplib Threads::Threads)
if(WIN32)
    target_link_libraries(mcp-check PRIVATE bcrypt)
endif()

# Model-free codec integration checks run in the CPU CI image, never the runtime.
add_executable(audio-formats-check tests/audio/formats.cpp)
target_include_directories(audio-formats-check PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(audio-formats-check PRIVATE minimp3 Threads::Threads)
if(NOT MSVC)
    target_link_libraries(audio-formats-check PRIVATE m)
    target_compile_options(audio-formats-check PRIVATE -Wall -Wextra -Wconversion -Wno-unused-function)
endif()
