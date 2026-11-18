"""Host-C runtime tests for JP actor instance generation and bounded Gfx windows."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from jp_actor_model_trace import ACTOR_SIG, DRAW_SIG, transform as make_v1
from jp_actor_model_trace_v2 import (
    V1_HELPER_SHA256, ROM_ANCHORS, GFX_TAIL_VMA, find_targets,
    upgrade_sources, validate_rom,
)
from jp_actor_model_trace import HELPER as OLD_HELPER

ORIGINAL_ACTOR = '#include "recomp.h"\n'+ACTOR_SIG+'    (void)rdram; (void)ctx;\n}\n'
ORIGINAL_DRAW = '''#include "recomp.h"
''' + DRAW_SIG + '''    // Two guest commands emitted into the main game display-list buffer.
    uint32_t cursor = MEM_W(0, (gpr)(int32_t)0x80161DBCu);
    MEM_W(0, (gpr)(int32_t)cursor) = 0x06000000u;
    MEM_W(4, (gpr)(int32_t)cursor) = 0x80301020u;
    MEM_W(8, (gpr)(int32_t)cursor) = 0xDA000000u;
    MEM_W(12, (gpr)(int32_t)cursor) = 0x80211000u;
    MEM_W(0, (gpr)(int32_t)0x80161DBCu) = cursor + 16u;
    (void)ctx;
}
'''
HEADER = r'''#ifndef RECOMP_H
#define RECOMP_H
#include <stdint.h>
typedef int64_t gpr;
typedef struct { uint64_t r4; } recomp_context;
#define RECOMP_FUNC
#define MEM_W(off,base) (*(uint32_t*)(rdram + ((((uint32_t)(base))+(off)) & 0x7fffffu)))
#define MEM_H(off,base) (*(uint16_t*)(rdram + (((((uint32_t)(base))+(off)) & 0x7fffffu) ^ 2u)))
#endif
'''
HARNESS = r'''#include "recomp.h"
#include <stdlib.h>
void func_8021D7C4_5D8D54(uint8_t*, recomp_context*);
void func_800167D4_173D4(uint8_t*, recomp_context*);
int main(void) {
    uint8_t* rdram = calloc(0x800000, 1);
    if (!rdram) return 7;
    recomp_context ctx = {0};
    gpr a = (gpr)(int32_t)0x80150000u;
    gpr obj = (gpr)(int32_t)0x80160000u;
    // Reconstructed case #1: mode 1, segment 8, overlay base 0x803EAE40.
    MEM_W(0, (gpr)(int32_t)0x80161DBCu) = 0x80210000u;
    MEM_W(0x18, a) = 0x80160000u;
    MEM_W(0x2C, obj) = 0x18000420u;
    MEM_W(0x30, obj) = 0xC0073400u;
    MEM_W(0x38, obj) = 0x803EAE40u;
    MEM_W(0, (gpr)(int32_t)0x803EB260u) = 0x12131415u;
    MEM_W(4, (gpr)(int32_t)0x803EB260u) = 0x16171819u;
    ctx.r4 = 0xffffffff80150000ULL;
    func_8021D7C4_5D8D54(rdram, &ctx);
    MEM_H(0x5C, a) = 0xFB;
    MEM_H(0x5E, a) = 0xFB;
    ctx.r4 = 0xffffffff80160000ULL;
    func_800167D4_173D4(rdram, &ctx);
    // A real change without a loader re-entry: same generation.
    MEM_H(0x5E, a) = 1u;
    // Reconstructed case #2: mode 4, segment A, slot 2 base.
    MEM_W(0x2C, obj) = 0x4A000640u;
    MEM_W(0x30, obj) = 0xA0160080u;
    MEM_W(0x48, obj) = 0x803A5040u;
    MEM_W(0, (gpr)(int32_t)0x803A5680u) = 0xABCDEF01u;
    MEM_W(4, (gpr)(int32_t)0x803A5680u) = 0x22334455u;
    func_800167D4_173D4(rdram, &ctx);
    // Actual new initializer entry: separate generation.
    ctx.r4 = 0xffffffff80150000ULL;
    func_8021D7C4_5D8D54(rdram, &ctx);
    MEM_H(0x5C, a) = 0xFB;
    MEM_H(0x5E, a) = 0xFB;
    ctx.r4 = 0xffffffff80160000ULL;
    func_800167D4_173D4(rdram, &ctx);
    free(rdram);
    return 0;
}
'''

class UpgradeTests(unittest.TestCase):
    @staticmethod
    def v1():
        return make_v1(ORIGINAL_ACTOR, ORIGINAL_DRAW)

    def test_v1_helper_hash_locked(self):
        self.assertEqual(hashlib.sha256(OLD_HELPER.encode()).hexdigest(), V1_HELPER_SHA256)

    def test_source_install(self):
        a,d=upgrade_sources(*self.v1())
        self.assertIn('jp_model_trace_v2_register_actor(rdram, ctx);',a)
        self.assertIn('jp_model_trace_v2_original_draw(rdram, ctx);',d)
        self.assertNotIn('    jp_model_trace_draw_actor(rdram, ctx);',d)
        self.assertEqual(d.count('RECOMP_FUNC void func_800167D4_173D4('),1)
        self.assertEqual(d.count('RECOMP_FUNC void jp_model_trace_v2_original_draw('),2)
        self.assertEqual(a.count('void jp_model_trace_register_actor('),0)

    def test_refuses_v2_reapply(self):
        a,d=upgrade_sources(*self.v1())
        with self.assertRaisesRegex(ValueError,'already installed'):
            upgrade_sources(a,d)

    def test_refuses_unexpected_old_helper(self):
        a,d=self.v1()
        a=a.replace('static int jp_model_trace_loader_seen;', 'static int jp_model_trace_loader_seen;\n// changed')
        with self.assertRaisesRegex(ValueError,'differs'):
            upgrade_sources(a,d)

    def test_refuses_old_renderer_drift(self):
        a,d=self.v1()
        d=d.replace('    jp_model_trace_draw_actor(rdram, ctx);', '    (void)ctx;')
        with self.assertRaisesRegex(ValueError,'not found uniquely'):
            upgrade_sources(a,d)

    def test_rom_validation_rejects_bad(self):
        with self.assertRaisesRegex(ValueError,'exact 32-MiB'):
            validate_rom(b'not rom')
        self.assertEqual(GFX_TAIL_VMA,0x80161DBC)
        self.assertEqual(len(ROM_ANCHORS),7)

    def test_find_v1_generated_sources(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);a,d=self.v1()
            (p/'funcs_50.c').write_text(a)
            (p/'funcs_8.c').write_text(d)
            self.assertEqual(tuple(x.name for x in find_targets(p)),('funcs_50.c','funcs_8.c'))
            (p/'funcs_16.c').write_text(d)
            with self.assertRaisesRegex(ValueError,'duplicated'):
                find_targets(p)

    def test_compiled_native_synthetic_case(self):
        if subprocess.run(['which','cc'],capture_output=True).returncode:
            self.skipTest('host compiler missing')
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            a,d=upgrade_sources(*self.v1())
            for path,s in [('recomp.h',HEADER),('actor.c',a),('draw.c',d),('main.c',HARNESS)]:
                (p/path).write_text(s)
            c=subprocess.run(['cc','-std=c17','-Wall','-Wextra','-Werror','-o',str(p/'harness'),
                              *(str(p/x) for x in ['actor.c','draw.c','main.c'])],
                              capture_output=True,text=True)
            self.assertEqual(c.returncode,0,c.stderr)
            r=subprocess.run([str(p/'harness')],env={**os.environ,'GOEMON_JP_ACTOR_TRACE':'1'},
                              capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            out=r.stderr
            self.assertIn('LOADER JP=0x8021D7C4',out)
            self.assertIn('DRAW JP=0x800167D4',out)
            self.assertIn('TARGET actor=0x80150000 gen=1 model=0x00FB',out)
            self.assertIn('STATE_CHANGE actor=0x80150000 gen=1 model=0x00FB->0x0001',out)
            self.assertIn('REINIT actor=0x80150000 previous_gen=1 previous_model=0x0001',out)
            self.assertIn('TARGET actor=0x80150000 gen=2 model=0x00FB',out)
            self.assertIn('seg=8 address=0x803EB260 words=12131415,16171819',out)
            self.assertIn('seg=10 address=0x803A5680 words=ABCDEF01,22334455',out)
            self.assertEqual(out.count(' GFX_WINDOW '),3)
            self.assertIn('commands=2',out)
            self.assertIn('op06=1 opDE=0 op01=0 opDA=1',out)
            self.assertNotIn(' GFX_WINDOW_UNAVAILABLE ',out)
            off=subprocess.run([str(p/'harness')],env={**os.environ,'GOEMON_JP_ACTOR_TRACE':'0'},
                               capture_output=True,text=True)
            self.assertEqual(off.returncode,0,off.stderr)
            self.assertEqual(off.stderr,'')

if __name__=='__main__':
    unittest.main()