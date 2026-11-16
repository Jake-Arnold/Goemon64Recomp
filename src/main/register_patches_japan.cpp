#include "ovl_patches.hpp"
// Explicitly exclude the USA patch binary and exported USA addresses.
// Japanese-specific patches are required for runtime/playability validation.
void goemon64::register_patches() {}
