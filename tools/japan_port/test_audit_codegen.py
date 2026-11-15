"""ROM-free, synthetic integrity checks for generated C-output auditing."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from .audit_codegen import verify
except ImportError:
    from audit_codegen import verify


class CodegenAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / 'out'
        self.out.mkdir()
        self.syms = self.root / 'symbols.toml'
        sections = [
            ('.entry', 0x1000, 0x80000400, 0x50),
            ('.main', 0x1050, 0x80000450, 0x100),
        ]
        sections.extend(
            (f'.file_{i}', 0x20000 + (i - 11) * 0x100,
             0x08000000 if i >= 24 else 0x801D0B90, 0x100)
            for i in range(11, 81)
        )
        symbol_lines, table_lines = [], []
        for index, (name, rom, ram, size) in enumerate(sections):
            symbol_lines.extend([
                '[[section]]', f'name = "{name}"',
                f'rom = 0x{rom:X}', f'vram = 0x{ram:X}',
                f'size = 0x{size:X}',
            ])
            if name == '.file_24':
                symbol_lines.extend([
                    'relocs = [',
                    ' { type = "R_MIPS_26", vram = 0x08000004, target_vram = 0x08000000 },',
                    ']',
                ])
            symbol_lines.extend(['functions = []', ''])
            table_lines.append(
                f'{{ .rom_addr = 0x{rom:08X}, .ram_addr = 0x{ram:08X}, '
                f'.size = 0x{size:08X}, .funcs = nullptr, .num_funcs = 0, '
                f'.relocs = nullptr, .num_relocs = 0, .index = {index} }},'
            )
        self.syms.write_text('\n'.join(symbol_lines))
        self.out.joinpath('funcs.h').write_text(
            'void recomp_entrypoint(uint8_t* rdram, recomp_context* ctx);\n'
        )
        self.out.joinpath('funcs_0.c').write_text(
            'RECOMP_FUNC void recomp_entrypoint(uint8_t* rdram, recomp_context* ctx) {\n'
            '}\n'
        )
        self.out.joinpath('lookup.cpp').write_text(
            'gpr get_entrypoint_address() { return (gpr)(int32_t)0x80000400u; }\n'
        )
        self.out.joinpath('recomp_overlays.inl').write_text(
            'static FuncEntry section_0_entry_funcs[] = {\n'
            ' { .func = recomp_entrypoint, .offset = 0x0, .rom_size = 0x38 },\n'
            '};\n'
            'static RelocEntry section_15_file_24_relocs[] = {\n'
            ' { .offset = 0x00000004, .target_section_offset = 0x00000000, '
            '.target_section = 15, .type = R_MIPS_26 },\n'
            '};\n'
            'static SectionTableEntry section_table[] = {\n' +
            '\n'.join(table_lines) + '\n};\n'
            'const size_t num_sections = 72;\n'
            'static int overlay_sections_by_index[] = {\n' +
            '\n'.join(f'{n},' for n in range(15,72)) + '\n};\n'
        )

    def tearDown(self):
        self.temp.cleanup()

    def replace(self, file, current, revised):
        path = self.out / file
        source = path.read_text()
        self.assertIn(current, source)
        path.write_text(source.replace(current, revised, 1))

    def test_valid_minimal_generated_output(self):
        report = verify(self.out, self.syms)
        self.assertEqual(report['sections'], 72)
        self.assertEqual(report['validated_relocation_records'], 1)
        self.assertEqual(report['relocatable_overlay_slots'], 57)
        self.assertEqual(report['emitted_c_function_definitions'], 1)

    def test_wrong_relocation_target_fails(self):
        self.replace('recomp_overlays.inl', '.target_section_offset = 0x00000000',
                     '.target_section_offset = 0x00000004')
        with self.assertRaisesRegex(ValueError, 'Relocation entry disagrees'):
            verify(self.out, self.syms)

    def test_missing_overlay_index_fails(self):
        self.replace('recomp_overlays.inl', '\n71,\n};', '\n70,\n};')
        with self.assertRaisesRegex(ValueError, 'overlay mappings'):
            verify(self.out, self.syms)

    def test_symbol_not_declared_fails(self):
        self.replace('funcs.h', 'recomp_entrypoint', 'wrong_function')
        with self.assertRaisesRegex(ValueError, 'different functions'):
            verify(self.out, self.syms)

    def test_unexpected_extern_fails(self):
        self.out.joinpath('funcs.h').write_text(
            self.out.joinpath('funcs.h').read_text() +
            'void phantom_native(uint8_t* rdram, recomp_context* ctx);\n'
        )
        self.out.joinpath('recomp_overlays.inl').write_text(
            self.out.joinpath('recomp_overlays.inl').read_text().replace(
                ' { .func = recomp_entrypoint,',
                ' { .func = phantom_native, .offset = 0, .rom_size = 0 },\n'
                ' { .func = recomp_entrypoint,',
                1
            )
        )
        with self.assertRaisesRegex(ValueError, 'Unexpected undefined'):
            verify(self.out, self.syms)

    def test_expected_runtime_extern_allowed(self):
        self.out.joinpath('funcs.h').write_text(
            self.out.joinpath('funcs.h').read_text() +
            'void osInitialize_recomp(uint8_t* rdram, recomp_context* ctx);\n'
        )
        self.out.joinpath('recomp_overlays.inl').write_text(
            self.out.joinpath('recomp_overlays.inl').read_text().replace(
                ' { .func = recomp_entrypoint,',
                ' { .func = osInitialize_recomp, .offset = 0, .rom_size = 0 },\n'
                ' { .func = recomp_entrypoint,',1
            )
        )
        report=verify(self.out,self.syms)
        self.assertEqual(report['externally_provided_runtime_functions'],1)

    def test_wrong_entrypoint_fails(self):
        self.replace('lookup.cpp', '0x80000400u', '0x80000404u')
        with self.assertRaisesRegex(ValueError, 'entrypoint lookup'):
            verify(self.out, self.syms)


if __name__ == '__main__':
    unittest.main()
