"""Synthetic source / opt-in safety checks for the v16 RSP read-only trace."""
import tempfile
import subprocess
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import jp_rt64_texture_segment_v16 as v16


FIXTURE = '''#include <cassert>
namespace RT64 {
''' + v16.FUNCTION_ANCHOR + '\n}\n'


class SegmentV16(unittest.TestCase):
    def test_source_transformation(self):
        s = v16.transform(FIXTURE)
        self.assertEqual(s.count(v16.MARKER), 1)
        self.assertEqual(s.count('state->rdp->setTextureImage(fmt, siz, width, resolved);'), 1)
        self.assertIn('segmentBase + segmentOffset', s)
        self.assertIn('physical != 0x0078B6E0u', s)
        self.assertIn('physical != 0x007953D0u', s)
        self.assertIn('seenCount >= 32u', s)

    def test_reject_duplicate_install(self):
        with self.assertRaisesRegex(ValueError, 'already installed'):
            v16.transform(v16.transform(FIXTURE))

    def test_reject_anchor_drift(self):
        with self.assertRaisesRegex(ValueError, 'source anchor'):
            v16.transform(FIXTURE.replace('state->rdp->setTextureImage', 'missing->setTextureImage'))

    def test_reject_duplicate_anchor(self):
        with self.assertRaisesRegex(ValueError, 'source anchor'):
            v16.transform(FIXTURE + v16.FUNCTION_ANCHOR)

    def test_wrong_rom_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'bad.z64'
            f.write_bytes(bytes.fromhex('80371240') + b'bad')
            with self.assertRaisesRegex(ValueError, 'Wrong ROM'):
                v16.verify_rom(f)

    def test_source_hash_safety(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rsp = root / v16.RSP
            rsp.parent.mkdir(parents=True)
            rsp.write_text(FIXTURE)
            with patch.object(v16, 'verify_rom'):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    v16.plan(root, root / 'rom')
            self.assertEqual(rsp.read_text(), FIXTURE)

    def test_exact_fixture_success_and_backup_reject(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rsp = root / v16.RSP
            rsp.parent.mkdir(parents=True)
            rsp.write_text(FIXTURE)
            with patch.object(v16, 'verify_rom'), patch.object(v16, 'RSP_GIT_BLOB', v16.git_blob(FIXTURE.encode())):
                path, original, new = v16.plan(root, root / 'rom')
                self.assertEqual(path, rsp)
                self.assertEqual(original, FIXTURE.encode())
                self.assertIn(v16.MARKER.encode(), new)
                backup = rsp.with_name(rsp.name + v16.BACKUP)
                backup.write_bytes(original)
                with self.assertRaisesRegex(ValueError, 'backup already exists'):
                    v16.plan(root, root / 'rom')
                self.assertEqual(rsp.read_bytes(), original)

    def test_compiled_cpp_normal_and_target_modes(self):
        header = r'''#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <array>
namespace RT64 {
struct RDP {
    struct { uint32_t address = 0; } texture;
    void setTextureImage(uint8_t, uint8_t, uint16_t, uint32_t address) {
        texture.address = address & 0x00FFFFFFu;
    }
};
struct State {
    RDP* rdp;
    struct { bool extendRDRAM = false; } extended;
};
struct RSP {
    State* state;
    std::array<uint32_t,16> segments{};
    uint32_t fromSegmented(uint32_t raw) {
        return segments[(raw >> 24u) & 15u] + (raw & 0x00FFFFFFu);
    }
    void setTextureImage(uint8_t, uint8_t, uint16_t, uint32_t);
};
'''
        footer = r'''
}
int main() {
    RT64::RDP rdp;
    RT64::State state{&rdp, {false}};
    RT64::RSP rsp{&state};
    rsp.segments[11] = 0x0078B6E0u;
    rsp.setTextureImage(0, 2, 1, 0x0B000000u);
    assert(rdp.texture.address == 0x0078B6E0u);
    rsp.setTextureImage(0, 2, 1, 0x0B000000u);
    rsp.segments[12] = 0x007953D0u;
    rsp.setTextureImage(0, 2, 1, 0x0C000000u);
    assert(rdp.texture.address == 0x007953D0u);
}
'''
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'test.cpp'
            binary = Path(d) / 'test'
            source.write_text(header + v16.FUNCTION_PATCH + footer)
            cmd = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
                                 capture_output=True, text=True)
            self.assertEqual(cmd.returncode, 0, cmd.stderr)
            base = {**os.environ, 'GOEMON_JP_RT64_TEX_TRACE': '0'}
            default = subprocess.run([str(binary)], capture_output=True, text=True, env=base)
            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertNotIn('TEX_SEG_V16', default.stderr)
            base['GOEMON_JP_RT64_TEX_TRACE'] = '1'
            traced = subprocess.run([str(binary)], capture_output=True, text=True, env=base)
            self.assertEqual(traced.returncode, 0, traced.stderr)
            self.assertEqual(traced.stderr.count('TEX_SEG_V16'), 2, traced.stderr)
            self.assertIn('raw=0x0B000000 seg=11 base=0x0078B6E0', traced.stderr)
            self.assertIn('raw=0x0C000000 seg=12 base=0x007953D0', traced.stderr)

    def test_pins(self):
        self.assertEqual(v16.ROM_SIZE, 33554432)
        self.assertEqual(v16.ROM_SHA1, '6f8745fecc3a5e7d4918c7a73353eb0726116ded')
        self.assertEqual(v16.RSP_GIT_BLOB, 'd4d9883e9bab98e0e44988a58ca5f6a06906890e')


if __name__ == '__main__':
    unittest.main()
