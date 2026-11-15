#!/usr/bin/env python3
"""Prepare and optionally trial an isolated Japanese N64Recomp invocation.

Requires user-owned Japanese 32 MiB ROM + freshly extracted Splat assembly.
All derived code, ROMs and symbol files go under ignored build-generated/.
The trial is intentionally opt-in, and a successful C-generation run does
not mean the Japanese game is playable.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

try:
    from .candidate_symbols import sections, parse_functions, render
    from .reloc_candidates import parse as scan_relocations
    from .merge_candidate_symbols import merge, JP_DECOMP
    from .complete_symbols import complete
    from .rom import verify_decompressed
except ImportError:
    from candidate_symbols import sections, parse_functions, render
    from reloc_candidates import parse as scan_relocations
    from merge_candidate_symbols import merge, JP_DECOMP
    from complete_symbols import complete
    from rom import verify_decompressed

EXPECTED_SECTIONS = 72
EXPECTED_FUNCTIONS = 7351
EXPECTED_RELOCATIONS = 6434
EXPECTED_TLB = [f'.file_{number}' for number in range(24, 81)]


def validate_config(repo_root: Path, sections_found: list[dict]) -> None:
    config = tomllib.loads((repo_root / 'mnsg.japan.toml').read_text())['input']
    expected = {
        'entrypoint': 0x80000400,
        'output_func_path': 'build-generated/japan/RecompiledFuncs',
        'symbols_file_path': 'build-generated/japan/japan-PROVISIONAL.syms.toml',
        'rom_file_path': 'build-generated/japan/baserom.decompressed.z64',
        'relocatable_sections_path': 'mnsg.overlays.txt',
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(f'Japanese N64Recomp config mismatch: {key}')
    overlay_file = repo_root / config['relocatable_sections_path']
    configured = [name.strip() for name in overlay_file.read_text().splitlines()
                  if name.strip() and not name.strip().startswith('#')]
    if configured != EXPECTED_TLB:
        raise ValueError('TLB overlay identifiers changed; inspect region mapping')
    observed = {'.'+section['name'] for section in sections_found}
    if not set(configured) <= observed:
        raise ValueError('Japan Splat does not define all N64Recomp overlay names')


def generate(repo_root: Path, splat: Path, asm_root: Path, rom: Path) -> dict:
    repo_root = repo_root.resolve()
    splat, asm_root, rom = splat.resolve(), asm_root.resolve(), rom.resolve()
    verify_decompressed(rom)
    sec = sections(splat)
    functions = parse_functions(asm_root, sec)
    relocations = scan_relocations(asm_root, splat, rom)
    if relocations['source_sha1'] != JP_DECOMP:
        raise ValueError('Incorrect Japanese decompressed ROM revision')
    if (len(sec),len(functions),relocations['candidate_relocations']) != (
        EXPECTED_SECTIONS,EXPECTED_FUNCTIONS,EXPECTED_RELOCATIONS
    ):
        raise ValueError('Unexpected symbol/relocation counts: investigate before writing')
    validate_config(repo_root, sec)
    bss = {'.'+part['name']:part.get('bss_size',0) for part in sec}
    combined, candidate_report = merge(render(sec, functions), relocations, bss)
    combined, completion_report = complete(combined, rom.read_bytes())
    report = {**candidate_report, **completion_report}
    output = repo_root / 'build-generated' / 'japan'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'japan-PROVISIONAL.syms.toml').write_text(combined)
    (output / 'reloc-candidates.json').write_text(json.dumps(relocations,indent=2)+'\n')
    dest = output / 'baserom.decompressed.z64'
    if dest.resolve() != rom:
        shutil.copyfile(rom,dest)
    return {
        **report,
        'rom_sha1': JP_DECOMP,
        'generated_directory': str(output),
        'n64recomp_trial_executed': False,
        'warning': 'Candidate map only; no native PC build or gameplay proof',
    }


def main() -> int:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--japan-splat',type=Path,required=True)
    cli.add_argument('--japan-asm',type=Path,required=True)
    cli.add_argument('--japan-decompressed-rom',type=Path,required=True)
    cli.add_argument('--repo-root',type=Path,
                     default=Path(__file__).resolve().parents[2])
    cli.add_argument('--run-recompiler',action='store_true',
                     help='Explicitly run installed N64Recomp (may fail on incomplete symbols)')
    cli.add_argument('--recompiler',type=Path,
                     help='Existing executable path; only used with --run-recompiler')
    args=cli.parse_args()
    if args.run_recompiler and args.recompiler is None:
        cli.error('--recompiler is required with --run-recompiler')
    report=generate(args.repo_root,args.japan_splat,args.japan_asm,
                    args.japan_decompressed_rom)
    if args.run_recompiler:
        binary=args.recompiler.resolve()
        if not binary.is_file() or not os.access(binary,os.X_OK):
            cli.error(f'N64Recomp binary missing or not executable: {binary}')
        subprocess.run([str(binary),'mnsg.japan.toml'],
                       cwd=args.repo_root.resolve(),check=True)
        report['n64recomp_trial_executed']=True
        report['warning']='Trial code generation returned zero; gameplay not tested'
    print(json.dumps(report,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
