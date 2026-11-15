#!/usr/bin/env python3
"""Verify and prepare privately supplied Goemon ROMs for Japanese recompilation.

Never distribute ROMs, extracted assets, generated MIPS source or object files.
The Japanese file on disk may be byte-swapped despite its .n64 suffix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

JP_SOURCE = "b6386455c0b8f573e315976bbb47548cbafcedb3"
JP_NORMAL = "9843ee979b5f6c80f5eda85df0baed9ae7c4e73b"
JP_DECOMP = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
USA_SOURCE = "df8083a54296b8c151917c5333e1c85f014a2a66"
USA_DECOMP = "6ea0ed71032ce08fc2745f412d84936382197494"
NORMAL_MAGIC = bytes.fromhex("80371240")
V64_MAGIC = bytes.fromhex("37804012")
N64_MAGIC = bytes.fromhex("40123780")
COMPRESSED_SIZE = 0x1000000
DECOMPRESSED_SIZE = 0x2000000
JP_FILE_TABLE_OFFSET = 0x58258


class RomError(ValueError):
    """A supplied ROM or output fails a region/format validation gate."""


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def normalize(data: bytes) -> tuple[bytes, str]:
    """Convert arbitrary N64 ROM byte order to canonical big-endian .z64."""
    if len(data) < 4 or len(data) % 4:
        raise RomError("ROM size must be a nonzero multiple of four")
    if data[:4] == NORMAL_MAGIC:
        return data, "z64"
    if data[:4] == V64_MAGIC:
        target = bytearray(len(data))
        target[::2], target[1::2] = data[1::2], data[::2]
        return bytes(target), "v64"
    if data[:4] == N64_MAGIC:
        target = bytearray(len(data))
        target[::4], target[1::4] = data[3::4], data[2::4]
        target[2::4], target[3::4] = data[1::4], data[::4]
        return bytes(target), "n64"
    raise RomError("Unrecognised N64 ROM magic: " + data[:4].hex())


def checked(path: Path, expected: str, size: int) -> bytes:
    data = path.read_bytes()
    if len(data) != size or sha1(data) != expected:
        raise RomError(f"{path}: expected {size} bytes, SHA-1 {expected}; "
                       f"got {len(data)} bytes, SHA-1 {sha1(data)}")
    return data


def prepare(japan: Path, destination: Path) -> dict:
    data = japan.read_bytes()
    if len(data) != COMPRESSED_SIZE:
        raise RomError("Expected a 16 MiB Japanese ROM")
    normalized, original_format = normalize(data)
    if sha1(data) not in (JP_SOURCE, JP_NORMAL) or sha1(normalized) != JP_NORMAL:
        raise RomError("Unsupported Japanese ROM revision or damaged input")
    if normalized[0x3B:0x3F] != b"NG5J":
        raise RomError("The Japanese internal game code NG5J was not found")
    if normalized.find(b"Nisitenma-Ichigo") + 16 != JP_FILE_TABLE_OFFSET:
        raise RomError("Japanese compressed file-table offset does not match")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != normalized:
        raise RomError("Refusing to overwrite an existing different ROM")
    destination.write_bytes(normalized)
    return {"region": "japan_0", "original_format": original_format,
            "source_sha1": sha1(data), "normalized_sha1": JP_NORMAL,
            "path": str(destination)}


def verify_decompressed(path: Path) -> dict:
    checked(path, JP_DECOMP, DECOMPRESSED_SIZE)
    return {"region": "japan_0", "verified": True, "sha1": JP_DECOMP}


def decompress(rom: Path, rommy: Path, manifest: Path, destination: Path,
               python_executable: str) -> dict:
    checked(rom, JP_NORMAL, COMPRESSED_SIZE)
    if not rommy.is_file() or not manifest.is_file():
        raise RomError("ROMMY script or region-specific rommy.yaml manifest missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [python_executable, str(rommy), "decompress", "--input",
               str(rom), "--output", str(destination), "--manifest",
               str(manifest), "--pad"]
    subprocess.run(command, check=True)
    return verify_decompressed(destination)


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--japan", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify-decompressed")
    check.add_argument("--rom", type=Path, required=True)
    decomp = sub.add_parser("decompress")
    decomp.add_argument("--rom", type=Path, required=True)
    decomp.add_argument("--rommy", type=Path, required=True)
    decomp.add_argument("--manifest", type=Path, required=True)
    decomp.add_argument("--output", type=Path, required=True)
    decomp.add_argument("--python", default="python3")
    args = cli.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.japan, args.output)
        elif args.command == "verify-decompressed":
            result = verify_decompressed(args.rom)
        else:
            result = decompress(args.rom, args.rommy, args.manifest,
                                args.output, args.python)
    except (OSError, RomError, subprocess.CalledProcessError) as error:
        cli.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
