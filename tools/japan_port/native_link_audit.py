#!/usr/bin/env python3
"""Audit undefined symbols in the privately generated Japanese static library.

Requires nm, not ROM bytes. Optionally list native-provider archives to check
which ABI names they export. Symbol-name resolution is not a link or boot test.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

LIBC_OR_MATH = {
    "__assert_fail", "fegetround", "fesetround", "lrint", "lrintf", "sqrtf",
}
DISPATCH_OR_PLATFORM = {
    "do_break", "get_function", "pause_self", "section_addresses",
    "switch_error",
}
DEFINED_TYPES = {"A", "B", "C", "D", "G", "I", "R", "S", "T", "V", "W"}


def parse_nm(output: str) -> tuple[set[str], set[str]]:
    defined: set[str] = set()
    undefined: set[str] = set()
    for line in output.splitlines():
        fields = line.split()
        # GNU nm -P archive header ends with ":"; not a symbol row.
        if len(fields) < 2 or fields[0].endswith(":"):
            continue
        symbol, kind = fields[:2]
        if not re.fullmatch(r"[A-Za-z_.$?@][A-Za-z_0-9.$?@]*", symbol):
            continue
        if kind == "U":
            undefined.add(symbol)
        elif kind in DEFINED_TYPES:
            defined.add(symbol)
    return defined, undefined


def classify(symbol: str) -> str:
    if symbol.endswith("_recomp"):
        return "n64_host_runtime"
    if symbol in LIBC_OR_MATH:
        return "libc_or_math"
    if symbol in DISPATCH_OR_PLATFORM:
        return "recomp_dispatch_or_platform"
    return "unclassified"


def nm_symbols(paths: list[Path]) -> tuple[set[str], set[str]]:
    if not paths:
        return set(), set()
    command = ["nm", "-g", "-P", *(str(p.resolve(strict=True)) for p in paths)]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("nm failed: " + result.stderr[:2000])
    return parse_nm(result.stdout)


def audit(archive: Path, providers: list[Path]) -> dict:
    local_defs, local_refs = nm_symbols([archive])
    provider_defs, _ = nm_symbols(providers)
    unresolved = local_refs - local_defs
    matched = unresolved & provider_defs
    remaining = sorted(unresolved - matched)
    categories: dict[str, list[str]] = {}
    for name in remaining:
        categories.setdefault(classify(name), []).append(name)
    return {
        "archive": str(archive),
        "local_defined_symbols": len(local_defs),
        "raw_undefined_references": len(local_refs),
        "unique_external_imports": len(unresolved),
        "provider_archive_count": len(providers),
        "imports_satisfied_by_provider_names": sorted(matched),
        "remaining_import_count": len(remaining),
        "remaining_by_category": categories,
        "caveat": "Symbol-name audit only, not a successful final PC runtime link",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--provider", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.archive, args.provider)
    serialized = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    print(serialized, end="")


if __name__ == "__main__":
    main()
