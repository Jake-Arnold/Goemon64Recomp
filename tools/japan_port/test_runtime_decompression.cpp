// Synthetic structural regression for shared USA/Japan LZKN64 ROM handling.
// No original Nintendo game bytes are needed or used.
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <span>
#include <vector>

#include "goemon_game.h"
#include "goemon_rom_regions.hpp"

namespace {
void ensure(bool condition, const char* text) {
    if (!condition) {
        std::cerr << "ROM decompression regression failed: " << text << "\n";
        std::abort();
    }
}

void big_endian_word(std::vector<uint8_t>& bytes, size_t offset, uint32_t value) {
    bytes[offset] = static_cast<uint8_t>(value >> 24);
    bytes[offset + 1] = static_cast<uint8_t>(value >> 16);
    bytes[offset + 2] = static_cast<uint8_t>(value >> 8);
    bytes[offset + 3] = static_cast<uint8_t>(value);
}

uint32_t read_word(const std::vector<uint8_t>& bytes, size_t offset) {
    return (uint32_t(bytes[offset]) << 24)
         | (uint32_t(bytes[offset + 1]) << 16)
         | (uint32_t(bytes[offset + 2]) << 8)
         | uint32_t(bytes[offset + 3]);
}

std::vector<uint8_t> make_fake_rom(const goemon64::regions::RomParameters& region) {
    std::vector<uint8_t> rom(0x1000000, 0);
    rom[0] = 0x80; rom[1] = 0x37; rom[2] = 0x12; rom[3] = 0x40;
    for (size_t i = 0; i < region.internal_game_code.size(); ++i) {
        rom[0x3B + i] = static_cast<uint8_t>(region.internal_game_code[i]);
    }
    // One 16-byte uncompressed entry, then a zero sentinel.
    big_endian_word(rom, region.file_table_offset, 0x80000);
    big_endian_word(rom, region.file_table_offset + 4, 0x80010);
    for (size_t i = 0; i < 16; ++i) {
        rom[0x80000 + i] = static_cast<uint8_t>(i * 7 + 3);
    }
    return rom;
}

void validate(const goemon64::regions::RomParameters& region, bool japan) {
    auto rom = make_fake_rom(region);
    auto decompressed = japan
        ? goemon64::decompress_mnsg_japan(rom)
        : goemon64::decompress_mnsg(rom);
    ensure(decompressed.size() == 0x100000, "power-of-two output size");
    ensure(read_word(decompressed, 0x10) == region.decompressed_crc1, "regional CRC1");
    ensure(read_word(decompressed, 0x14) == region.decompressed_crc2, "regional CRC2");
    ensure(read_word(decompressed, region.file_table_offset) == 0x80000,
           "regional ROM file table offset");
    ensure(read_word(decompressed, region.file_table_offset + 4) == 0x80010,
           "regional ROM file table end");
    for (size_t i = 0; i < 16; ++i) {
        ensure(decompressed[0x80000 + i] == static_cast<uint8_t>(i * 7 + 3),
               "uncompressed entry payload");
    }
    for (size_t i = 0; i < region.internal_game_code.size(); ++i) {
        ensure(decompressed[0x3B + i] ==
                   static_cast<uint8_t>(region.internal_game_code[i]),
               "regional game code");
    }
}
}

int main() {
    validate(goemon64::regions::usa, false);
    validate(goemon64::regions::japan_0, true);
    std::cout << "Synthetic USA and Japan native ROM decompression: PASS\n";
    return 0;
}
