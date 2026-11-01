cmake_minimum_required(VERSION 3.19)
project(Yue2GGML LANGUAGES C CXX)

# Keep the same ABI and compiler definitions as the embedded source build.
set(CMAKE_CXX_STANDARD 17)
include(../ggml-abi.cmake)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_CUDA ON CACHE BOOL "" FORCE)
set(GGML_VULKAN OFF CACHE BOOL "" FORCE)
set(GGML_CUDA_GRAPHS ON CACHE BOOL "" FORCE)
set(GGML_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
include(../ggml-source.cmake)
yue2_fetch_ggml(GGML_SOURCE_DIR)
add_subdirectory("${GGML_SOURCE_DIR}" ggml)

# The upstream PUBLIC_HEADER list is relative to its own source directory.
# This second install rule lives here, so use absolute paths for both rules.
get_target_property(ggml_public_headers ggml PUBLIC_HEADER)
list(TRANSFORM ggml_public_headers PREPEND "${GGML_SOURCE_DIR}/")
set_target_properties(ggml PROPERTIES PUBLIC_HEADER "${ggml_public_headers}")

# Export the actual targets so private static-library dependencies (CUDA,
# NCCL, OpenMP, dl, m) and public compile definitions survive installation.
install(TARGETS ggml ggml-base ggml-cpu ggml-cuda
    EXPORT Yue2GGMLTargets ARCHIVE DESTINATION lib PUBLIC_HEADER DESTINATION include)
install(EXPORT Yue2GGMLTargets NAMESPACE Yue2:: DESTINATION lib/cmake/Yue2GGML)
include(CMakePackageConfigHelpers)
configure_package_config_file(Yue2GGMLConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/Yue2GGMLConfig.cmake"
    INSTALL_DESTINATION lib/cmake/Yue2GGML)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/Yue2GGMLConfig.cmake"
    "${GGML_SOURCE_DIR}/cmake/FindNCCL.cmake" DESTINATION lib/cmake/Yue2GGML)
install(FILES "${GGML_SOURCE_DIR}/LICENSE" DESTINATION licenses RENAME ggml-MIT.txt)
