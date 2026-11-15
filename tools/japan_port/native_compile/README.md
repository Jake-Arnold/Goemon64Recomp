# Isolated native compilation of Japanese generated functions

This is an **object-library compile gate**, not a runnable Goemon PC port.
It does not modify the USA game, launcher, graphics runtime or patch build.

## Prerequisites

- Locally generated, verified Japanese `RecompiledFuncsJP/` output from pinned `N64Recomp`
- Pinned `N64Recomp/include/recomp.h` matching the host compiler revision
- The fork's `include/trace.h`
- Linux GCC or Clang, CMake 3.20+, Ninja or Make

The host compiler workflow `japan-port-recompilers.yml` now provides the pinned API header with the matching Linux compiler binary. It never includes ROMs or generated game C.

## Compile the private code to a static library

From the repository root:

```bash
cmake -S tools/japan_port/native_compile -B build-generated/japan-native-lib \
  -G Ninja \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_BUILD_TYPE=Debug \
  -DGOEMON_JAPAN_GENERATED=/absolute/private/path/RecompiledFuncsJP \
  -DGOEMON_N64RECOMP_INCLUDE=/absolute/path/pinned/N64Recomp/include \
  -DGOEMON_PORT_INCLUDE="$PWD/include"

cmake --build build-generated/japan-native-lib \
  --target GoemonRecompiledJapan -j4
```

This compiles the local `funcs_*.c` and `lookup.cpp` into `libGoemonRecompiledJapan.a`. It does **not** compile or link `recomp_overlays.inl` into a PC runtime yet.

## Verified local build, 15 November 2026

With the Japanese ROM SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`, the pinned x86-64 `N64Recomp` emitted 145 C source units. The isolated build passed CMake configuration, Clang 17 compilation and static archiving with **exit code 0** (33 MiB library, debug/unoptimised build).

The generated C referenced **15 host-runtime functions** not declared by `funcs.h`; they are listed in `runtime_externs.h` and are provided as compile-time **prototypes only**. The original PC port defines some, including `osPiWriteIo_recomp`, in `src/game/unknown_symbols.cpp`. Missing implementations are **not** fabricated or stubbed out by this target.

An archive-wide `nm -g` audit found **82 unique unresolved external symbols** after removing functions resolved inside the archive: 71 `*_recomp` host-runtime functions and 11 dispatch/math/compiler/runtime symbols. The majority are expected native runtime imports, but all must be resolved or deliberately implemented before **linking an executable**. The Japanese ROM handling, graphics, input, sound, overlays, UI, saves, native patches and boot/gameplay remain to be integrated and tested.

Do not commit the compiled archive, `funcs_*.c`, generated headers or any ROM/asset bytes.
