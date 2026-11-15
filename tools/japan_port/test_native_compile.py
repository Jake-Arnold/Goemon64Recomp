"""ROM-free CMake smoke tests for isolated Japanese static-library build."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent / 'native_compile'


@unittest.skipUnless(shutil.which('cmake') and shutil.which('cc') and shutil.which('c++'),
                     'Native CMake and C/C++ compilers are required')
class NativeCompileSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.generated = self.base / 'japan-generated'
        self.headers = self.base / 'sdk'
        self.trace = self.base / 'port'
        self.build = self.base / 'build'
        for path in (self.generated, self.headers, self.trace):
            path.mkdir()
        (self.headers / 'recomp.h').write_text(
            '#pragma once\n#include <stdint.h>\n'
            'typedef struct recomp_context { int value; } recomp_context;\n'
        )
        (self.trace / 'trace.h').write_text('#pragma once\n')
        (self.generated / 'funcs.h').write_text('#pragma once\n')
        (self.generated / 'lookup.cpp').write_text('int japan_lookup_smoke_test() { return 42; }\n')
        (self.generated / 'recomp_overlays.inl').write_text('// Synthetic only\n')
        for index in range(140):
            (self.generated / f'funcs_{index}.c').write_text(
                f'#include "recomp.h"\n'
                f'void jp_synthetic_{index}(uint8_t* ptr, recomp_context* ctx)'
                f' {{ (void)ptr; (void)ctx; }}\n'
            )

    def tearDown(self):
        self.temp.cleanup()

    def configure(self):
        return subprocess.run(
            ['cmake', '-S', str(HERE), '-B', str(self.build),
             '-DGOEMON_JAPAN_GENERATED=' + str(self.generated),
             '-DGOEMON_N64RECOMP_INCLUDE=' + str(self.headers),
             '-DGOEMON_PORT_INCLUDE=' + str(self.trace)],
            capture_output=True, text=True, timeout=30
        )

    def test_synthetic_archive_compiles_without_rom(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(
            ['cmake', '--build', str(self.build), '--target', 'GoemonRecompiledJapan',
             '--parallel', '4'],
            capture_output=True, text=True, timeout=90
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(list(self.build.glob('*GoemonRecompiledJapan.a')))

    def test_missing_generated_header_rejected(self):
        (self.generated / 'funcs.h').unlink()
        result = self.configure()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Required native recompilation header', result.stdout + result.stderr)

    def test_incomplete_function_batch_rejected(self):
        for index in range(10):
            (self.generated / f'funcs_{index}.c').unlink()
        result = self.configure()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Incomplete Japanese N64Recomp C output', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
