# Generate a build fingerprint for the Japanese executable at *build* time.
# This runs for every build, not only CMake configure, so Git changes are seen.
# Write through copy_if_different to avoid unnecessary native recompilation.
cmake_minimum_required(VERSION 3.20)

if(NOT DEFINED GOEMON_SOURCE_DIR OR NOT DEFINED GOEMON_OUTPUT)
    message(FATAL_ERROR "GOEMON_SOURCE_DIR and GOEMON_OUTPUT are required")
endif()

set(git_sha "unknown")
set(git_dirty 0)
find_program(GIT_EXECUTABLE NAMES git)
if(GIT_EXECUTABLE)
    execute_process(
        COMMAND "${GIT_EXECUTABLE}" -C "${GOEMON_SOURCE_DIR}" rev-parse --short=10 HEAD
        RESULT_VARIABLE git_result
        OUTPUT_VARIABLE candidate_sha
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET)
    if(git_result EQUAL 0 AND candidate_sha MATCHES "^[0-9a-fA-F]+$")
        set(git_sha "${candidate_sha}")
        execute_process(
            COMMAND "${GIT_EXECUTABLE}" -C "${GOEMON_SOURCE_DIR}" status --porcelain --untracked-files=no
            RESULT_VARIABLE status_result
            OUTPUT_VARIABLE status_text
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET)
        if(status_result EQUAL 0 AND NOT status_text STREQUAL "")
            set(git_dirty 1)
        endif()
    endif()
endif()

get_filename_component(out_dir "${GOEMON_OUTPUT}" DIRECTORY)
file(MAKE_DIRECTORY "${out_dir}")
set(content "#pragma once\n#define GOEMON_JP_BUILD_COMMIT \"${git_sha}\"\n#define GOEMON_JP_BUILD_DIRTY ${git_dirty}\n")
file(WRITE "${GOEMON_OUTPUT}.tmp" "${content}")
execute_process(
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${GOEMON_OUTPUT}.tmp" "${GOEMON_OUTPUT}"
    RESULT_VARIABLE copy_result)
file(REMOVE "${GOEMON_OUTPUT}.tmp")
if(NOT copy_result EQUAL 0)
    message(FATAL_ERROR "Could not write JP build fingerprint")
endif()
