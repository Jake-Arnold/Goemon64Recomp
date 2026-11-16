cmake_minimum_required(VERSION 3.20)

if (APPLE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Minimum OS X deployment version")
endif()

project(Goemon64Recompiled LANGUAGES C CXX)
set(CMAKE_C_STANDARD 17)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
# set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_SIMULATE_ID STREQUAL "MSVC")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-everything /W4")
endif()

# Opt out of constexpr mutex constructor on windows to prevent vcredist issues
if (WIN32)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR")
endif()

if (APPLE)
    enable_language(OBJC OBJCXX)
endif()

if (CMAKE_SYSTEM_NAME MATCHES "Linux")
    option(RECOMP_FLATPAK "Configure the build for Flatpak compatibility." OFF)
endif()

# Avoid warning about DOWNLOAD_EXTRACT_TIMESTAMP in CMake 3.24:
if (CMAKE_VERSION VERSION_GREATER_EQUAL "3.24.0")
    cmake_policy(SET CMP0135 NEW)
endif()

set (CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set (CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

if (WIN32)
    set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${PROJECT_SOURCE_DIR}/lib/")
endif()

set(RT64_STATIC TRUE)
set(RT64_SDL_WINDOW_VULKAN TRUE)

# Because 'plume' uses CMake 3.12, it ignores normal variables.
# We must set a CACHE variable to configure it.
if (CMAKE_SYSTEM_NAME MATCHES "Linux" AND RT64_SDL_WINDOW_VULKAN)
    set(SDL_VULKAN_ENABLED ON CACHE BOOL "Forcing Plume to use Vulkan on Linux" FORCE)
endif()

add_compile_definitions(HLSL_CPU)

if (RECOMP_FLATPAK)
    add_compile_definitions(RECOMP_FLATPAK)
endif()

add_subdirectory(${CMAKE_SOURCE_DIR}/lib/rt64 ${CMAKE_BINARY_DIR}/rt64)

# set(BUILD_SHARED_LIBS_SAVED "${BUILD_SHARED_LIBS}")
set(BUILD_SHARED_LIBS OFF)
SET(LUNASVG_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory(${CMAKE_SOURCE_DIR}/lib/lunasvg)
# set(BUILD_SHARED_LIBS "${BUILD_SHARED_LIBS_SAVED}")
SET(RMLUI_SVG_PLUGIN ON CACHE BOOL "" FORCE)
SET(RMLUI_TESTS_ENABLED OFF CACHE BOOL "" FORCE)
add_subdirectory(${CMAKE_SOURCE_DIR}/lib/RmlUi)
target_compile_definitions(rmlui_core PRIVATE LUNASVG_BUILD_STATIC)

add_subdirectory(${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime)

target_include_directories(rt64 PRIVATE ${CMAKE_BINARY_DIR}/rt64/src)

# RecompiledFuncs - Library containing the primary recompiler output
add_library(RecompiledFuncs STATIC)

target_compile_options(RecompiledFuncs PRIVATE
    # -Wno-unused-but-set-variable
    -fno-strict-aliasing
    -Wno-unused-variable
    -Wno-implicit-function-declaration
)

target_include_directories(RecompiledFuncs PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/ultramodern/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/librecomp/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/N64Recomp/include
)

file(GLOB FUNC_C_SOURCES ${CMAKE_SOURCE_DIR}/RecompiledFuncs/*.c)
file(GLOB FUNC_CXX_SOURCES ${CMAKE_SOURCE_DIR}/RecompiledFuncs/*.cpp)

target_sources(RecompiledFuncs PRIVATE ${FUNC_C_SOURCES} ${FUNC_CXX_SOURCES})

# PatchesLib - Library containing the recompiled output for any custom function patches
add_library(PatchesLib STATIC)

target_compile_options(PatchesLib PRIVATE
    # -Wno-unused-but-set-variable
    -fno-strict-aliasing
    -Wno-unused-variable
    -Wno-implicit-function-declaration
)

target_include_directories(PatchesLib PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/ultramodern/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/librecomp/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/N64Recomp/include
)

target_sources(PatchesLib PRIVATE
    ${CMAKE_SOURCE_DIR}/RecompiledPatches/patches.c
    ${CMAKE_SOURCE_DIR}/RecompiledPatches/patches_bin.c
)

set_source_files_properties(${CMAKE_SOURCE_DIR}/RecompiledPatches/patches.c PROPERTIES COMPILE_FLAGS -fno-strict-aliasing)

# Build patches elf
if(NOT DEFINED PATCHES_C_COMPILER)
    set(PATCHES_C_COMPILER clang)
endif()

if(NOT DEFINED PATCHES_LD)
    set(PATCHES_LD ld.lld)
endif()

add_custom_target(PatchesBin
    COMMAND ${CMAKE_COMMAND} -E env CC=${PATCHES_C_COMPILER} LD=${PATCHES_LD} make
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/patches
    BYPRODUCTS ${CMAKE_SOURCE_DIR}/patches/build/patches.elf
)

# Generate patches_bin.c from patches.bin
add_custom_command(OUTPUT ${CMAKE_SOURCE_DIR}/RecompiledPatches/patches_bin.c
    COMMAND file_to_c ${CMAKE_SOURCE_DIR}/patches/patches.bin mm_patches_bin ${CMAKE_SOURCE_DIR}/RecompiledPatches/patches_bin.c ${CMAKE_SOURCE_DIR}/RecompiledPatches/patches_bin.h
    DEPENDS ${CMAKE_SOURCE_DIR}/patches/patches.bin
)

# Recompile patches elf into patches.c and patches.bin
add_custom_command(OUTPUT
                       ${CMAKE_SOURCE_DIR}/patches/patches.bin
                       ${CMAKE_SOURCE_DIR}/RecompiledPatches/patches.c
                       ${CMAKE_SOURCE_DIR}/RecompiledPatches/recomp_overlays.inl
                       ${CMAKE_SOURCE_DIR}/RecompiledPatches/funcs.h
                   # TODO: Look into why modifying patches requires two builds to take
                   COMMAND ./N64Recomp patches.toml
                   WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
                   DEPENDS ${CMAKE_SOURCE_DIR}/patches/build/patches.elf
)

# Main executable
add_executable(Goemon64Recompiled)

set (SOURCES
    ${CMAKE_SOURCE_DIR}/src/main/main.cpp
    ${CMAKE_SOURCE_DIR}/src/main/support.cpp
    ${CMAKE_SOURCE_DIR}/src/main/register_overlays.cpp
    ${CMAKE_SOURCE_DIR}/src/main/register_patches.cpp
    ${CMAKE_SOURCE_DIR}/src/main/rt64_render_context.cpp

    ${CMAKE_SOURCE_DIR}/src/game/input.cpp
    ${CMAKE_SOURCE_DIR}/src/game/controls.cpp
    ${CMAKE_SOURCE_DIR}/src/game/config.cpp
    ${CMAKE_SOURCE_DIR}/src/game/scene_table.cpp
    ${CMAKE_SOURCE_DIR}/src/game/debug.cpp
    ${CMAKE_SOURCE_DIR}/src/game/recomp_api.cpp
    ${CMAKE_SOURCE_DIR}/src/game/recomp_actor_api.cpp
    ${CMAKE_SOURCE_DIR}/src/game/recomp_data_api.cpp
    ${CMAKE_SOURCE_DIR}/src/game/rom_decompression.cpp
    ${CMAKE_SOURCE_DIR}/src/game/unknown_symbols.cpp

    ${CMAKE_SOURCE_DIR}/src/ui/ui_renderer.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_state.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_launcher.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_config.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_prompt.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_config_sub_menu.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_color_hack.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_rml_hacks.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_elements.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_mod_details_panel.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_mod_installer.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_mod_menu.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_api.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_api_events.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_api_images.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/ui_utils.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/util/hsv.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/core/ui_context.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_button.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_clickable.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_container.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_element.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_image.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_label.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_radio.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_scroll_container.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_slider.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_span.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_style.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_text_input.cpp
    ${CMAKE_SOURCE_DIR}/src/ui/elements/ui_toggle.cpp

    ${CMAKE_SOURCE_DIR}/rsp/aspMain.cpp

    ${CMAKE_SOURCE_DIR}/lib/RmlUi/Backends/RmlUi_Platform_SDL.cpp
)

if (APPLE)
    list(APPEND SOURCES ${CMAKE_SOURCE_DIR}/src/main/support_apple.mm)
endif()

target_include_directories(Goemon64Recompiled PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/N64Recomp/include
    ${CMAKE_SOURCE_DIR}/lib/concurrentqueue
    ${CMAKE_SOURCE_DIR}/lib/GamepadMotionHelpers
    ${CMAKE_SOURCE_DIR}/lib/RmlUi/Include
    ${CMAKE_SOURCE_DIR}/lib/RmlUi/Backends
    ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib
    ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/hlslpp/include
    ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/inc
    ${CMAKE_SOURCE_DIR}/lib/rt64/src
    ${CMAKE_SOURCE_DIR}/lib/rt64/src/rhi
    ${CMAKE_SOURCE_DIR}/lib/rt64/src/render
    ${CMAKE_SOURCE_DIR}/lib/freetype-windows-binaries/include
    ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/nativefiledialog-extended/src/include
    ${CMAKE_SOURCE_DIR}/lib/SlotMap
    ${CMAKE_BINARY_DIR}/shaders
    ${CMAKE_CURRENT_BINARY_DIR}
)

if(CMAKE_SIZEOF_VOID_P EQUAL 8 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
    target_compile_options(Goemon64Recompiled PRIVATE
        -march=nehalem
        -fno-strict-aliasing
        -fms-extensions
    )
else()
    target_compile_options(Goemon64Recompiled PRIVATE
        -fno-strict-aliasing
        -fms-extensions
    )
endif()

if (MSVC)
    # Disable identical code folding, since this breaks mod function patching as multiple functions can get merged into one.
    target_link_options(Goemon64Recompiled PRIVATE /OPT:NOICF)
elseif (APPLE)
    # Use a wrapper around ld64 that respects segprot's `max_prot` value in order
    # to make our executable memory writable (required for mod function patching)
    target_link_options(Goemon64Recompiled PRIVATE
        "-fuse-ld=${CMAKE_SOURCE_DIR}/.github/macos/ld64"
    )
endif()

if (WIN32)
    include(FetchContent)

    if (DEFINED ENV{SDL2_VERSION})
        set(SDL2_VERSION $ENV{SDL2_VERSION})
    else()
        set(SDL2_VERSION "2.30.3")
    endif()

    # Fetch SDL2 on windows
    FetchContent_Declare(
        sdl2
        URL https://github.com/libsdl-org/SDL/releases/download/release-${SDL2_VERSION}/SDL2-devel-${SDL2_VERSION}-VC.zip
    )
    FetchContent_MakeAvailable(sdl2)
    target_include_directories(Goemon64Recompiled PRIVATE
        ${sdl2_SOURCE_DIR}/include
    )
    target_link_directories(Goemon64Recompiled PRIVATE
        ${sdl2_SOURCE_DIR}/lib/x64
    )

    # Copy SDL2 and dxc DLLs to output folder as post build step
    add_custom_command(TARGET Goemon64Recompiled POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${sdl2_SOURCE_DIR}/lib/x64/SDL2.dll"
            "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxil.dll"
            "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxcompiler.dll"
            $<TARGET_FILE_DIR:Goemon64Recompiled>)

    set_target_properties(
        Goemon64Recompiled
        PROPERTIES
            LINK_FLAGS_DEBUG "/SUBSYSTEM:CONSOLE"
            LINK_FLAGS_RELEASE "/SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup"
            LINK_FLAGS_RELWITHDEBINFO "/SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup"
            LINK_FLAGS_MINSIZEREL "/SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup"
    )

    target_sources(Goemon64Recompiled PRIVATE ${CMAKE_SOURCE_DIR}/icons/app.rc)
    target_link_libraries(Goemon64Recompiled PRIVATE SDL2 Winmm.lib)
endif()

if (APPLE)
    find_package(SDL2 REQUIRED)
    target_include_directories(Goemon64Recompiled PRIVATE ${SDL2_INCLUDE_DIRS})

    set(CMAKE_THREAD_PREFER_PTHREAD TRUE)
    set(THREADS_PREFER_PTHREAD_FLAG TRUE)
    find_package(Threads REQUIRED)

    target_link_libraries(Goemon64Recompiled PRIVATE ${CMAKE_DL_LIBS} Threads::Threads SDL2::SDL2)

    include(${CMAKE_SOURCE_DIR}/.github/macos/apple_bundle.cmake)
endif()

if (CMAKE_SYSTEM_NAME MATCHES "Linux")
    find_package(SDL2 REQUIRED)

    add_compile_definitions("RT64_SDL_WINDOW_VULKAN")

    # Generate icon_bytes.c from the app icon PNG.
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/icon_bytes.c ${CMAKE_CURRENT_BINARY_DIR}/icon_bytes.h
        COMMAND file_to_c ${CMAKE_SOURCE_DIR}/icons/512.png icon_bytes ${CMAKE_CURRENT_BINARY_DIR}/icon_bytes.c ${CMAKE_CURRENT_BINARY_DIR}/icon_bytes.h
        DEPENDS ${CMAKE_SOURCE_DIR}/icons/512.png
    )
    target_sources(Goemon64Recompiled PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/icon_bytes.c)

    message(STATUS "SDL2_FOUND = ${SDL2_FOUND}")
    message(STATUS "SDL2_INCLUDE_DIRS = ${SDL2_INCLUDE_DIRS}")

    target_include_directories(Goemon64Recompiled PRIVATE ${SDL2_INCLUDE_DIRS})

    find_package(Freetype REQUIRED)

    message(STATUS "FREETYPE_FOUND = ${FREETYPE_FOUND}")
    message(STATUS "FREETYPE_INCLUDE_DIRS = ${FREETYPE_INCLUDE_DIRS}")
    message(STATUS "FREETYPE_LIBRARIES = ${FREETYPE_LIBRARIES}")

    include_directories(${FREETYPE_LIBRARIES})
    target_link_libraries(Goemon64Recompiled PRIVATE ${FREETYPE_LIBRARIES} SDL2::SDL2)

    set(CMAKE_THREAD_PREFER_PTHREAD TRUE)
    set(THREADS_PREFER_PTHREAD_FLAG TRUE)
    find_package(Threads REQUIRED)

    target_link_libraries(Goemon64Recompiled PRIVATE "-latomic -static-libstdc++" ${CMAKE_DL_LIBS} Threads::Threads)
endif()

target_link_libraries(Goemon64Recompiled PRIVATE
    PatchesLib
    RecompiledFuncs
    librecomp
    ultramodern
    rt64
    RmlUi::Core
    RmlUi::Debugger
    nfd
    lunasvg
)

# TODO fix the rt64 CMake script so that this doesn't need to be duplicated here
# For DXC
set (DXC_COMMON_OPTS "-I${PROJECT_SOURCE_DIR}/src")
set (DXC_DXIL_OPTS "-Wno-ignored-attributes")
set (DXC_SPV_OPTS "-spirv" "-fspv-target-env=vulkan1.0" "-fvk-use-dx-layout")
set (DXC_PS_OPTS "${DXC_COMMON_OPTS}" "-E" "PSMain" "-T ps_6_0" "-D DYNAMIC_RENDER_PARAMS")
set (DXC_VS_OPTS "${DXC_COMMON_OPTS}" "-E" "VSMain" "-T vs_6_0" "-D DYNAMIC_RENDER_PARAMS" "-fvk-invert-y")
set (DXC_CS_OPTS "${DXC_COMMON_OPTS}" "-E" "CSMain" "-T cs_6_0")
set (DXC_GS_OPTS "${DXC_COMMON_OPTS}" "-E" "GSMain" "-T gs_6_0")
set (DXC_RT_OPTS "${DXC_COMMON_OPTS}" "-D" "RT_SHADER" "-T" "lib_6_3" "-fspv-target-env=vulkan1.1spirv1.4" "-fspv-extension=SPV_KHR_ray_tracing" "-fspv-extension=SPV_EXT_descriptor_indexing")

if (${WIN32})
    set (DXC "${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxc.exe")
    add_compile_definitions(NOMINMAX)
else()
    if (APPLE)
        # Apple's binary is universal, so it'll work on both x86_64 and arm64
        set (DXC "DYLD_LIBRARY_PATH=${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/lib/arm64" "${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/arm64/dxc-macos")
        if(CMAKE_SIZEOF_VOID_P EQUAL 8 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
            set(SPIRVCROSS "DYLD_LIBRARY_PATH=${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/spirv-cross/lib/x64" "${PROJECT_SOURCE_DIR}/lib/rt64//src/contrib/spirv-cross/bin/x64/spirv-cross")
        else()
            set(SPIRVCROSS "DYLD_LIBRARY_PATH=${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/spirv-cross/lib/arm64" "${PROJECT_SOURCE_DIR}/lib/rt64//src/contrib/spirv-cross/bin/x64/spirv-cross")
        endif()
    else()
        if(CMAKE_SIZEOF_VOID_P EQUAL 8 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
            set (DXC "LD_LIBRARY_PATH=${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/lib/x64" "${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxc-linux")
        else()
            set (DXC "LD_LIBRARY_PATH=${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/lib/arm64" "${PROJECT_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/arm64/dxc-linux")
        endif()
    endif()
endif()

build_vertex_shader(Goemon64Recompiled "shaders/InterfaceVS.hlsl" "shaders/InterfaceVS.hlsl")
build_pixel_shader(Goemon64Recompiled "shaders/InterfacePS.hlsl" "shaders/InterfacePS.hlsl")

# Embed all .nrm files in the "mods" directory
file(GLOB NRM_FILES "${CMAKE_SOURCE_DIR}/mods/*.nrm")

set(GENERATED_NRM_SOURCES "")

foreach(NRM_FILE ${NRM_FILES})
    get_filename_component(NRM_NAME ${NRM_FILE} NAME_WE)
    set(OUT_C "${CMAKE_CURRENT_BINARY_DIR}/mods/${NRM_NAME}.c")
    set(OUT_H "${CMAKE_CURRENT_BINARY_DIR}/mods/${NRM_NAME}.h")

    add_custom_command(
        OUTPUT ${OUT_C} ${OUT_H}
        COMMAND file_to_c ${NRM_FILE} ${NRM_NAME} ${OUT_C} ${OUT_H}
        DEPENDS ${NRM_FILE}
    )

    list(APPEND GENERATED_NRM_SOURCES ${OUT_C})
endforeach()

target_sources(Goemon64Recompiled PRIVATE ${GENERATED_NRM_SOURCES})

target_sources(Goemon64Recompiled PRIVATE ${SOURCES})

set_property(TARGET Goemon64Recompiled PROPERTY VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")

if(CMAKE_EXPORT_COMPILE_COMMANDS)
    execute_process(COMMAND ${CMAKE_COMMAND} -E create_symlink
        "${CMAKE_BINARY_DIR}/compile_commands.json"
        "${CMAKE_SOURCE_DIR}/compile_commands.json"
    )
endif()
# Experimental Japanese native executable. An opt-in separate target ensures
# the original USA CMake target and its patches remain unchanged.
option(GOEMON_BUILD_JAPAN "Build isolated Japanese Goemon PC executable" OFF)
set(GOEMON_JAPAN_GENERATED "" CACHE PATH "Private JP N64Recomp output; never commit")
set(GOEMON_JAPAN_STATIC_LIB "" CACHE FILEPATH "Private JP recompiled archive; never commit")
if(GOEMON_BUILD_JAPAN)
    if(NOT EXISTS "${GOEMON_JAPAN_GENERATED}/recomp_overlays.inl"
       OR NOT EXISTS "${GOEMON_JAPAN_GENERATED}/funcs.h")
        message(FATAL_ERROR "Japanese generated overlay metadata is required")
    endif()
    if(NOT EXISTS "${GOEMON_JAPAN_STATIC_LIB}")
        message(FATAL_ERROR "Japanese native recompilation archive is required")
    endif()
    # Experimental reset prerequisite: make pinned runtime timer joinable
    # before RDRAM teardown. Opt-in, and does NOT implement a reset yet.
    option(GOEMON_JP_TIMER_STAGE1 "Enable experimental JP timer lifecycle stage" OFF)
    if(GOEMON_JP_TIMER_STAGE1)
        find_package(Python3 REQUIRED COMPONENTS Interpreter)
        set(JP_TIMER_SCRIPT "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_timer_runtime.py")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${JP_TIMER_SCRIPT}")
        set(JP_TIMER_RUNTIME_ROOT "${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime")
        set(JP_TIMER_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/jp_reset_timer_runtime")
        execute_process(
            COMMAND "${Python3_EXECUTABLE}" "${JP_TIMER_SCRIPT}"
                --runtime "${JP_TIMER_RUNTIME_ROOT}"
                --output "${JP_TIMER_GENERATED_DIR}"
            RESULT_VARIABLE JP_TIMER_PATCH_RESULT
            OUTPUT_VARIABLE JP_TIMER_PATCH_OUTPUT
            ERROR_VARIABLE JP_TIMER_PATCH_ERROR)
        if(NOT JP_TIMER_PATCH_RESULT EQUAL 0)
            message(FATAL_ERROR
                "JP reset timer source overlay failed (pinned runtime mismatch?):\n"
                "${JP_TIMER_PATCH_OUTPUT}\n${JP_TIMER_PATCH_ERROR}")
        endif()
        message(STATUS "${JP_TIMER_PATCH_OUTPUT}")

        # Replace just the two original source files in the CMake targets.
        # No files in lib/N64ModernRuntime are modified.
        get_target_property(JP_TIMER_ULTRA_SOURCES ultramodern SOURCES)
        list(FIND JP_TIMER_ULTRA_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/timer.cpp"
            JP_TIMER_SOURCE_INDEX)
        if(JP_TIMER_SOURCE_INDEX EQUAL -1)
            message(FATAL_ERROR "Original timer.cpp not found in ultramodern target")
        endif()
        list(REMOVE_ITEM JP_TIMER_ULTRA_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/timer.cpp")
        set_property(TARGET ultramodern PROPERTY SOURCES ${JP_TIMER_ULTRA_SOURCES})
        target_sources(ultramodern PRIVATE "${JP_TIMER_GENERATED_DIR}/timer.cpp")

        get_target_property(JP_TIMER_RECOMP_SOURCES librecomp SOURCES)
        list(FIND JP_TIMER_RECOMP_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/librecomp/src/recomp.cpp"
            JP_RECOMP_SOURCE_INDEX)
        if(JP_RECOMP_SOURCE_INDEX EQUAL -1)
            message(FATAL_ERROR "Original recomp.cpp not found in librecomp target")
        endif()
        list(REMOVE_ITEM JP_TIMER_RECOMP_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/librecomp/src/recomp.cpp")
        set_property(TARGET librecomp PROPERTY SOURCES ${JP_TIMER_RECOMP_SOURCES})
        target_sources(librecomp PRIVATE "${JP_TIMER_GENERATED_DIR}/recomp.cpp")
    endif()
    # Experimental JP reset stage 2: count guest OSThread host lifecycles.
    # No guest worker is stopped and no guest memory is reset at this stage.
    option(GOEMON_JP_THREAD_STAGE2 "Enable Japanese guest thread reset audit" OFF)
    option(GOEMON_JP_GUEST_STAGE3 "Enable JP guest cooperative stop primitives (disabled in UI)" OFF)
    option(GOEMON_JP_QUEUE_STAGE4 "Enable JP queue and cleaner lifecycle diagnostics" OFF)
    option(GOEMON_JP_JOIN_STAGE5 "Enable inactive guarded guest join barrier and scheduler stop gates" OFF)
    option(GOEMON_JP_HOST_STAGE6 "Enable JP native VI/RT64/RSP worker lifecycle audit" OFF)
    if(GOEMON_JP_HOST_STAGE6 AND NOT GOEMON_JP_JOIN_STAGE5)
        message(FATAL_ERROR "GOEMON_JP_HOST_STAGE6 requires GOEMON_JP_JOIN_STAGE5=ON")
    endif()
    if(GOEMON_JP_JOIN_STAGE5 AND NOT GOEMON_JP_QUEUE_STAGE4)
        message(FATAL_ERROR "GOEMON_JP_JOIN_STAGE5 requires GOEMON_JP_QUEUE_STAGE4=ON")
    endif()
    if(GOEMON_JP_QUEUE_STAGE4 AND NOT GOEMON_JP_GUEST_STAGE3)
        message(FATAL_ERROR "GOEMON_JP_QUEUE_STAGE4 requires GOEMON_JP_GUEST_STAGE3=ON")
    endif()
    if(GOEMON_JP_GUEST_STAGE3 AND NOT GOEMON_JP_THREAD_STAGE2)
        message(FATAL_ERROR "GOEMON_JP_GUEST_STAGE3 requires GOEMON_JP_THREAD_STAGE2=ON")
    endif()
    if(GOEMON_JP_THREAD_STAGE2 AND NOT GOEMON_JP_TIMER_STAGE1)
        message(FATAL_ERROR "GOEMON_JP_THREAD_STAGE2 requires GOEMON_JP_TIMER_STAGE1=ON")
    endif()
    if(GOEMON_JP_THREAD_STAGE2)
        if(GOEMON_JP_JOIN_STAGE5)
            set(JP_THREAD_SCRIPT "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_join_stage5.py")
            set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
                "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_queue_cleaner_stage4.py"
                "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_quiescence_stage3.py"
                "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_threads_runtime.py")
        elseif(GOEMON_JP_QUEUE_STAGE4)
            set(JP_THREAD_SCRIPT "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_queue_cleaner_stage4.py")
            set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
                "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_quiescence_stage3.py"
                "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_threads_runtime.py")
        elseif(GOEMON_JP_GUEST_STAGE3)
            set(JP_THREAD_SCRIPT "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_quiescence_stage3.py")
            # The stage-3 generator imports stage-2 instrumentation.
            set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
                "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_threads_runtime.py")
        else()
            set(JP_THREAD_SCRIPT "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_guest_threads_runtime.py")
        endif()
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${JP_THREAD_SCRIPT}")
        execute_process(
            COMMAND "${Python3_EXECUTABLE}" "${JP_THREAD_SCRIPT}"
                --runtime "${JP_TIMER_RUNTIME_ROOT}"
                --output "${JP_TIMER_GENERATED_DIR}"
            RESULT_VARIABLE JP_THREAD_PATCH_RESULT
            OUTPUT_VARIABLE JP_THREAD_PATCH_OUTPUT
            ERROR_VARIABLE JP_THREAD_PATCH_ERROR)
        if(NOT JP_THREAD_PATCH_RESULT EQUAL 0)
            message(FATAL_ERROR
                "JP guest-thread source audit failed (pinned runtime mismatch?):\n"
                "${JP_THREAD_PATCH_OUTPUT}\n${JP_THREAD_PATCH_ERROR}")
        endif()
        message(STATUS "${JP_THREAD_PATCH_OUTPUT}")

        get_target_property(JP_THREAD_ORIGINAL_SOURCES ultramodern SOURCES)
        list(FIND JP_THREAD_ORIGINAL_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/threads.cpp"
            JP_THREAD_SOURCE_INDEX)
        if(JP_THREAD_SOURCE_INDEX EQUAL -1)
            message(FATAL_ERROR "Original threads.cpp not found in ultramodern target")
        endif()
        list(REMOVE_ITEM JP_THREAD_ORIGINAL_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/threads.cpp")
        set_property(TARGET ultramodern PROPERTY SOURCES ${JP_THREAD_ORIGINAL_SOURCES})
        target_sources(ultramodern PRIVATE "${JP_TIMER_GENERATED_DIR}/threads.cpp")
        if(GOEMON_JP_QUEUE_STAGE4)
            get_target_property(JP_MESG_ORIGINAL_SOURCES ultramodern SOURCES)
            list(FIND JP_MESG_ORIGINAL_SOURCES
                "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/mesgqueue.cpp"
                JP_MESG_SOURCE_INDEX)
            if(JP_MESG_SOURCE_INDEX EQUAL -1)
                message(FATAL_ERROR "Original mesgqueue.cpp not found in ultramodern target")
            endif()
            list(REMOVE_ITEM JP_MESG_ORIGINAL_SOURCES
                "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/mesgqueue.cpp")
            set_property(TARGET ultramodern PROPERTY SOURCES ${JP_MESG_ORIGINAL_SOURCES})
            target_sources(ultramodern PRIVATE "${JP_TIMER_GENERATED_DIR}/mesgqueue.cpp")
            if(GOEMON_JP_JOIN_STAGE5)
                get_target_property(JP_SCHED_ORIGINAL_SOURCES ultramodern SOURCES)
                list(FIND JP_SCHED_ORIGINAL_SOURCES
                    "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/scheduling.cpp"
                    JP_SCHED_SOURCE_INDEX)
                if(JP_SCHED_SOURCE_INDEX EQUAL -1)
                    message(FATAL_ERROR "Original scheduling.cpp not found in ultramodern target")
                endif()
                list(REMOVE_ITEM JP_SCHED_ORIGINAL_SOURCES
                    "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/scheduling.cpp")
                set_property(TARGET ultramodern PROPERTY SOURCES ${JP_SCHED_ORIGINAL_SOURCES})
                target_sources(ultramodern PRIVATE "${JP_TIMER_GENERATED_DIR}/scheduling.cpp")
            endif()
        endif()
    endif()
    if(GOEMON_JP_HOST_STAGE6)
        # Build-local events.cpp; do not modify the pinned submodule.
        set(JP_HOST_SCRIPT "${CMAKE_SOURCE_DIR}/tools/japan_port/patch_native_events_stage6.py")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${JP_HOST_SCRIPT}")
        execute_process(
            COMMAND "${Python3_EXECUTABLE}" "${JP_HOST_SCRIPT}"
                --runtime "${JP_TIMER_RUNTIME_ROOT}"
                --output "${JP_TIMER_GENERATED_DIR}"
            RESULT_VARIABLE JP_HOST_PATCH_RESULT
            OUTPUT_VARIABLE JP_HOST_PATCH_OUTPUT
            ERROR_VARIABLE JP_HOST_PATCH_ERROR)
        if(NOT JP_HOST_PATCH_RESULT EQUAL 0)
            message(FATAL_ERROR
                "JP native event worker audit generation failed:\n"
                "${JP_HOST_PATCH_OUTPUT}\n${JP_HOST_PATCH_ERROR}")
        endif()
        message(STATUS "${JP_HOST_PATCH_OUTPUT}")
        get_target_property(JP_EVENT_ORIGINAL_SOURCES ultramodern SOURCES)
        list(FIND JP_EVENT_ORIGINAL_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/events.cpp"
            JP_EVENT_SOURCE_INDEX)
        if(JP_EVENT_SOURCE_INDEX EQUAL -1)
            message(FATAL_ERROR "Original events.cpp not found in ultramodern target")
        endif()
        list(REMOVE_ITEM JP_EVENT_ORIGINAL_SOURCES
            "${JP_TIMER_RUNTIME_ROOT}/ultramodern/src/events.cpp")
        set_property(TARGET ultramodern PROPERTY SOURCES ${JP_EVENT_ORIGINAL_SOURCES})
        target_sources(ultramodern PRIVATE "${JP_TIMER_GENERATED_DIR}/events.cpp")
    endif()
    # Reuse the existing frontend sources and shared shader/icon build rules.
    get_target_property(JP_SOURCES Goemon64Recompiled SOURCES)
    list(REMOVE_ITEM JP_SOURCES
        "${CMAKE_SOURCE_DIR}/src/main/register_overlays.cpp"
        "${CMAKE_SOURCE_DIR}/src/main/register_patches.cpp")
    list(APPEND JP_SOURCES
        "${CMAKE_SOURCE_DIR}/src/main/register_overlays_japan.cpp"
        "${CMAKE_SOURCE_DIR}/src/main/register_patches_japan.cpp")
    add_executable(Goemon64RecompiledJP ${JP_SOURCES})
    target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JAPAN_NATIVE)
    if(GOEMON_JP_TIMER_STAGE1)
        target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JP_TIMER_STAGE1_ACTIVE)
    endif()
    if(GOEMON_JP_THREAD_STAGE2)
        target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JP_THREAD_STAGE2_ACTIVE)
    endif()
    if(GOEMON_JP_GUEST_STAGE3)
        target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JP_GUEST_STAGE3_ACTIVE)
    endif()
    if(GOEMON_JP_QUEUE_STAGE4)
        target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JP_QUEUE_STAGE4_ACTIVE)
    endif()
    if(GOEMON_JP_JOIN_STAGE5)
        target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JP_JOIN_STAGE5_ACTIVE)
    endif()
    if(GOEMON_JP_HOST_STAGE6)
        target_compile_definitions(Goemon64RecompiledJP PRIVATE GOEMON_JP_HOST_STAGE6_ACTIVE)
    endif()
    # Regenerate the build-commit identifier on every JP build. The script
    # writes only when content changes; incremental compilation stays fast.
    set(JP_BUILD_ID_HEADER "${CMAKE_CURRENT_BINARY_DIR}/goemon_japan_build_id.h")
    add_custom_target(goemon_japan_build_id
        COMMAND "${CMAKE_COMMAND}"
            "-DGOEMON_SOURCE_DIR=${CMAKE_SOURCE_DIR}"
            "-DGOEMON_OUTPUT=${JP_BUILD_ID_HEADER}"
            -P "${CMAKE_SOURCE_DIR}/tools/japan_port/write_build_id.cmake"
        BYPRODUCTS "${JP_BUILD_ID_HEADER}"
        COMMENT "Updating Japanese native build fingerprint"
        VERBATIM)
    add_dependencies(Goemon64RecompiledJP goemon_japan_build_id)
    target_include_directories(Goemon64RecompiledJP PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
    get_target_property(JP_INCLUDES Goemon64Recompiled INCLUDE_DIRECTORIES)
    get_target_property(JP_COMPILE_OPTS Goemon64Recompiled COMPILE_OPTIONS)
    get_target_property(JP_LINK_OPTS Goemon64Recompiled LINK_OPTIONS)
    target_include_directories(Goemon64RecompiledJP PRIVATE
        ${JP_INCLUDES} "${GOEMON_JAPAN_GENERATED}")
    if(JP_COMPILE_OPTS)
        target_compile_options(Goemon64RecompiledJP PRIVATE ${JP_COMPILE_OPTS})
    endif()
    if(JP_LINK_OPTS)
        target_link_options(Goemon64RecompiledJP PRIVATE ${JP_LINK_OPTS})
    endif()
    target_link_libraries(Goemon64RecompiledJP PRIVATE
        "${GOEMON_JAPAN_STATIC_LIB}"
        librecomp ultramodern rt64
        RmlUi::Core RmlUi::Debugger nfd lunasvg)
    if(CMAKE_SYSTEM_NAME MATCHES "Linux")
        target_link_libraries(Goemon64RecompiledJP PRIVATE
            "-latomic -static-libstdc++" ${CMAKE_DL_LIBS} Threads::Threads
            ${FREETYPE_LIBRARIES} SDL2::SDL2)
    elseif(APPLE)
        target_link_libraries(Goemon64RecompiledJP PRIVATE
            ${CMAKE_DL_LIBS} Threads::Threads SDL2::SDL2)
    elseif(WIN32)
        target_link_libraries(Goemon64RecompiledJP PRIVATE SDL2 Winmm.lib)
    endif()
    add_dependencies(Goemon64RecompiledJP Goemon64Recompiled)
    set_property(TARGET Goemon64RecompiledJP PROPERTY
        VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
endif()
