#!/usr/bin/env python3
"""One-command strict-SHA1 launcher for the optional JP decompressed-ROM test.

Requires separately installed native v14 research mode. Does not modify the
ROM, binary or graphical resources; the application additionally checks exact
XXH3 and stores the ROM in an isolated game-id filename.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import os
import sys
from jp_decompressed_runtime_test_v14 import verify_rom, JP_DECOMP_SHA1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom", type=Path, required=True)
    p.add_argument("--binary", type=Path, default=Path("build-generated/japan-native-game/Goemon64RecompiledJP"))
    a = p.parse_args()
    try:
        verify_rom(a.rom)
    except (ValueError, OSError) as e:
        p.error(str(e))
    rom = a.rom.resolve()
    exe = a.binary.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        p.error(f"Native executable missing or not executable: {exe}")
    print(f"[JP-ROM-TEST] SHA-1 PASS: {JP_DECOMP_SHA1}", flush=True)
    print("[JP-ROM-TEST] Running isolated decompressed-ROM native mode", flush=True)
    os.execv(str(exe), [str(exe), "--test-decompressed-jp", str(rom)])
    return 0


if __name__ == "__main__":
    sys.exit(main())