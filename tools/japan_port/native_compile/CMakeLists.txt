cmake_minimum_required(VERSION 3.20)
project(GoemonJapanGeneratedFunctions LANGUAGES C CXX)

# Deliberately independent of the existing USA CMake executable and patches.
# All game-derived C is generated locally and is never checked into Git.
set(GOEMON_JAPAN_GENERATED "" CACHE PATH "Private N64Recomp output containing funcs_*.c")
set(GOEMON_N64RECOMP_INCLUDE "" CACHE PATH "Pinned N64Recomp include dir containing recomp.h")
set(GOEMON_PORT_INCLUDE "" CACHE PATH "Goemon64Recomp include dir containing trace.h")

foreach(required_dir GOEMON_JAPAN_GENERATED GOEMON_N64RECOMP_INCLUDE GOEMON_PORT_INCLUDE)
  if(NOT IS_DIRECTORY "${${required_dir}}")
    message(FATAL_ERROR "${required_dir} must point to an existing directory")
  endif()
endforeach()

foreach(required_header "${GOEMON_N64RECOMP_INCLUDE}/recomp.h" "${GOEMON_PORT_INCLUDE}/trace.h" "${GOEMON_JAPAN_GENERATED}/funcs.h")
  if(NOT EXISTS "${required_header}")
    message(FATAL_ERROR "Required native recompilation header not found: ${required_header}")
  endif()
endforeach()

file(GLOB generated_c CONFIGURE_DEPENDS "${GOEMON_JAPAN_GENERATED}/funcs_*.c")
list(LENGTH generated_c source_count)
if(source_count LESS 140)
  message(FATAL_ERROR "Incomplete Japanese N64Recomp C output (${source_count} units; expected >= 140)")
endif()
if(NOT EXISTS "${GOEMON_JAPAN_GENERATED}/lookup.cpp")
  message(FATAL_ERROR "Missing Japanese N64Recomp lookup.cpp")
endif()
if(NOT EXISTS "${GOEMON_JAPAN_GENERATED}/recomp_overlays.inl")
  message(FATAL_ERROR "Missing Japanese N64Recomp overlay metadata")
endif()

add_library(GoemonRecompiledJapan STATIC ${generated_c} "${GOEMON_JAPAN_GENERATED}/lookup.cpp")
set_target_properties(GoemonRecompiledJapan PROPERTIES
  C_STANDARD 17
  C_STANDARD_REQUIRED ON
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
)
target_include_directories(GoemonRecompiledJapan PRIVATE
  "${GOEMON_JAPAN_GENERATED}"
  "${GOEMON_N64RECOMP_INCLUDE}"
  "${GOEMON_PORT_INCLUDE}"
)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(GoemonRecompiledJapan PRIVATE
    -fno-strict-aliasing
    -Wno-unused-variable
    -Wno-unused-but-set-variable
  )
endif()

message(STATUS "Japanese native C objects: ${source_count} translation units")
message(STATUS "This static library alone is not a playable PC executable.")
