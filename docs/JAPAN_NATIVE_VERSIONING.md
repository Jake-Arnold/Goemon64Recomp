# Japanese native PC port — build identification

The Japanese native executable has a separate, explicitly incremented
development version. Do not copy a feature from one branch into another
without checking and bumping the target branch's version first.

## Current baseline and increment policy

- Stable Japanese baseline after Ubuntu dock integration: `v0.2.2-dev`.
- Next Japanese build-identity feature: `v0.2.3-dev`.
- Increment the **patch** number for each new user-visible Japanese native build,
  including fixes, usability work, and testable development milestones.
- Increment the **minor** number for a planned compatibility milestone, and the
  **major** number only for incompatible changes.
- Do not reuse an earlier number for a different feature branch or silently
  overwrite a build under the same version. For ongoing commits within the same
  version, the generated Git commit fingerprint must distinguish exact binaries.
- Keep experimental changes in separate branches and mark failed builds clearly.
  The prior `v0.2.1-dev` F8 process-relaunch experiment is **not a working N64 reset**.

## How to identify the executable

For `GOEMON_BUILD_JAPAN=ON`, every native build regenerates the
`goemon_japan_build_id.h` file from the checked-out Git commit (short SHA,
plus `-dirty` if tracked source files differ from Git). It is regenerated on
**every build** but rewritten only when its content changes.

The exact version and fingerprint appear in:

1. The Japanese launcher footer.
2. The SDL window title (also visible during gameplay).
3. `Goemon64RecompiledJP --version` (runs without opening SDL or loading ROMs).

The USA executable keeps its existing version and title behaviour.

## Building and verifying on Ubuntu

```bash
cd ~/Goemon64Recomp-JP
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
git rev-parse --short=10 HEAD
git status --short
```

Confirm the displayed commit matches `git rev-parse`; if `-dirty`
appears, inspect tracked modifications with `git status --short`.

The desktop launcher uses the same compiled binary; it cannot have a different
version unless its wrapper points to a separate binary.

## Test discipline

When reporting crashes or successful gameplay regressions, capture the exact
`vMAJOR.MINOR.PATCH-dev (commit[-dirty])` string, the JP ROM revision,
the tested location, and the result. Do not treat a version bump alone
as proof of compilation or gameplay compatibility.
