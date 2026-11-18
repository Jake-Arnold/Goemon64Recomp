"""Fail-closed v2→v3 actor Gfx trace tests, including compiled native-C fixture."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from jp_actor_model_trace import transform as make_v1
from jp_actor_model_trace_v2 import HELPER as V2_HELPER, upgrade_sources as make_v2
from jp_actor_model_trace_v3 import (V2_HELPER_SHA256, V3_MARKER, find_sources,
                                      upgrade_sources as make_v3, validate_rom)
from test_jp_actor_model_trace_v2 import ORIGINAL_ACTOR, ORIGINAL_DRAW, HEADER, HARNESS


class TraceV3Tests(unittest.TestCase):
    def v2(self):
        return make_v2(*make_v1(ORIGINAL_ACTOR, ORIGINAL_DRAW))

    def test_pinned_v2_helper(self):
        self.assertEqual(hashlib.sha256(V2_HELPER.encode()).hexdigest(), V2_HELPER_SHA256)

    def test_exact_upgrade_only_changes_actor_unit(self):
        actor, draw = self.v2()
        after_actor, after_draw = make_v3(actor, draw)
        self.assertIs(after_draw, draw)
        self.assertEqual(after_actor.count(V3_MARKER), 1)
        self.assertEqual(after_actor.count('static unsigned jp_v3_samples_mode1;'), 1)
        self.assertEqual(after_actor.count('static unsigned jp_v3_samples_mode4;'), 1)
        self.assertEqual(after_actor.count('jp_model_trace_v2_register_actor(rdram, ctx);'), 1)
        self.assertEqual(draw.count('jp_model_trace_v2_end(rdram, &frame);'), 1)

    def test_refuses_repeat_upgrade(self):
        actor, draw = make_v3(*self.v2())
        with self.assertRaisesRegex(ValueError, 'already installed'):
            make_v3(actor, draw)

    def test_refuses_mutated_v2_helper(self):
        actor, draw = self.v2()
        actor = actor.replace('static unsigned jp_v2_loader_logged, jp_v2_draw_logged;',
                              'static unsigned jp_v2_loader_logged, jp_v2_draw_logged;\n// altered')
        # Drift must occur inside the authenticated helper. The actual original has int fields.
        if actor == self.v2()[0]:
            actor = actor.replace('static int jp_v2_loader_logged, jp_v2_draw_logged;',
                                  'static int jp_v2_loader_logged, jp_v2_draw_logged;\n// altered')
        with self.assertRaisesRegex(ValueError,'modified v2 helper'):
            make_v3(actor, draw)

    def test_refuses_non_v2_renderer(self):
        actor, draw = self.v2()
        draw=draw.replace('    jp_model_trace_v2_end(rdram, &frame);\n', '    (void)frame;\n')
        with self.assertRaisesRegex(ValueError,'not the exact v2 wrapper'):
            make_v3(actor, draw)

    def test_refuses_wrong_region_rom(self):
        with self.assertRaisesRegex(ValueError,'exact original Japanese'):
            validate_rom(b'not a Japanese ROM')

    def test_requires_unique_generated_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a,d=self.v2()
            (root/'funcs_50.c').write_text(a)
            (root/'funcs_8.c').write_text(d)
            self.assertEqual(tuple(p.name for p in find_sources(root)),('funcs_50.c','funcs_8.c'))
            (root/'funcs_77.c').write_text(a)
            with self.assertRaisesRegex(ValueError,'separate actor/renderer'):
                find_sources(root)

    def test_compiled_c_2_samples_for_each_mode_and_off_mode(self):
        if subprocess.run(['which','cc'],capture_output=True).returncode:
            self.skipTest('C compiler missing')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            actor,draw=make_v3(*self.v2())
            # Three mode-1 draws: quota captures only the first two.
            # Mode-4 draws remain in the original harness.
            harness = HARNESS.replace('// A real change without a loader re-entry: same generation.',
                   'func_800167D4_173D4(rdram, &ctx);\n    '
                   'func_800167D4_173D4(rdram, &ctx);\n    '
                   '// A real change without a loader re-entry: same generation.')
            for name,src in [('recomp.h',HEADER),('actor.c',actor),('draw.c',draw),('main.c',harness)]:
                (root/name).write_text(src)
            command=['cc','-std=c17','-Wall','-Wextra','-Werror','-o',str(root/'test'),
                     str(root/'actor.c'),str(root/'draw.c'),str(root/'main.c')]
            p=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            run=subprocess.run([str(root/'test')],env={**os.environ,'GOEMON_JP_ACTOR_TRACE':'1'},
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            lines=run.stderr.splitlines()
            b=[l for l in lines if '[JP-MODEL3] BEGIN' in l]
            c=[l for l in lines if '[JP-MODEL3] CMD' in l]
            e=[l for l in lines if '[JP-MODEL3] END' in l]
            self.assertEqual(len(b),4,run.stderr)
            self.assertEqual(len(c),8,run.stderr)
            self.assertEqual(len(e),4,run.stderr)
            self.assertTrue(any('mode=1 sample=1' in l for l in b))
            self.assertTrue(any('mode=1 sample=2' in l for l in b))
            self.assertTrue(any('mode=4 sample=1' in l for l in b))
            self.assertTrue(any('w0=06000000 w1=80301020' in l for l in c))
            self.assertTrue(any('w0=DA000000 w1=80211000' in l for l in c))
            self.assertEqual(sum(' GFX_WINDOW ' in l for l in lines),5)
            off=subprocess.run([str(root/'test')],env={**os.environ,'GOEMON_JP_ACTOR_TRACE':'0'},
                               capture_output=True,text=True)
            self.assertEqual(off.returncode,0,off.stderr)
            self.assertEqual(off.stderr,'')


if __name__=='__main__':
    unittest.main()