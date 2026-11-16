# Japanese native Linux — automatic persistent session and crash logs

Beginning with **v0.2.14-dev**, `Goemon64RecompiledJP` opens a new persistent
session log automatically every time the **game** starts, including when
launched from GNOME's desktop icon or as a standalone executable.

The game does not need a terminal, wrapper or external `tee` command.

## Where files go

Default Linux location:

```text
~/.local/state/goemon64recomp-jp/logs/
    latest.log
    session-YYYYMMDD-HHMMSS-pidNNNN-XXXXXX.log
    ...
```

If `XDG_STATE_HOME` is an absolute path, replace `~/.local/state`
with that path. The program prints the **exact current log path** as a
`[Goemon JP session log]` line when it begins. `latest.log` is a
symlink to the most recently launched session log, **not a copy**.

Log files are created with permissions `0600`; their log directory
is `0700`. Old session files are pruned after **20 retained sessions**.
Files survive normal application exit or native crashes until rotation
removes them. Keep a copy of an important crash log before starting
20 additional sessions.

Both stdout and stderr from the game and native runtime are copied to
the on-disk session log continuously, while still being shown in the
original terminal if one exists. The logger initializes before executable
preload, SDL, the game runtime and N64 guest worker creation. The
`--version` CLI command intentionally does not create a session log.

### When a crash happens

A handler for `SIGSEGV`, `SIGABRT`, `SIGBUS`, `SIGILL` and `SIGFPE`
writes a **direct, immediately appended** fatal-signal marker, including
signal number and available fault and instruction addresses, then
re-raises the signal using the default handler so the OS and debugger
can create a core dump.

Example:

```text
[Goemon JP FATAL SIGNAL] SIGSEGV number=11 fault_address=0x... instruction_pointer=0x... (see core dump for stack trace)
```

The logger does **not** manufacture a C++ backtrace inside a signal
handler, because doing so would be unsafe and could deadlock during
a real crash. On a crash, the last few messages still buffered in the
reader pipe may be missing; the fatal marker is written straight to
the file descriptor. Kills by `SIGKILL`, power loss and hardware failure
may leave no fatal marker. A full traceback may still require a Linux
core dump or GDB capture.

When a session log cannot be created (such as a full or read-only
home filesystem), a warning is printed to stderr and the game continues
without changing its previous behaviour.

## Uploading after a crash

In GNOME Files, press **Ctrl+L**, enter this directory and upload
`latest.log` (or the matching actual `session-...log` file):

```text
~/.local/state/goemon64recomp-jp/logs
```

For CLI:

```bash
ls -lh ~/.local/state/goemon64recomp-jp/logs
readlink -f ~/.local/state/goemon64recomp-jp/logs/latest.log
```

If using a custom `XDG_STATE_HOME`, use that root instead. Logs can
contain local paths, emulator diagnostics, game state and potentially
private data. Review before distributing publicly.

## Ubuntu build and integration validation

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-persistent-session-logs
git switch feature/japan-persistent-session-logs 2>/dev/null ||
  git switch --track origin/feature/japan-persistent-session-logs
git pull --ff-only

# This suite compiles the actual C++ logger into a small harness and
# deliberately tests SIGSEGV and SIGABRT with core dumps disabled.
python3 tools/japan_port/test_persistent_session_logs.py

for test in \
  test_reset_preflight \
  test_timer_runtime_stage1 \
  test_guest_threads_stage2 \
  test_guest_quiescence_stage3 \
  test_queue_cleaner_stage4 \
  test_guest_join_stage5 \
  test_native_events_stage6 \
  test_native_boot_save_audio_stage7 \
  test_graphics_queue_stage8 \
  test_jp_file80_data_fixups
do
  python3 "tools/japan_port/${test}.py"
done

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON \
  -DGOEMON_JP_EVENTS_STAGE6=ON \
  -DGOEMON_JP_BOOT_STAGE7=ON \
  -DGOEMON_JP_GRAPHICS_STAGE8=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

Expected: `v0.2.14-dev` and `[graphics-queue-audit]`, plus the exact
Git commit. Runtime crash testing must happen **only inside the harness**
above. Do not deliberately crash a gameplay session with an unsaved game.

The eleven-test harness checks normal stdout/stderr capture, preservation
of terminal messages, signal markers with standard Linux signal
termination, quick-exit draining, latest-log symlink, permissions,
20-session retention, inherited pipe writers and closed-terminal safety. The native gameplay build and desktop launch
still need Ubuntu verification.

## Scope

The logger is compiled **only into the Japanese Linux target**. No
original ROM, USA target, toolkit or pinned N64ModernRuntime file
is changed. F8 is still diagnostic-only; no N64 soft reset has been
enabled. Automatic logging does not constitute a shutdown barrier.
