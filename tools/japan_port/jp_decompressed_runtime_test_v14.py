#!/usr/bin/env python3
"""Fail-closed, research-only opt-in native JP decompressed ROM A/B input selector.

Only patches the user's private src/main/main.cpp when it matches one of two
audited exact Git blobs (original research baseline or JP stage18 runtime). No game assets/ROM, renderer, generated MIPS code or runtime library
are modified. Default JP ROM loading remains unchanged; the alternate
--test-decompressed-jp mode requires the known 32 MiB image and never uses the
normal game's stored ROM filename.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

JP_DECOMP_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
JP_DECOMP_XXH3 = 0xC519E0E26FA0D20E
JP_DECOMP_BYTES = 0x02000000
ORIGINAL_MAIN_BLOB = "6e6d2c5afae012b91507b85f114f3e31ebef7165"
STAGE18_MAIN_BLOB = "e8d467df4637bd20592547140a533fca404379d5"
SUPPORTED_MAIN_BLOBS = (ORIGINAL_MAIN_BLOB, STAGE18_MAIN_BLOB)

MARKER = "GOEMON_JP_DECOMP_ROM_AB_V14"
BACKUP_SUFFIX = ".pre-jp-decompressed-rom-ab-v14"

VERSION_ANCHOR = """    recomp::Version project_version{};
"""
VERSION_PATCH = """#ifdef GOEMON_JAPAN_NATIVE
    // GOEMON_JP_DECOMP_ROM_AB_V14: explicitly selected ROM-only comparison.
    // The normal compressed Japanese ROM entry is unchanged unless this
    // command-line mode is requested. The test has its own stored filename.
    const char *jpDecompressedTestInput = nullptr;
    if (argc > 1 && std::strcmp(argv[1], "--test-decompressed-jp") == 0) {
        if (argc != 3 || argv[2][0] == '\\0') {
            std::fprintf(stderr, "Usage: Goemon64RecompiledJP --test-decompressed-jp <verified-32MiB-ROM>\\n");
            return EXIT_FAILURE;
        }
        jpDecompressedTestInput = argv[2];
        auto &testGame = supported_games.at(0);
        testGame.rom_hash = 0xC519E0E26FA0D20EULL;
        testGame.game_id = u8"mnsg.jp.decomp-test";
        // Keep the same game/mod implementation, but isolate ROM storage/saves.
        testGame.mod_game_id = "mnsg.jp";
        testGame.decompression_routine = nullptr;
        testGame.has_compressed_code = false;
        std::fprintf(stderr, "[JP-ROM-TEST] input=decompressed; expected_size=33554432; expected_xxh3=0xC519E0E26FA0D20E; no decompression\\n");
    }
#endif
    recomp::Version project_version{};
"""

REGISTER_ANCHOR = """    // Register supported games and patches
    for (const auto& game : supported_games) {
        recomp::register_game(game);
    }
"""
REGISTER_PATCH = """    // Register supported games and patches
    for (const auto& game : supported_games) {
        recomp::register_game(game);
    }
#ifdef GOEMON_JAPAN_NATIVE
    if (jpDecompressedTestInput != nullptr) {
        // This test entry uses mnsg.jp.decomp-test.z64, never mnsg.jp.z64.
        // Native runtime select_rom checks exact XXH3 before storing it.
        std::error_code jpRomPathError;
        const std::filesystem::path jpAppPath = goemon64::get_app_folder_path();
        std::filesystem::create_directories(jpAppPath, jpRomPathError);
        if (jpRomPathError) {
            std::fprintf(stderr, "[JP-ROM-TEST] Could not create isolated ROM storage: %s\\n", jpRomPathError.message().c_str());
            return EXIT_FAILURE;
        }
        const auto jpResult = recomp::select_rom(
            std::filesystem::path(jpDecompressedTestInput), supported_games[0].game_id);
        if (jpResult != recomp::RomValidationError::Good) {
            std::fprintf(stderr, "[JP-ROM-TEST] Rejected ROM: validation error=%u; expected verified 32 MiB Japan decompressed image\\n",
                static_cast<unsigned>(jpResult));
            return EXIT_FAILURE;
        }
        const auto jpStoredRom = jpAppPath / "mnsg.jp.decomp-test.z64";
        jpRomPathError.clear();
        const auto jpStoredSize = std::filesystem::file_size(jpStoredRom, jpRomPathError);
        if (jpRomPathError || jpStoredSize != 33554432ull) {
            std::fprintf(stderr, "[JP-ROM-TEST] Refusing to launch: isolated stored ROM missing/incorrect size\\n");
            return EXIT_FAILURE;
        }
        std::fprintf(stderr, "[JP-ROM-TEST] Accepted exact expected XXH3 input; isolated stored ROM ready; launcher will use 32 MiB without decompression\\n");
    }
#endif
"""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def digest(path: Path) -> tuple[int, str, bytes]:
    h = hashlib.sha1()
    size = 0
    with path.open("rb") as f:
        magic = f.read(4)
        h.update(magic)
        size += len(magic)
        while block := f.read(1024 * 1024):
            size += len(block)
            h.update(block)
    return size, h.hexdigest(), magic


def verify_rom(path: Path) -> None:
    size, sha1, magic = digest(path)
    if size != JP_DECOMP_BYTES or sha1 != JP_DECOMP_SHA1 or magic != bytes.fromhex("80371240"):
        raise ValueError("ROM rejected: expected exact Japanese decompressed 32 MiB SHA-1 "
                         f"{JP_DECOMP_SHA1}; got size={size}, SHA-1={sha1}, magic={magic.hex()}")


def one(source: str, old: str, new: str, label: str) -> str:
    hits = source.count(old)
    if hits != 1:
        raise ValueError(f"{label}: expected one exact source anchor, found {hits}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    if MARKER in source:
        raise ValueError("v14 already installed")
    source = one(source, VERSION_ANCHOR, VERSION_PATCH, "JP v14 command selector")
    source = one(source, REGISTER_ANCHOR, REGISTER_PATCH, "JP v14 verified ROM import")
    return source


def plan(main: Path, rom: Path) -> tuple[bytes, bytes]:
    verify_rom(rom)
    original = main.read_bytes()
    observed = git_blob(original)
    if observed not in SUPPORTED_MAIN_BLOBS:
        allowed = ", ".join(SUPPORTED_MAIN_BLOBS)
        raise ValueError(f"main.cpp source drift; expected one of pinned blobs [{allowed}]; got {observed}")
    if main.with_name(main.name + BACKUP_SUFFIX).exists():
        raise ValueError("v14 backup already exists; refuse reapply")
    output = transform(original.decode("utf-8")).encode("utf-8")
    return original, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--main", type=Path, default=Path("src/main/main.cpp"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--confirm-modify-private-main", action="store_true")
    a = parser.parse_args()
    try:
        original, updated = plan(a.main, a.rom)
        if a.confirm_modify_private_main:
            backup = a.main.with_name(a.main.name + BACKUP_SUFFIX)
            backup.write_bytes(original)
            try:
                a.main.write_bytes(updated)
            except BaseException:
                a.main.write_bytes(original)
                raise
        print("Japanese decompressed ROM: 32 MiB, exact SHA-1 verified; pinned main.cpp: PASS")
        print("v14: " + ("installed; rebuild needed" if a.confirm_modify_private_main else "validated only"))
    except (OSError, UnicodeError, ValueError) as e:
        parser.error(str(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())