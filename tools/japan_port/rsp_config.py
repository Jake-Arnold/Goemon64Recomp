#!/usr/bin/env python3
"""Generate a Japan-specific RSPRecomp config from the original USA audio task.

Both ROMs contain identical 0xE20 bytes of aspMain audio RSP microcode,
but at different ROM offsets. Verify exact source hashes before reuse.
The recompiled C++ output is local only and must not be committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

USA_SHA1 = "6ea0ed71032ce08fc2745f412d84936382197494"
JAPAN_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
AUDIO_MICROCODE_SHA1 = "21e05bb9b4b3611e0cc2374c3ad6cc26adf2b385"
USA_OFFSET = 0x546B0
JP_OFFSET = 0x54930
TEXT_SIZE = 0xE20
TEXT_ADDRESS = 0x04001080


def verify_roms(usa: bytes, japan: bytes) -> dict:
    if len(usa) != 0x2000000 or hashlib.sha1(usa).hexdigest() != USA_SHA1:
        raise ValueError("Expected exact 32 MiB USA decompressed source image")
    if len(japan) != 0x2000000 or hashlib.sha1(japan).hexdigest() != JAPAN_SHA1:
        raise ValueError("Expected exact 32 MiB Japanese decompressed source image")
    us_text = usa[USA_OFFSET:USA_OFFSET + TEXT_SIZE]
    jp_text = japan[JP_OFFSET:JP_OFFSET + TEXT_SIZE]
    if (us_text != jp_text
            or hashlib.sha1(us_text).hexdigest() != AUDIO_MICROCODE_SHA1):
        raise ValueError("Audio microcode differs across regions")
    return {"usa_offset": f"0x{USA_OFFSET:X}", "japan_offset": f"0x{JP_OFFSET:X}",
            "text_size": f"0x{TEXT_SIZE:X}", "rsp_sha1": AUDIO_MICROCODE_SHA1,
            "byte_identical": True}


def render_config(usa_config: dict, rom: Path, output_cpp: Path) -> str:
    expected = {
        "text_offset": USA_OFFSET, "text_size": TEXT_SIZE,
        "text_address": TEXT_ADDRESS, "output_function_name": "aspMain",
    }
    for key, value in expected.items():
        if usa_config.get(key) != value:
            raise ValueError(f"Unexpected upstream aspMain configuration: {key}")
    targets = usa_config.get("extra_indirect_branch_targets")
    if (not isinstance(targets, list) or len(targets) != 16
            or any(not isinstance(v, int) or v < 0 for v in targets)):
        raise ValueError("Unexpected aspMain indirect branch targets")
    def quoted(value: Path | str) -> str:
        return json.dumps(str(value))
    return (
        "# Japan only; byte-identical RSP task at its JP ROM offset.\n"
        f"text_offset = 0x{JP_OFFSET:X}\n"
        f"text_size = 0x{TEXT_SIZE:X}\n"
        f"text_address = 0x{TEXT_ADDRESS:X}\n"
        f"rom_file_path = {quoted(rom)}\n"
        f"output_file_path = {quoted(output_cpp)}\n"
        f"output_function_name = {quoted('aspMain')}\n"
        "extra_indirect_branch_targets = [\n"
        + "".join(f"    0x{target:X},\n" for target in targets)
        + "]\n"
    )


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--usa-rom", type=Path, required=True)
    cli.add_argument("--japan-rom", type=Path, required=True)
    cli.add_argument("--usa-config", type=Path, required=True)
    cli.add_argument("--output-config", type=Path, required=True)
    cli.add_argument("--output-cpp", type=Path, required=True)
    args = cli.parse_args()
    inputs = {p.resolve(strict=True) for p in (args.usa_rom, args.japan_rom, args.usa_config)}
    config_path = args.output_config.resolve()
    output_cpp = args.output_cpp.resolve()
    if (config_path in inputs or output_cpp in inputs
            or config_path == output_cpp or config_path.exists() or output_cpp.exists()):
        cli.error("Output must be a new file outside all input paths")
    try:
        result = verify_roms(args.usa_rom.read_bytes(), args.japan_rom.read_bytes())
        source_config = tomllib.loads(args.usa_config.read_text())
        rendered = render_config(source_config, args.japan_rom.resolve(), output_cpp)
        tomllib.loads(rendered)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        cli.error(str(error))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(rendered)
    print(json.dumps({**result, "config": str(config_path),
                      "output_cpp": str(output_cpp)}, indent=2))


if __name__ == "__main__":
    main()
