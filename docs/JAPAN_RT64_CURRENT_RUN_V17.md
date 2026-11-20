# JP robot current-run replay cause classification — v17 (RESEARCH_ONLY)

## User evidence (20 November 2026)

The actual v16 log under `~/goemon-jp-texture-segment-v16.log` has **11** TEX_REPLAY_TARGET lines with robot hash `0x8042C12B60EC2B4E` and **zero** TEX_REPLAY_LOAD lines with source_start `0x0078B6E0` or `0x007953D0`. The v16 source trace returned one control event with raw `0x08000790`, segment-8 base `0x003D0C40`, resolved and RDP image address `0x003D13D0`. The earlier v13 high-address findings must not be conflated with the current run.

The 11 target hashes by themselves do not establish this run's per-target `total_tmem_nonzero`, whether it was 0 in all captures, or which RDP load last changed TMEM. The v12 replay ring is limited to the latest 32 loads and can include the same load in multiple upload snapshots.

## Read-only v17 analyzer

`tools/japan_port/analyze_jp_rt64_current_run_v17.py` scans the **same existing** v16 log, groups the robot-hash target lines with their matching bounded load records, classifies whether each target had whole-TMEM nonzero=0, and reports load operations whose whole-TMEM count changes from positive to zero. It also groups other source_start values, counts first-64 RDRAM bytes (0 versus unread), and flags incomplete load lists and absent histories. It never assumes the earlier high source addresses recur; no rendering patch, ROM/asset extraction, source modification or new gameplay capture is required.

Run:

    cd ~/Goemon64Recomp-JP
    git fetch origin research/japan-native-actor-model-trace-20261118
    git show FETCH_HEAD:tools/japan_port/analyze_jp_rt64_current_run_v17.py > /tmp/analyze_jp_rt64_current_run_v17.py
    python3 /tmp/analyze_jp_rt64_current_run_v17.py ~/goemon-jp-texture-segment-v16.log

Interpret `nonzero_to_zero` as whole-TMEM change, not proof it cleared the particular tile. If no such transition appears, it may have happened earlier than the bounded replay history, or the TMEM was zero before the recorded operations. For source_nonzero64, UNREAD means the sample was unavailable, not that the bytes were zero.

## Verification

10 synthetic Python unittest cases and `py_compile` run on the assistant host: PASS. Actual user gameplay execution and independent inspection of the user's private log: NOT RUN. Research-only; does not change game version or native runtime.
