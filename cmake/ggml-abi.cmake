# Shared by source builds, the dependency artifact and its application consumer.
# Tensor names can exceed the upstream GGML_MAX_NAME of 64.
add_compile_definitions(GGML_MAX_NAME=128)

# SYCL device code cannot resolve the fortified memcpy replacement.
if(NOT MSVC AND NOT GGML_SYCL)
    add_compile_definitions(_FORTIFY_SOURCE=2)
endif()
