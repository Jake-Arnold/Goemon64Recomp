import unittest
from analyze_jp_rt64_current_run_v17 import summarize, parse

H='0x8042C12B60EC2B4E'

def target(frame=5,call=144,nz=0,loads=2,hash_=H):
    return (f'[JP-RT64] TEX_REPLAY_TARGET frame={frame} call={call} hash={hash_} '
            f'total_tmem_nonzero={nz} recent_loads={loads}')

def load(frame=5,call=144,addr='0x007953D0',pre=4096,post=0,nz=0,hash_=H):
    return (f'[JP-RT64] TEX_REPLAY_LOAD frame={frame} call={call} hash={hash_} '
            f'index=33 type=1 source_tex={addr} source_start={addr} '
            f'source_nonzero64={nz} load_siz=2 width=1 '
            f'tmem_nz_before={pre} tmem_nz_after={post}')

class CurrentRunV17(unittest.TestCase):
    def test_empty(self):
        self.assertIn('NO TARGETS', summarize([]))

    def test_clearing_source(self):
        x=summarize([target(loads=1),load()])
        self.assertIn('zero=1 nonzero=0',x)
        self.assertIn('0x007953D0 (load=33, src64=0/64, 4096->0)',x)
        self.assertIn('drops_to_zero=1',x)

    def test_no_clearing_in_window(self):
        x=summarize([target(loads=1),load(addr='0x003D13D0',pre=0,post=0,nz=64)])
        self.assertIn('NONE in recorded replay window',x)
        self.assertIn('src64=[64/64:1]',x)

    def test_two_snapshots_do_not_mix(self):
        x=summarize([target(loads=1),load(),target(frame=6,loads=1),load(frame=6,addr='0x003D13D0',pre=0,post=0,nz=64)])
        self.assertIn('targets=2',x)
        self.assertIn('windows with nonzero-to-zero TMEM load=1, without=1',x)

    def test_mismatched_load_rejected(self):
        x=summarize([target(loads=1),load(frame=8)])
        self.assertIn('unmatched=1',x)
        self.assertIn('incomplete_load_lists=1',x)

    def test_other_hash_filtered(self):
        x=summarize([target(hash_='0x4263CA7EF085E861',loads=0),target(loads=0)])
        self.assertIn('targets=1 other_hash_targets=1',x)

    def test_target_limit(self):
        x=summarize([target(loads=1),load(),load(addr='0x003D13D0')])
        self.assertIn('over_target_limit=1',x)
        self.assertIn('distinct source_start addresses in recorded load windows=1',x)

    def test_unread_not_zero(self):
        x=summarize([target(loads=1),load(nz=4294967295)])
        self.assertIn('src64=UNREAD',x)

    def test_missing_values_handled(self):
        x=summarize(['[JP-RT64] TEX_REPLAY_TARGET frame=5 call=144 hash='+H,
                    '[JP-RT64] TEX_REPLAY_LOAD frame=5 call=144 hash='+H])
        self.assertIn('unreported=1',x)
        self.assertIn('NOT_LOGGED',x)

    def test_load_not_accounted_without_target(self):
        x=summarize([load(), target(loads=0)])
        self.assertIn('load rows=0',x)

if __name__ == '__main__': unittest.main()
