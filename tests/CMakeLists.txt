# Reference parity binaries are available for optional model-dependent checks.
add_subdirectory(parity)

# Model-free planning/retry checks, not shipped in the runtime image.
add_executable(score-check planning/score-check.cpp ../src/request.cpp)
target_include_directories(score-check PRIVATE ${CMAKE_SOURCE_DIR}/src)
target_link_libraries(score-check PRIVATE yyjson)
