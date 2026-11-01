# Download only for source builds. Application builds import installed headers
# and libraries from the precompiled dependency without fetching GGML again.
include_guard(GLOBAL)
include(FetchContent)
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

function(yue2_fetch_ggml output)
    file(READ "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../docker/ggml-source.json" lock)
    string(JSON url GET "${lock}" url)
    string(JSON checksum GET "${lock}" sha256)
    FetchContent_Declare(yue2_ggml URL "${url}" URL_HASH "SHA256=${checksum}")
    FetchContent_GetProperties(yue2_ggml)
    if(NOT yue2_ggml_POPULATED)
        FetchContent_Populate(yue2_ggml)
    endif()
    set(${output} "${yue2_ggml_SOURCE_DIR}" PARENT_SCOPE)
endfunction()
