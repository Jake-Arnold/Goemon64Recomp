"""Strict source-free postprocessor tests for bounded JP Gfx v3 records."""
import unittest
from analyze_jp_gfx_windows import parse, compare, summarize


def make(mode,sample,words):
    size=len(words)
    rows=[f'[JP-MODEL3] BEGIN actor=0x80150000 gen=32 model=0x00FB mode={mode} sample={sample} source=0x803EB260 start=0x80210000 end=0x{0x80210000+8*size:08X} commands={size}']
    rows += [f'[JP-MODEL3] CMD mode={mode} sample={sample} index={i} w0={w0:08X} w1={w1:08X}' for i,(w0,w1) in enumerate(words)]
    rows.append(f'[JP-MODEL3] END mode={mode} sample={sample} commands={size}')
    return '\n'.join(rows)

class AnalyzeTests(unittest.TestCase):
    def test_parse_and_diff_words_without_misreporting_opcodes(self):
        a=make(1,1,[(0x06000000,0x80110000),(0x01000000,0x80120000)])
        b=make(1,2,[(0x06000000,0x80110100),(0x01000001,0x80120000)])
        windows=parse(a+'\n'+b)
        d=compare(windows[(1,1)],windows[(1,2)])
        self.assertTrue(d['same_opcode_sequence'])
        self.assertEqual(d['first_word_changed'],[1])
        self.assertEqual(d['second_word_changed'],[0])
        self.assertEqual(d['opcode_changed'],[])
        self.assertIn('same_opcode_sequence=True',summarize(windows))

    def test_changes_in_command_opcode(self):
        a=make(4,1,[(0x06000000,0x80110000)])
        b=make(4,2,[(0xDE000000,0x80110000)])
        diff=compare(*parse(a+'\n'+b).values())
        self.assertFalse(diff['same_opcode_sequence'])
        self.assertEqual(diff['opcode_changed'],[0])

    def test_rejects_missing_commands(self):
        s=make(1,1,[(0x06000000,0x80110000)])
        s=s.replace('[JP-MODEL3] CMD mode=1 sample=1 index=0 w0=06000000 w1=80110000\n','')
        with self.assertRaisesRegex(ValueError,'incomplete'):
            parse(s)

    def test_rejects_duplicate_and_nested(self):
        s=make(4,1,[(0xE7000000,0)])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            parse(s+'\n'+s)
        with self.assertRaisesRegex(ValueError,'nested'):
            parse(s.splitlines()[0]+'\n'+s)

    def test_rejects_unbounded(self):
        s=make(1,1,[(0x06000000,0)]*65)
        with self.assertRaisesRegex(ValueError,'invalid bounded'):
            parse(s)

    def test_rejects_wrong_index_and_unknown(self):
        s=make(1,1,[(0x06000000,0)])
        with self.assertRaisesRegex(ValueError,'wrong command index'):
            parse(s.replace('index=0','index=10'))
        with self.assertRaisesRegex(ValueError,'unrecognized'):
            parse('[JP-MODEL3] RANDOM')

    def test_ignores_other_log_lines(self):
        s='Loading Goemon\n[JP-MODEL2] GFX_WINDOW\n'+make(4,1,[(0xE7000000,0)])
        self.assertEqual(len(parse(s)),1)

if __name__=='__main__':unittest.main()