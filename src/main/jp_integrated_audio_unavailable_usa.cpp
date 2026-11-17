// Only linked into the USA executable when the shared Japanese integrated
// reset experiment is enabled. The experimental librecomp archive contains
// a reference to this symbol, but the actual SDL audio reset callback exists
// only in the JP frontend (main.cpp, gated by its JP-only compile definition).
//
// Keep the USA executable linkable without enabling reset operations there.
// A hypothetical call from the USA executable must fail closed.
namespace recomp {
bool jp_reset_audio_buffer_after_join() {
    return false;
}
} // namespace recomp
