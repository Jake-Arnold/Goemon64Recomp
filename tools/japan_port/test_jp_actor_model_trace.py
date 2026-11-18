"""ROM-free tests and a real host-C execution fixture for JP actor graphics tracing."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from jp_actor_model_trace import (
    ACTOR_SIG, DRAW_SIG, HELPER, MARKER,
    find_targets, transform, validate_rom,
)

SKELETON = '#include "recomp.h"\n\n' + ACTOR_SIG + '    (void)rdram; (void)ctx;\n}\n'
RENDER = '#include "recomp.h"\n\n' + DRAW_SIG + '    (void)rdram; (void)ctx;\n}\n'
HEADER = r'''#ifndef RECOMP_H
#define RECOMP_H
#include <stdint.h>
typedef int64_t gpr;
typedef struct { uint64_t r4; } recomp_context;
#define RECOMP_FUNC
// Stub mapping simulates the N64 host wordswapped RDRAM arrangement.
#define MEM_W(off,base) (*(uint32_t*)(rdram + ((((uint32_t)(base))+(off)) & 0x7fffffu)))
#define MEM_H(off,base) (*(uint16_t*)(rdram + (((((uint32_t)(base))+(off)) & 0x7fffffu) ^ 2u)))
#endif
'''
HARNESS = r'''#include "recomp.h"
#include <stdlib.h>
#include <stdio.h>
void func_8021D7C4_5D8D54(uint8_t*, recomp_context*);
void func_800167D4_173D4(uint8_t*, recomp_context*);
int main(void) {
    uint8_t* rdram = calloc(0x800000u, 1u);
    if (!rdram) return 11;
    recomp_context ctx = {0};
    ctx.r4 = 0xffffffff80150000ULL;
    func_8021D7C4_5D8D54(rdram, &ctx);
    // Emulate original actor stores AFTER the entry trace registers a0.
    gpr actor = (gpr)(int64_t)(int32_t)0x80150000u;
    MEM_H(0x5C, actor) = 0xFBu;
    MEM_H(0x5E, actor) = 0xFBu;
    MEM_W(0x18, actor) = 0x80160000u;
    gpr obj = (gpr)(int64_t)(int32_t)0x80160000u;
    MEM_W(0x2C, obj) = 0x790047F8u;
    MEM_W(0x30, obj) = 0x07029980u;
    MEM_H(0x34, obj) = 0x0120u;
    MEM_W(0x38, obj) = 0x80300000u;
    ctx.r4 = 0xffffffff80160000ULL;
    func_800167D4_173D4(rdram, &ctx);
    // Repeated draw should not emit a second BOUND line.
    func_800167D4_173D4(rdram, &ctx);
    free(rdram);
    return 0;
}
'''

class TraceTests(unittest.TestCase):
    def test_injected_functions_and_distinct_sources(self):
        actor, draw = transform(SKELETON, RENDER)
        self.assertIn('jp_model_trace_register_actor(rdram, ctx);', actor)
        self.assertIn('jp_model_trace_draw_actor(rdram, ctx);', draw)
        self.assertEqual(actor.count("void jp_model_trace_register_actor(uint8_t*"), 1)
        self.assertIn('extern void jp_model_trace_draw_actor(', draw)

    def test_same_unit_injection(self):
        source = '#include "recomp.h"\n'+ DRAW_SIG+'}\n'+ACTOR_SIG+'}\n'
        a,b=transform(source, source)
        self.assertEqual(a,b)
        self.assertIn('jp_model_trace_register_actor(rdram, ctx);',a)
        self.assertIn('jp_model_trace_draw_actor(rdram, ctx);',a)

    def test_refuse_second_install(self):
        a,d=transform(SKELETON, RENDER)
        with self.assertRaisesRegex(ValueError, 'already applied'):
            transform(a,d)

    def test_refuse_missing_function(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            transform(SKELETON, '#include "recomp.h"\n')

    def test_refuse_bad_rom(self):
        with self.assertRaisesRegex(ValueError, 'exact original'):
            validate_rom(b'bad')

    def test_find_unique_symbols(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'funcs_0.c').write_text(RENDER)
            (root/'funcs_9.c').write_text(SKELETON)
            got=find_targets(root)
            self.assertEqual(tuple(x.name for x in got), ('funcs_9.c','funcs_0.c'))
            (root/'funcs_10.c').write_text(RENDER)
            with self.assertRaisesRegex(ValueError,'found 2'):
                find_targets(root)

    def test_synthetic_native_execution(self):
        if subprocess.run(['which','cc'],capture_output=True).returncode:
            self.skipTest('No host C compiler')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            a,d=transform(SKELETON, RENDER)
            (root/'recomp.h').write_text(HEADER)
            (root/'actor.c').write_text(a)
            (root/'draw.c').write_text(d)
            (root/'main.c').write_text(HARNESS)
            executable=root/'test_actor_trace'
            built=subprocess.run(['cc','-std=c17','-Wall','-Wextra','-Werror',
                                  '-o',str(executable),str(root/'actor.c'),str(root/'draw.c'),
                                  str(root/'main.c')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            enabled=subprocess.run([str(executable)],capture_output=True,text=True,
                                   env={**os.environ,'GOEMON_JP_ACTOR_TRACE':'1'})
            self.assertEqual(enabled.returncode,0,enabled.stderr)
            self.assertIn('LOADER_ENTRY',enabled.stderr)
            self.assertIn('DRAW_ENTRY',enabled.stderr)
            self.assertIn('TARGET_SEEN actor=0x80150000',enabled.stderr)
            self.assertIn('BOUND actor=0x80150000 model_id=0x00FB',enabled.stderr)
            self.assertIn('OVERLAY slot=0 file_id=0x0120',enabled.stderr)
            self.assertEqual(enabled.stderr.count(' BOUND '),1)
            disabled=subprocess.run([str(executable)],capture_output=True,text=True,
                                    env={**os.environ,'GOEMON_JP_ACTOR_TRACE':'0'})
            self.assertEqual(disabled.stderr,'')

if __name__=='__main__': unittest.main()