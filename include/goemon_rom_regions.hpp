#pragma once
// Verified parameters for region-isolated ROM decompression and future launch.
// This header does not register a Japanese recompiled executable.
#include <array>
#include <cstdint>

namespace goemon64::regions {
struct RomParameters {
    std::array<char, 4> internal_game_code;
    std::uint32_t file_table_offset;
    std::uint32_t decompressed_crc1;
    std::uint32_t decompressed_crc2;
    std::uint64_t original_rom_xxh3_64;
};

// XXH3-64 computed over the entire normalised 16 MiB original ROM; the
// USA value reproduces src/main/main.cpp's existing GameEntry.rom_hash.
inline constexpr RomParameters usa = {
    {'N', 'G', '5', 'E'}, 0x57FD8, 0x9CC11F4B, 0xABAA8538,
    0xDB1BC7EE0E6BEBA1ULL,
};
inline constexpr RomParameters japan_0 = {
    {'N', 'G', '5', 'J'}, 0x58258, 0x673A3EDC, 0x2491ADFC,
    0xD526A3DB80EB7924ULL,
};
}
