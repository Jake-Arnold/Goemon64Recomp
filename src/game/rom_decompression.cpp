#include <cassert>
#include <cstring>
#include <fstream>

#include "goemon_game.h"
#include "goemon_rom_regions.hpp"

#ifdef _MSC_VER
inline uint32_t byteswap(uint32_t val) {
    return _byteswap_ulong(val);
}
#else
constexpr uint32_t byteswap(uint32_t val) {
    return __builtin_bswap32(val);
}
#endif

constexpr uint8_t COMMAND_SLIDING_WINDOW_COPY_END = 0x7F;
constexpr uint8_t COMMAND_SLIDING_WINDOW_COPY_LENGTH_MASK = 0x7C;
constexpr uint8_t COMMAND_SLIDING_WINDOW_COPY_OFFSET_FIRST_BYTE_MASK = 0x03;
constexpr uint16_t COMMAND_SLIDING_WINDOW_COPY_OFFSET_MAX_MASK = 0x3FF;

constexpr uint8_t COMMAND_RAW_COPY_END = 0x9F;
constexpr uint8_t COMMAND_RAW_COPY_LENGTH_MASK = 0x1F;

constexpr uint8_t COMMAND_RLE_WRITE_SHORT_ANY_VALUE_END = 0xDF;
constexpr uint8_t COMMAND_RLE_WRITE_SHORT_ANY_VALUE_LENGTH_MASK = 0x1F;

constexpr uint8_t COMMAND_RLE_WRITE_SHORT_ZERO_END = 0xFE;
constexpr uint8_t COMMAND_RLE_WRITE_SHORT_ZERO_LENGTH_MASK = 0x1F;

constexpr uint8_t COMMAND_RLE_WRITE_LONG_ZERO = 0xFF;
constexpr uint8_t COMMAND_RLE_WRITE_LONG_ZERO_LENGTH_MASK = 0xFF;

size_t lzkn64_decompress(std::span<const uint8_t> input, std::span<uint8_t> output) {
    size_t input_pos = 4;
    size_t output_pos = 0;

    uint32_t compressed_size = byteswap(*reinterpret_cast<const uint32_t*>(input.data()));
    if (compressed_size > input.size()) {
        return 0;
    }

    while (input_pos < compressed_size) {
        uint8_t command = input[input_pos++];

        if (command <= COMMAND_SLIDING_WINDOW_COPY_END) {
            uint8_t length = (command & COMMAND_SLIDING_WINDOW_COPY_LENGTH_MASK) >> 2;
            uint16_t offset_first_byte = (command & COMMAND_SLIDING_WINDOW_COPY_OFFSET_FIRST_BYTE_MASK) << 8;
            uint8_t offset_second_byte = input[input_pos++];
            uint16_t offset = (offset_first_byte | offset_second_byte) & COMMAND_SLIDING_WINDOW_COPY_OFFSET_MAX_MASK;

            // Add 2 to get the actual length since 2 is the minimum length.
            length += 2;

            for (size_t i = 0; i < length; i++) {
                output[output_pos] = output[output_pos - offset];
                output_pos++;
            }
        } else if (command <= COMMAND_RAW_COPY_END) {
            uint8_t length = command & COMMAND_RAW_COPY_LENGTH_MASK;

            for (size_t i = 0; i < length; i++) {
                output[output_pos++] = input[input_pos++];
            }
        } else if (command <= COMMAND_RLE_WRITE_SHORT_ANY_VALUE_END) {
            uint8_t length = command & COMMAND_RLE_WRITE_SHORT_ANY_VALUE_LENGTH_MASK;
            uint8_t value = input[input_pos++];

            // Add 2 to get the actual length since 2 is the minimum length.
            length += 2;

            for (size_t i = 0; i < length; i++) {
                output[output_pos++] = value;
            }
        } else if (command <= COMMAND_RLE_WRITE_SHORT_ZERO_END) {
            uint8_t length = command & COMMAND_RLE_WRITE_SHORT_ZERO_LENGTH_MASK;

            // Add 2 to get the actual length since 2 is the minimum length.
            length += 2;

            for (size_t i = 0; i < length; i++) {
                output[output_pos++] = 0;
            }
        } else if (command == COMMAND_RLE_WRITE_LONG_ZERO) {
            uint16_t length = input[input_pos++] & COMMAND_RLE_WRITE_LONG_ZERO_LENGTH_MASK;

            // Add 2 to get the actual length since 2 is the minimum length.
            length += 2;

            for (size_t i = 0; i < length; i++) {
                output[output_pos++] = 0;
            }
        } else {
            // Invalid command.
        }
    }

    // Return the output position as the output size.
    return output_pos;
}

size_t lzkn64_decompress_rom(std::span<const uint8_t> input_rom, std::span<uint8_t> output_rom, size_t file_table_offset) {
    const uint32_t* input_file_table_entry = reinterpret_cast<const uint32_t*>(input_rom.data() + file_table_offset);
    uint32_t* output_file_table_entry = reinterpret_cast<uint32_t*>(output_rom.data() + file_table_offset);
    uint32_t rom_offset = byteswap(input_file_table_entry[0]) & 0x7FFFFFFF;

    while (input_file_table_entry[0] != 0 && input_file_table_entry[1] != 0) {
        uint8_t file_is_compressed = (byteswap(input_file_table_entry[0]) & 0x80000000) >> 31;
        uint32_t file_offset = byteswap(input_file_table_entry[0]) & 0x7FFFFFFF;
        uint32_t file_size = (byteswap(input_file_table_entry[1]) & 0x7FFFFFFF) - file_offset;

        if (file_is_compressed) {
            std::span input_span = input_rom.subspan(file_offset, file_size);
            std::span output_span = output_rom.subspan(rom_offset);

            file_size = lzkn64_decompress(input_span, output_span);
        } else {
            memcpy(output_rom.data() + rom_offset, input_rom.data() + file_offset, file_size);
        }

        // Update the table entries for the current and the next file.
        output_file_table_entry[0] = byteswap(rom_offset);
        output_file_table_entry[1] = byteswap(rom_offset + ((file_size + 0xF) & ~0xF));

        rom_offset += (file_size + 0xF) & ~0xF;

        input_file_table_entry++;
        output_file_table_entry++;
    }

    return rom_offset;
}

constexpr size_t MAXIMUM_ROM_SIZE = 0x4000000;

// The compressed ROM structure is shared by USA and Japan, but its file
// table, game code and decompressed-header CRCs are region-specific.
// Keep the original USA entrypoint as-is for existing releases.
static std::vector<uint8_t> decompress_mnsg_region(
    std::span<const uint8_t> compressed_rom,
    const goemon64::regions::RomParameters& parameters
) {
    if (compressed_rom.size() != 0x1000000) {
        assert(false);
        return {};
    }

    for (size_t i = 0; i < parameters.internal_game_code.size(); ++i) {
        if (compressed_rom[0x3B + i] != static_cast<uint8_t>(parameters.internal_game_code[i])) {
            assert(false);
            return {};
        }
    }

    std::vector<uint8_t> ret(MAXIMUM_ROM_SIZE);
    memcpy(ret.data(), compressed_rom.data(), compressed_rom.size());

    size_t final_size = lzkn64_decompress_rom(
        compressed_rom, ret, parameters.file_table_offset
    );

    // Preserve the original runtime's power-of-two output alignment.
    if (final_size == 0 || final_size > MAXIMUM_ROM_SIZE) {
        assert(false);
        return {};
    }
    final_size--;
    final_size |= final_size >> 1;
    final_size |= final_size >> 2;
    final_size |= final_size >> 4;
    final_size |= final_size >> 8;
    final_size |= final_size >> 16;
    final_size++;
    ret.resize(final_size);

    *reinterpret_cast<uint32_t*>(ret.data() + 0x10) =
        byteswap(parameters.decompressed_crc1);
    *reinterpret_cast<uint32_t*>(ret.data() + 0x14) =
        byteswap(parameters.decompressed_crc2);
    return ret;
}

std::vector<uint8_t> goemon64::decompress_mnsg(
    std::span<const uint8_t> compressed_rom
) {
    return decompress_mnsg_region(compressed_rom, regions::usa);
}

// Intentionally not registered in supported_games yet: Japanese
// game code/overlays must be linked into their own native build first.
std::vector<uint8_t> goemon64::decompress_mnsg_japan(
    std::span<const uint8_t> compressed_rom
) {
    return decompress_mnsg_region(compressed_rom, regions::japan_0);
}
