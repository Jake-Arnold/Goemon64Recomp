#pragma once
// Verified parameters for region-isolated ROM decompression.
// This does not register a Japanese recompiled executable.
#include <array>
#include <cstdint>

namespace goemon64::regions {
struct RomParameters {
    std::array<char, 4> internal_game_code;
    std::uint32_t file_table_offset;
    std::uint32_t decompressed_crc1;
    std::uint32_t decompressed_crc2;
};

inline constexpr RomParameters usa = {
    {'N', 'G', '5', 'E'}, 0x57FD8, 0x9CC11F4B, 0xABAA8538
};
inline constexpr RomParameters japan_0 = {
    {'N', 'G', '5', 'J'}, 0x58258, 0x673A3EDC, 0x2491ADFC
};
}
